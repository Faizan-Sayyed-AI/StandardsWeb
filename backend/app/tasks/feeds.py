"""
Celery tasks: feeds queue.

M2 full implementation: RSS polling, ISO reference extraction, diff logic.

Tasks:
  poll_feed(feed_id)  — Fetch, parse, diff and persist one feed (primary task)
  poll_all_feeds()    — Fan-out dispatcher for all enabled feeds (Beat entry)

poll_feed flow (PRD §8.3):
  1. Load feed record from DB; skip if disabled.
  2. Fetch RSS XML via httpx (10 s timeout, follow redirects).
  3. Parse with feedparser.
  4. For each entry:
       a. Extract ISO/IEC/IEEE reference number with regex.
       b. Compute SHA-256 content hash (title + link + published + updated + summary).
       c. Query standards table by iso_reference.
       d. INSERT new standard + history row (event_type=new) if not found.
       e. UPDATE standard + append history row if content_hash differs.
       f. Skip if hash unchanged (no-op).
  5. Update rss_feeds: last_polled_at, last_poll_status=ok, failure_count=0.
  6. Commit.

Retry policy (exponential backoff — PRD §8.3 step 9):
  Attempt 1 fails → retry after  60 s  (retries=0)
  Attempt 2 fails → retry after 120 s  (retries=1)
  Attempt 3 fails → retry after 240 s  (retries=2)
  Attempt 4 fails → mark permanently failed, log critical alert (retries=3)
"""

import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx
import structlog
from sqlalchemy import select

from app.celery_app import celery
from app.models.rss_feed import PollStatus, RssFeed
from app.models.standard import Standard, StandardStatus
from app.models.standard_history import EventSource, EventType, StandardHistory

log = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ISO Reference Regex
#
# Matches (case-insensitive):
#   ISO 9001:2015          ISO/IEC 27001         ISO/IEC/IEEE 90003:2018
#   IEC 60601-1:2005       IEEE 802.3:2022        ISO 3166-1
#
# Requires ≥2 main digits to avoid matching committee IDs (e.g. "ISO TC 176").
# ─────────────────────────────────────────────────────────────────────────────
_ISO_REF_RE = re.compile(
    r"\b"
    r"("                                    # capture group start
    r"(?:ISO(?:/IEC)?(?:/IEEE)?|IEC|IEEE)"  # standard body prefix
    r"\s+"
    r"\d{2,}"                               # main number, ≥2 digits
    r"(?:[.\-]\d+)*"                        # optional part numbers: -1, .1
    r"(?::\d{4})?"                          # optional year :2015
    r")"                                    # capture group end
    r"\b",
    re.IGNORECASE,
)

_EDITION_RE = re.compile(r":(\d{4})\b")

# Lifecycle keywords used to classify the change event type
_WITHDRAWN_KW = frozenset(("withdrawn", "cancelled", "cancell", "obsolete"))
_REPLACED_KW = frozenset(("replaced", "superseded"))
_AMENDED_KW = frozenset(("amended", "amendment", "corrigendum", "amd"))


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────
def extract_iso_reference(text: str) -> str | None:
    """
    Return the first ISO/IEC/IEEE reference found in *text*, normalised to
    uppercase with single spaces.  Returns None if no reference is detected.
    """
    match = _ISO_REF_RE.search(text)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip().upper()
    return None


def compute_content_hash(entry: Any) -> str:
    """
    Compute a SHA-256 fingerprint of an RSS entry.

    Fields hashed: title, link, published, updated, summary (first 500 chars).
    A different hash on subsequent polls indicates content has changed.
    """
    h = hashlib.sha256()
    for field in ("title", "link", "published", "updated"):
        h.update(str(entry.get(field, "")).encode())
    # Limit summary to 500 chars to avoid hashing boilerplate footers
    h.update(str(entry.get("summary", ""))[:500].encode())
    return h.hexdigest()


def _extract_edition(iso_ref: str) -> str | None:
    """Extract the year from an ISO reference string. 'ISO 9001:2015' → '2015'."""
    m = _EDITION_RE.search(iso_ref)
    return m.group(1) if m else None


def _clean_title(title: str) -> str:
    """Collapse whitespace in an RSS entry title."""
    return re.sub(r"\s+", " ", title).strip()


def _classify_event(entry: Any) -> EventType:
    """
    Determine the lifecycle EventType from RSS entry text.

    Scans title + summary for known ISO lifecycle keywords.
    Falls back to EventType.updated if no keyword matches.
    """
    text = (
        str(entry.get("title", "")) + " " + str(entry.get("summary", ""))
    ).lower()
    if any(kw in text for kw in _WITHDRAWN_KW):
        return EventType.withdrawn
    if any(kw in text for kw in _REPLACED_KW):
        return EventType.replaced
    if any(kw in text for kw in _AMENDED_KW):
        return EventType.amended
    return EventType.updated


def _event_to_status(event: EventType, current: StandardStatus) -> StandardStatus:
    """Map a change EventType to the new StandardStatus, preserving current if unknown."""
    return {
        EventType.withdrawn: StandardStatus.withdrawn,
        EventType.replaced: StandardStatus.replaced,
        EventType.amended: StandardStatus.amended,
        EventType.updated: StandardStatus.revised,
    }.get(event, current)


# ─────────────────────────────────────────────────────────────────────────────
# Entry processing
# ─────────────────────────────────────────────────────────────────────────────
async def _process_entry(entry: Any, feed: RssFeed, session: Any) -> str:
    """
    Process one RSS entry against the standards database.

    Performs upsert + history append inside the caller's transaction.
    Returns 'new' | 'updated' | 'skipped'.
    """
    # 1. Extract ISO reference from entry title + summary
    entry_text = f"{entry.get('title', '')} {entry.get('summary', '')}"
    iso_ref = extract_iso_reference(entry_text)
    if not iso_ref:
        return "skipped"

    content_hash = compute_content_hash(entry)

    # 2. Look up existing standard
    result = await session.execute(
        select(Standard).where(Standard.iso_reference == iso_ref)
    )
    standard = result.scalar_one_or_none()

    if standard is None:
        # ── New standard discovered ──────────────────────────────────────────
        title = _clean_title(entry.get("title") or iso_ref)
        edition = _extract_edition(iso_ref)

        standard = Standard(
            iso_reference=iso_ref,
            title=title,
            edition=edition,
            tc_committee=feed.tc_committee,
            status=StandardStatus.active,
            source_feed_id=feed.id,
            external_url=entry.get("link") or None,
            content_hash=content_hash,
        )
        session.add(standard)
        await session.flush()  # assign UUID before FK in history row

        history = StandardHistory(
            standard_id=standard.id,
            event_type=EventType.new,
            old_value=None,
            new_value={
                "iso_reference": iso_ref,
                "title": title,
                "edition": edition,
                "status": StandardStatus.active.value,
                "source_feed_id": str(feed.id),
            },
            source=EventSource.rss,
        )
        session.add(history)

        log.info("standard_discovered", iso_reference=iso_ref, feed_id=str(feed.id))
        return "new"

    # 3. No change — content hash matches
    if standard.content_hash == content_hash:
        return "skipped"

    # ── Change detected ──────────────────────────────────────────────────────
    event_type = _classify_event(entry)
    new_status = _event_to_status(event_type, standard.status)

    old_snapshot: dict = {
        "title": standard.title,
        "edition": standard.edition,
        "status": standard.status.value if standard.status else None,
        "content_hash": standard.content_hash,
    }

    standard.title = _clean_title(entry.get("title") or standard.title)
    standard.edition = _extract_edition(iso_ref) or standard.edition
    standard.status = new_status
    standard.content_hash = content_hash
    if not standard.external_url and entry.get("link"):
        standard.external_url = entry.get("link")

    new_snapshot: dict = {
        "title": standard.title,
        "edition": standard.edition,
        "status": standard.status.value if standard.status else None,
        "content_hash": content_hash,
    }

    history = StandardHistory(
        standard_id=standard.id,
        event_type=event_type,
        old_value=old_snapshot,
        new_value=new_snapshot,
        source=EventSource.rss,
    )
    session.add(history)

    log.info(
        "standard_updated",
        iso_reference=iso_ref,
        event_type=event_type.value,
        feed_id=str(feed.id),
    )
    return "updated"


# ─────────────────────────────────────────────────────────────────────────────
# Async core implementations (called via asyncio.run from sync Celery tasks)
# ─────────────────────────────────────────────────────────────────────────────
async def _poll_feed_async(feed_id: str) -> dict:
    """Full async implementation of the poll_feed business logic."""
    from app.database import async_session_factory  # deferred to break circular imports

    async with async_session_factory() as session:
        # Load feed
        result = await session.execute(
            select(RssFeed).where(RssFeed.id == feed_id)
        )
        feed = result.scalar_one_or_none()

        if feed is None:
            log.error("poll_feed_not_found", feed_id=feed_id)
            return {"status": "error", "reason": "feed_not_found", "feed_id": feed_id}

        if not feed.is_enabled:
            log.info("poll_feed_disabled", feed_id=feed_id)
            return {"status": "skipped", "reason": "feed_disabled", "feed_id": feed_id}

        # Fetch RSS feed
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "ISTS/1.0 (ISO Standards Tracker)"},
        ) as client:
            response = await client.get(feed.url)
            response.raise_for_status()
            raw_content = response.text

        # Parse (synchronous — feedparser has no async variant; it's fast)
        parsed = feedparser.parse(raw_content)

        if parsed.bozo and not parsed.entries:
            raise ValueError(
                f"RSS parse failure for '{feed.url}': {parsed.bozo_exception}"
            )

        log.info(
            "feed_fetched",
            feed_id=feed_id,
            entry_count=len(parsed.entries),
            feed_title=parsed.feed.get("title", ""),
        )

        new_count = 0
        updated_count = 0
        skipped_count = 0

        for entry in parsed.entries:
            try:
                outcome = await _process_entry(entry, feed, session)
            except Exception as exc:
                log.warning(
                    "entry_processing_error",
                    entry_title=entry.get("title", "?"),
                    error=str(exc),
                )
                skipped_count += 1
                continue

            if outcome == "new":
                new_count += 1
            elif outcome == "updated":
                updated_count += 1
            else:
                skipped_count += 1

        # Update feed poll-status fields
        feed.last_polled_at = datetime.now(timezone.utc)
        feed.last_poll_status = PollStatus.ok
        feed.failure_count = 0

        await session.commit()

    summary = {
        "status": "ok",
        "feed_id": feed_id,
        "new": new_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "total_entries": len(parsed.entries),
    }
    log.info("poll_feed_complete", **summary)
    return summary


async def _update_feed_on_failure(
    feed_id: str,
    failure_count: int,
    is_final: bool = False,
) -> None:
    """
    Persist feed failure state in its own session/transaction.

    Called from the exception handler in poll_feed() AFTER the main
    session has been abandoned due to the error.
    """
    from app.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(RssFeed).where(RssFeed.id == feed_id)
        )
        feed = result.scalar_one_or_none()
        if feed is not None:
            feed.failure_count = failure_count
            feed.last_poll_status = PollStatus.failed
            if is_final:
                feed.last_polled_at = datetime.now(timezone.utc)
            await session.commit()

    if is_final:
        log.error(
            "feed_poll_permanently_failed",
            feed_id=feed_id,
            failure_count=failure_count,
            action_required=(
                "Admin: check feed URL reachability and RSS format, "
                "then re-enable via PATCH /feeds/{id}."
            ),
        )


async def _poll_all_feeds_async() -> dict:
    """Async implementation of poll_all_feeds."""
    from app.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(RssFeed.id).where(RssFeed.is_enabled == True)  # noqa: E712
        )
        feed_ids = [str(row[0]) for row in result.all()]

    for fid in feed_ids:
        poll_feed.delay(fid)

    log.info("poll_all_feeds_dispatched", count=len(feed_ids))
    return {"status": "dispatched", "feed_count": len(feed_ids)}


# ─────────────────────────────────────────────────────────────────────────────
# Celery task definitions
# ─────────────────────────────────────────────────────────────────────────────
@celery.task(
    name="app.tasks.feeds.poll_feed",
    queue="feeds",
    bind=True,
    max_retries=3,
    acks_late=True,
)
def poll_feed(self, feed_id: str) -> dict:  # type: ignore[no-untyped-def]
    """
    Poll a single RSS feed, extract ISO standard references, and diff against DB.

    Args:
        feed_id: UUID string of the rss_feeds row to poll.

    Retry schedule (PRD §8.3):
        retries=0 → countdown=60 s
        retries=1 → countdown=120 s
        retries=2 → countdown=240 s
        retries=3 → permanently failed (max_retries exceeded)
    """
    log.info("poll_feed_starting", feed_id=feed_id, attempt=self.request.retries + 1)

    try:
        return asyncio.run(_poll_feed_async(feed_id))

    except Exception as exc:
        retries = self.request.retries
        is_final = retries >= self.max_retries

        # Persist failure state in a fresh session — the main session is gone
        asyncio.run(
            _update_feed_on_failure(
                feed_id,
                failure_count=retries + 1,
                is_final=is_final,
            )
        )

        if is_final:
            log.error(
                "poll_feed_max_retries_exceeded",
                feed_id=feed_id,
                retries=retries,
                error=str(exc),
            )
            return {
                "status": "permanently_failed",
                "feed_id": feed_id,
                "error": str(exc),
            }

        # Exponential backoff: 60 → 120 → 240 s
        countdown = 60 * (2 ** retries)
        log.warning(
            "poll_feed_retrying",
            feed_id=feed_id,
            error=str(exc),
            retry_number=retries + 1,
            countdown_seconds=countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)


@celery.task(
    name="app.tasks.feeds.poll_all_feeds",
    queue="feeds",
)
def poll_all_feeds() -> dict:  # type: ignore[no-untyped-def]
    """
    Fan-out dispatcher: query all enabled feeds and dispatch poll_feed for each.

    Intended to be triggered by Celery Beat on a global fallback schedule
    (e.g. every hour) or manually via the admin panel.
    """
    return asyncio.run(_poll_all_feeds_async())
