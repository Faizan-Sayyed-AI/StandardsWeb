"""
Pins the way a rate_limited API key gets back to active.

The bug this covers took RSS polling down for weeks in production. `rate_limited`
had no time-based exit:

  * _poll_feed_async returns early, with no HTTP request at all, when the
    assigned key's status is not `active` (tasks/feeds.py).
  * The only automatic transition back to `active` lives in
    record_key_success(), which runs only *after* a successful rss2json call.

So leaving `rate_limited` required a request that being `rate_limited`
prevented. rss2json resets its quotas daily; the flag never expired. Once the
last active key tripped, every scheduled poll was skipped indefinitely and
only a manual database edit could restart it.

These tests write api_keys rows, but always inside a transaction that is rolled
back — nothing is committed.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.api_key import ApiKey, ApiKeyStatus
from app.services.api_key_service import recover_rate_limited_keys

COOLDOWN = timedelta(hours=6)


def _stale() -> datetime:
    """A failure old enough that the cooldown has elapsed."""
    return datetime.now(timezone.utc) - (COOLDOWN + timedelta(minutes=1))


def _recent() -> datetime:
    """A failure still inside the cooldown."""
    return datetime.now(timezone.utc) - (COOLDOWN - timedelta(minutes=1))


@pytest_asyncio.fixture
async def keys(db):
    """
    Insert one key per interesting state and roll back afterwards.

    Labels are unique-suffixed because `label` carries a UNIQUE constraint and
    the target database already holds the real pool.
    """
    suffix = datetime.now(timezone.utc).strftime("%H%M%S%f")
    made: dict[str, ApiKey] = {}
    for name, status, failed_at in [
        ("stale_rate_limited", ApiKeyStatus.rate_limited, _stale()),
        ("recent_rate_limited", ApiKeyStatus.rate_limited, _recent()),
        ("never_stamped", ApiKeyStatus.rate_limited, None),
        ("expired", ApiKeyStatus.expired, _stale()),
        ("disabled", ApiKeyStatus.disabled, _stale()),
        ("active", ApiKeyStatus.active, None),
    ]:
        key = ApiKey(
            label=f"test-{name}-{suffix}",
            key_value="not-a-real-key",
            capacity=25,
            status=status,
            consecutive_failures=1 if failed_at else 0,
            last_failure_at=failed_at,
        )
        db.add(key)
        made[name] = key
    await db.flush()
    try:
        yield made
    finally:
        await db.rollback()


async def test_recovers_a_key_whose_cooldown_has_elapsed(db, keys):
    """The core fix: the state is no longer terminal."""
    recovered = await recover_rate_limited_keys(db, cooldown=COOLDOWN)

    assert keys["stale_rate_limited"].id in {k.id for k in recovered}
    assert keys["stale_rate_limited"].status == ApiKeyStatus.active


async def test_leaves_a_key_still_inside_its_cooldown(db, keys):
    """
    Recovery must wait, or every poll hammers a key rss2json is still
    refusing and the pool never gets a chance to settle.
    """
    recovered = await recover_rate_limited_keys(db, cooldown=COOLDOWN)

    assert keys["recent_rate_limited"].id not in {k.id for k in recovered}
    assert keys["recent_rate_limited"].status == ApiKeyStatus.rate_limited


async def test_recovers_a_rate_limited_key_with_no_failure_timestamp(db, keys):
    """
    last_failure_at is nullable, and a key parked in `rate_limited` without one
    has no cooldown to elapse — it would stay stuck for good, which is exactly
    the failure being fixed. Treat the missing stamp as long past.
    """
    recovered = await recover_rate_limited_keys(db, cooldown=COOLDOWN)

    assert keys["never_stamped"].id in {k.id for k in recovered}
    assert keys["never_stamped"].status == ApiKeyStatus.active


@pytest.mark.parametrize("name", ["expired", "disabled"])
async def test_never_touches_a_key_that_will_not_heal_itself(db, keys, name):
    """
    Only `rate_limited` is transient. An expired credential and a key an admin
    switched off must both stay put — reviving either would send every poll at
    a key that cannot work, and would silently undo an operator's decision.
    """
    before = keys[name].status
    recovered = await recover_rate_limited_keys(db, cooldown=COOLDOWN)

    assert keys[name].id not in {k.id for k in recovered}
    assert keys[name].status == before


async def test_reports_nothing_when_no_key_is_due(db, keys):
    """The hourly sweep is a no-op on a healthy pool, and says so."""
    await recover_rate_limited_keys(db, cooldown=COOLDOWN)  # drains the due ones
    assert await recover_rate_limited_keys(db, cooldown=COOLDOWN) == []


async def test_recovered_key_is_visible_to_the_pool_picker(db, keys):
    """
    The end-to-end point of the fix: after recovery the key is `active`, which
    is the state both the poll gate and pick_key_with_spare_capacity select on.
    """
    await recover_rate_limited_keys(db, cooldown=COOLDOWN)

    active_ids = {
        k.id
        for k in (
            await db.execute(select(ApiKey).where(ApiKey.status == ApiKeyStatus.active))
        ).scalars()
    }
    assert keys["stale_rate_limited"].id in active_ids
    assert keys["recent_rate_limited"].id not in active_ids
