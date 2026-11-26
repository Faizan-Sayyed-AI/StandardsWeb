"""
Weekly email digest service.

Flow:
  enqueue_event()      called by send_email_notification when digest mode is on
  due_slot_key()       pure: is "now" inside a send slot, and what is its key
  run_digest()         claim the slot, compile one email per recipient, send

Delivery rules:
  * Recipients come from the existing notification_trigger_mappings →
    distribution_list_members join, resolved at send time. A recipient only sees
    events for event types their list is mapped to.
  * Nothing to send → no email. The slot is still recorded, so it is not retried.
  * SMTP connect/login failure → the claim is released (queue rows returned to
    pending, run row removed) and the error re-raised, so the next hourly tick
    the same day tries again. A single recipient failing is recorded but not
    retried, so recipients who already got the email are never sent it twice.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import aiosmtplib
import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.email_digest_template import SECTION_ORDER, DigestItem, DigestSection, render_digest
from app.core.smtp_config import get_active_smtp_settings
from app.models.distribution_list import DistributionListMember
from app.models.email_digest import EmailDigestQueueItem, EmailDigestRun
from app.models.notification_mapping import NotificationTriggerMapping
from app.models.standard import Standard
from app.services.audit_service import write_audit_log

log = structlog.get_logger(__name__)

_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ── configuration helpers ────────────────────────────────────────────────────
def excluded_event_types() -> set[str]:
    return {e.strip() for e in settings.EMAIL_DIGEST_EXCLUDED_EVENT_TYPES.split(",") if e.strip()}


def due_slot_key(
    now_utc: datetime,
    *,
    days: str,
    hour: int,
    tz_name: str,
) -> str | None:
    """
    Return the slot key (local ISO date) if `now_utc` falls on a configured day at
    or after the configured hour, else None. "At or after" lets an hourly tick
    catch up for the rest of the day if the server missed the exact hour.
    """
    wanted = {d.strip().lower()[:3] for d in days.split(",") if d.strip()}
    local = now_utc.astimezone(ZoneInfo(tz_name))
    if _WEEKDAYS[local.weekday()] in wanted and local.hour >= hour:
        return local.date().isoformat()
    return None


# ── queueing ─────────────────────────────────────────────────────────────────
async def enqueue_event(
    db: AsyncSession,
    *,
    event_type: str,
    standard_id: uuid.UUID,
    document_id: uuid.UUID | None = None,
    triggered_by_id: uuid.UUID | None = None,
) -> None:
    db.add(
        EmailDigestQueueItem(
            event_type=event_type,
            standard_id=standard_id,
            document_id=document_id,
            triggered_by_id=triggered_by_id,
        )
    )
    await db.flush()


# ── digest run ───────────────────────────────────────────────────────────────
async def _release_claim(db: AsyncSession, run_id: uuid.UUID) -> None:
    await db.execute(
        update(EmailDigestQueueItem)
        .where(EmailDigestQueueItem.digest_run_id == run_id)
        .values(digest_run_id=None)
    )
    await db.execute(delete(EmailDigestRun).where(EmailDigestRun.id == run_id))
    await db.commit()


async def run_digest(db: AsyncSession, slot_key: str) -> dict:
    """Claim `slot_key` and send its digest. Safe to call repeatedly."""
    # 1. Claim the slot atomically; if another tick/beat already did, stop.
    claimed = await db.execute(
        pg_insert(EmailDigestRun)
        .values(slot_key=slot_key)
        .on_conflict_do_nothing(index_elements=["slot_key"])
        .returning(EmailDigestRun.id)
    )
    run_id = claimed.scalar_one_or_none()
    if run_id is None:
        await db.rollback()
        return {"status": "skipped", "reason": "slot_already_claimed", "slot": slot_key}

    # 2. Atomically take every pending row for this run.
    taken = await db.execute(
        update(EmailDigestQueueItem)
        .where(EmailDigestQueueItem.digest_run_id.is_(None))
        .values(digest_run_id=run_id)
        .returning(
            EmailDigestQueueItem.event_type,
            EmailDigestQueueItem.standard_id,
        )
    )
    events = taken.all()
    await db.commit()  # claim + rows are now durable

    run = await db.get(EmailDigestRun, run_id)

    if not events:
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        log.info("email_digest_nothing_to_send", slot=slot_key)
        return {"status": "ok", "slot": slot_key, "sent": 0, "reason": "no_events"}

    # 3. Standards for the events, in one query.
    standard_ids = {sid for _, sid in events}
    std_rows = await db.execute(select(Standard).where(Standard.id.in_(standard_ids)))
    standards = {s.id: s for s in std_rows.scalars().all()}

    # event_type -> standard_id -> change count
    by_event: dict[str, dict[uuid.UUID, int]] = defaultdict(lambda: defaultdict(int))
    for event_type, sid in events:
        if sid in standards:
            by_event[event_type][sid] += 1

    # 4. Recipients: email -> (name, set of event types they are mapped to)
    rec_rows = await db.execute(
        select(
            DistributionListMember.email,
            DistributionListMember.name,
            NotificationTriggerMapping.event_type,
        )
        .join(
            NotificationTriggerMapping,
            NotificationTriggerMapping.list_id == DistributionListMember.list_id,
        )
        .where(
            DistributionListMember.is_active == True,  # noqa: E712
            NotificationTriggerMapping.event_type.in_(list(by_event.keys())),
        )
    )
    recipients: dict[str, tuple[str, set[str]]] = {}
    for email, name, event_type in rec_rows.all():
        entry = recipients.setdefault(email, (name or email, set()))
        entry[1].add(event_type)

    smtp = await get_active_smtp_settings(db)
    tz = ZoneInfo(settings.EMAIL_DIGEST_TIMEZONE)
    period_label = datetime.now(tz).strftime("%d %b %Y")

    success = failure = 0
    failures: list[tuple[str, str]] = []
    connection_error: str | None = None

    try:
        client = aiosmtplib.SMTP(
            hostname=smtp["SMTP_HOST"],
            port=smtp["SMTP_PORT"],
            start_tls=smtp["SMTP_USE_TLS"],
        )
        await client.connect()
        if smtp["SMTP_USER"] and smtp["SMTP_PASSWORD"]:
            await client.login(smtp["SMTP_USER"], smtp["SMTP_PASSWORD"])
        try:
            for email, (name, wanted) in recipients.items():
                sections = []
                for event_type, label in SECTION_ORDER:
                    if event_type not in wanted or event_type not in by_event:
                        continue
                    items = [
                        DigestItem(
                            standard_id=str(sid),
                            iso_reference=standards[sid].iso_reference,
                            title=standards[sid].title,
                            status=str(getattr(standards[sid].status, "value", standards[sid].status)).upper(),
                            count=count,
                        )
                        for sid, count in by_event[event_type].items()
                    ]
                    items.sort(key=lambda i: i.iso_reference)
                    sections.append(DigestSection(event_type, label, items))
                if not sections:
                    continue

                try:
                    html, text, total = render_digest(
                        recipient_name=name,
                        sections=sections,
                        frontend_url=settings.frontend_base_url,
                        period_label=period_label,
                    )
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = (
                        f"[StandardSphere] Weekly digest: {total} standard"
                        f"{'s' if total != 1 else ''} updated"
                    )
                    msg["From"] = smtp["SMTP_FROM_ADDRESS"]
                    msg["To"] = email
                    msg.attach(MIMEText(text, "plain"))
                    msg.attach(MIMEText(html, "html"))
                    await client.send_message(msg)
                    success += 1
                except Exception as e:  # noqa: BLE001 — one bad recipient must not stop the rest
                    failure += 1
                    failures.append((email, str(e)))
                    log.warning("email_digest_recipient_failed", email=email, error=str(e))
        finally:
            await client.quit()
    except Exception as exc:  # noqa: BLE001
        connection_error = str(exc)
        log.error("email_digest_connection_failed", error=connection_error)

    if connection_error and success == 0:
        # Nothing went out: hand the events back and let the next tick retry.
        await _release_claim(db, run_id)
        raise RuntimeError(f"SMTP connection/login failed: {connection_error}")

    run.finished_at = datetime.now(timezone.utc)
    run.event_count = len(events)
    run.recipient_count = success + failure
    run.success_count = success
    run.failure_count = failure
    await write_audit_log(
        db,
        action="notification.digest_sent",
        resource_type="email_digest_run",
        actor_id=None,
        resource_id=run_id,
        payload={
            "slot": slot_key,
            "events": len(events),
            "success_count": success,
            "failure_count": failure,
            "failures": failures,
        },
    )
    await db.commit()
    log.info("email_digest_sent", slot=slot_key, success=success, failure=failure)
    return {
        "status": "ok",
        "slot": slot_key,
        "events": len(events),
        "sent": success,
        "failed": failure,
    }
