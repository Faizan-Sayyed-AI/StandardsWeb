"""
Celery tasks: feeds queue.

Full implementation with:
  - rss2json.com API fetch backend (bypasses ISO.org Cloudflare Managed Challenge)
  - Tag-based ISO entry parsing (handles all prefix variants)
  - Full 36-entry ISO stage code → StandardStatus mapping
  - Stage name extraction from _STAGE_NAME_MAP
  - published_date from RSS pubDate field
  - Amendment/corrigendum status override (/AMD, /Cor → amended)
  - TC committee extracted directly from RSS description field

Tasks:
  poll_feed(feed_id)  — Fetch, parse, diff and persist one feed
  poll_all_feeds()    — Fan-out dispatcher for all enabled feeds (Beat entry)
"""

import asyncio
import hashlib
import re
import time
from datetime import date, datetime, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import select

from app.celery_app import celery
from app.models.rss_feed import PollStatus, RssFeed
from app.models.standard import Standard, StandardStatus
from app.models.standard_history import EventSource, EventType, StandardHistory

log = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ISO Reference Pattern — anchored to START of title string
#
# Handles all prefix variants found in real ISO RSS feeds:
#   ISO, ISO/TS, ISO/TR, ISO/WD, ISO/AWI, ISO/CD, ISO/NP, ISO/PAS
#   IEC, IEC/TR, IEC/CD, IEC/AWI, IEC/TS
#   IEEE, ISO/IEC, ISO/IEC/IEEE
#   Combinations: ISO/WD TS, IEC/CD TS, etc.
#   Amendments: ISO 15223-1:2021/Amd 1:2025
#   Corrigenda: IEC 80369-5:2016/Cor 2:2021
# ─────────────────────────────────────────────────────────────────────────────
_REFERENCE_RE = re.compile(
    r"^"
    r"("
    r"(?:ISO|IEC|IEEE)"
    r"(?:/(?:IEC|IEEE|TS|TR|WD|AWI|CD|NP|PAS|GUIDE))*"
    r"(?:\s+(?:TS|TR|WD|AWI|CD|NP|PAS|GUIDE))?"
    r")"
    r"\s+"
    r"("
    r"\d+(?:[.\-]\d+)*"
    r"(?::\d{4})?"
    r"(?:/(?:Amd|Cor|DAmd|DCor)\s*\d+(?::\d{4})?)?"
    r")",
    re.IGNORECASE,
)

_EDITION_RE = re.compile(r":(\d{4})\b")

# ─────────────────────────────────────────────────────────────────────────────
# Full ISO stage code → StandardStatus mapping (all 36 defined stage codes)
# ─────────────────────────────────────────────────────────────────────────────
_STAGE_STATUS_MAP: dict[str, StandardStatus] = {
    "10.00": StandardStatus.under_review,
    "10.99": StandardStatus.under_review,
    "20.00": StandardStatus.under_review,
    "20.20": StandardStatus.under_review,
    "20.60": StandardStatus.under_review,
    "20.98": StandardStatus.withdrawn,
    "20.99": StandardStatus.under_review,
    "30.00": StandardStatus.under_review,
    "30.20": StandardStatus.under_review,
    "30.60": StandardStatus.under_review,
    "30.92": StandardStatus.under_review,
    "30.98": StandardStatus.withdrawn,
    "30.99": StandardStatus.under_review,
    "40.00": StandardStatus.under_review,
    "40.20": StandardStatus.under_review,
    "40.60": StandardStatus.under_review,
    "40.92": StandardStatus.under_review,
    "40.98": StandardStatus.withdrawn,
    "40.99": StandardStatus.under_review,
    "50.00": StandardStatus.under_review,
    "50.20": StandardStatus.under_review,
    "50.60": StandardStatus.under_review,
    "50.92": StandardStatus.under_review,
    "50.98": StandardStatus.withdrawn,
    "50.99": StandardStatus.under_review,
    "60.00": StandardStatus.active,
    "60.60": StandardStatus.active,
    "90.00": StandardStatus.active,
    "90.20": StandardStatus.active,
    "90.60": StandardStatus.active,
    "90.92": StandardStatus.active,
    "90.93": StandardStatus.active,
    "90.99": StandardStatus.withdrawn,
    "95.00": StandardStatus.withdrawn,
    "95.20": StandardStatus.withdrawn,
    "95.60": StandardStatus.withdrawn,
    "95.92": StandardStatus.active,
    "95.99": StandardStatus.withdrawn,
}

# ─────────────────────────────────────────────────────────────────────────────
# Full ISO stage code → Stage name mapping (all 36 defined stage codes)
# ─────────────────────────────────────────────────────────────────────────────
_STAGE_NAME_MAP: dict[str, str] = {
    "10.00": "Preliminary work item registered",
    "10.99": "New work item approved",
    "20.00": "Working draft (WD) registered",
    "20.20": "Working draft study initiated",
    "20.60": "Close of comment period",
    "20.98": "Project deleted",
    "20.99": "WD approved for registration as CD",
    "30.00": "Committee draft (CD) registered",
    "30.20": "CD study / ballot initiated",
    "30.60": "Close of voting",
    "30.92": "CD referred back to working group",
    "30.98": "Project deleted",
    "30.99": "CD approved for registration as DIS",
    "40.00": "DIS registered",
    "40.20": "DIS ballot initiated",
    "40.60": "Close of voting",
    "40.92": "DIS referred back to TC",
    "40.98": "Project deleted",
    "40.99": "DIS approved for registration as FDIS",
    "50.00": "FDIS registered",
    "50.20": "FDIS ballot initiated",
    "50.60": "Close of voting — FDIS",
    "50.92": "FDIS referred back to TC",
    "50.98": "Project deleted",
    "50.99": "FDIS approved for publication",
    "60.00": "International Standard under publication",
    "60.60": "International Standard published",
    "90.00": "Review initiated",
    "90.20": "Under periodical review",
    "90.60": "Close of review",
    "90.92": "International Standard to be revised",
    "90.93": "International Standard confirmed",
    "90.99": "Withdrawal approved",
    "95.00": "Withdrawal initiated",
    "95.20": "Withdrawal ballot initiated",
    "95.60": "Close of voting — withdrawal",
    "95.92": "Decision not to withdraw",
    "95.99": "Withdrawal of International Standard",
}


def _map_stage_to_status(stage: str | None) -> StandardStatus:
    """Map an ISO stage code to StandardStatus."""
    if not stage:
        return StandardStatus.active
    if stage in _STAGE_STATUS_MAP:
        return _STAGE_STATUS_MAP[stage]
    try:
        major = int(stage.split(".")[0])
    except (ValueError, IndexError):
        return StandardStatus.active
    if major == 95:
        return StandardStatus.withdrawn
    if major in (60, 90):
        return StandardStatus.active
    if major in (10, 20, 30, 40, 50):
        return StandardStatus.under_review
    return StandardStatus.active


# ─────────────────────────────────────────────────────────────────────────────
# Tag-based RSS entry parser
# ─────────────────────────────────────────────────────────────────────────────
def parse_iso_entry(entry: Any) -> dict | None:
    """
    Parse an ISO RSS entry using tag content rather than free-text regex.

    Returns a dict with keys:
      iso_reference, title, edition, stage, stage_name, status,
      tc_committee, published_date, external_url, event_type_hint

    Returns None if the entry has no recognisable ISO reference.
    """
    raw_title = entry.get("title", "").strip()
    description = entry.get("summary", entry.get("description", "")).strip()
    link = entry.get("link", "") or entry.get("id", "")

    # ── Step 1: Extract ISO reference from START of title ────────────────────
    match = _REFERENCE_RE.match(raw_title)
    if not match:
        log.debug("entry_no_iso_reference", title=raw_title[:80])
        return None

    org_part = match.group(1).strip()
    num_part = match.group(2).strip()
    iso_reference = f"{org_part} {num_part}".upper()

    # ── Step 2: Extract clean title ──────────────────────────────────────────
    remainder = raw_title[match.end():].strip()
    for sep in (" - ", "- ", " — ", "— ", "—", " – ", "– ", "–"):
        if remainder.startswith(sep):
            remainder = remainder[len(sep):]
            break
    title = re.sub(r"\s+", " ", remainder).strip() or raw_title

    # ── Step 3: Parse description field ─────────────────────────────────────
    stage: str | None = None
    tc_committee: str | None = None

    if "stage " in description:
        after_stage = description.split("stage ")[1]
        stage_candidate = after_stage.split(" ")[0].rstrip(",")
        if re.match(r"^\d{2}\.\d{2}$", stage_candidate):
            stage = stage_candidate

    if "TC/SC: " in description:
        after_tc = description.split("TC/SC: ")[1]
        tc_committee = after_tc.split(",")[0].strip()

    # ── Step 4: Map stage to status and name ─────────────────────────────────
    status = _map_stage_to_status(stage)
    stage_name = _STAGE_NAME_MAP.get(stage) if stage else None

    # ── Step 5: Parse published_date from feedparser's published_parsed ──────
    published_date: date | None = None
    published_parsed = entry.get("published_parsed")
    if published_parsed:
        try:
            published_date = date(
                published_parsed.tm_year,
                published_parsed.tm_mon,
                published_parsed.tm_mday,
            )
        except (AttributeError, ValueError):
            published_date = None

    # ── Step 6: Determine event_type hint ────────────────────────────────────
    ref_upper = iso_reference.upper()
    event_type_hint: str = "new"

    if "/AMD" in ref_upper or "/DAMD" in ref_upper:
        event_type_hint = "amended"
    elif "/COR" in ref_upper or "/DCOR" in ref_upper:
        event_type_hint = "amended"
    elif status == StandardStatus.withdrawn:
        event_type_hint = "withdrawn"

    # ── Step 7: Extract edition year ─────────────────────────────────────────
    edition_match = _EDITION_RE.search(iso_reference)
    edition = edition_match.group(1) if edition_match else None

    return {
        "iso_reference": iso_reference,
        "title": title,
        "edition": edition,
        "stage": stage,
        "stage_name": stage_name,
        "status": status,
        "tc_committee": tc_committee,
        "published_date": published_date,
        "external_url": link or None,
        "event_type_hint": event_type_hint,
    }


def compute_content_hash(entry: Any) -> str:
    """SHA-256 fingerprint of an RSS entry."""
    h = hashlib.sha256()
    for field in ("title", "link", "published", "updated"):
        h.update(str(entry.get(field, "")).encode())
    h.update(str(entry.get("summary", ""))[:500].encode())
    return h.hexdigest()


def _classify_event_from_hint(
    hint: str,
    entry: Any,
    current_status: StandardStatus,
    new_status: StandardStatus,
) -> EventType:
    """Determine EventType for an update."""
    if hint == "amended":
        return EventType.amended
    if new_status == StandardStatus.withdrawn and current_status != StandardStatus.withdrawn:
        return EventType.withdrawn
    text = (
        str(entry.get("title", "")) + " " + str(entry.get("summary", ""))
    ).lower()
    if any(kw in text for kw in ("replaced", "superseded")):
        return EventType.replaced
    if any(kw in text for kw in ("withdrawn", "cancelled", "obsolete")):
        return EventType.withdrawn
    if any(kw in text for kw in ("amended", "amendment", "corrigendum")):
        return EventType.amended
    return EventType.updated


# ─────────────────────────────────────────────────────────────────────────────
# Entry processing
# ─────────────────────────────────────────────────────────────────────────────
async def _process_entry(entry: Any, feed: RssFeed, session: Any) -> tuple[str, str | None]:
    """Process one RSS entry against the standards database."""
    parsed = parse_iso_entry(entry)
    if parsed is None:
        return "skipped", None

    iso_ref = parsed["iso_reference"]
    content_hash = compute_content_hash(entry)
    tc_committee = parsed["tc_committee"] or feed.tc_committee

    result = await session.execute(
        select(Standard).where(Standard.iso_reference == iso_ref)
    )
    standard = result.scalar_one_or_none()

    # ── Amendment/corrigendum status override ────────────────────────────────
    new_status = parsed["status"]
    if parsed["event_type_hint"] == "amended":
        new_status = StandardStatus.amended

    if standard is None:
        # ── New standard discovered ──────────────────────────────────────────
        standard = Standard(
            iso_reference=iso_ref,
            title=parsed["title"],
            edition=parsed["edition"],
            tc_committee=tc_committee,
            status=new_status,
            source_feed_id=feed.id,
            external_url=parsed["external_url"],
            content_hash=content_hash,
            stage_code=parsed["stage"],
            stage_name=parsed["stage_name"],
            published_date=parsed["published_date"],
        )
        session.add(standard)
        await session.flush()

        history = StandardHistory(
            standard_id=standard.id,
            event_type=EventType.new,
            old_value=None,
            new_value={
                "iso_reference": iso_ref,
                "title": parsed["title"],
                "edition": parsed["edition"],
                "stage": parsed["stage"],
                "stage_name": parsed["stage_name"],
                "status": new_status.value,
                "tc_committee": tc_committee,
                "published_date": str(parsed["published_date"]) if parsed["published_date"] else None,
                "source_feed_id": str(feed.id),
            },
            source=EventSource.rss,
        )
        session.add(history)

        log.info(
            "standard_discovered",
            iso_reference=iso_ref,
            stage=parsed["stage"],
            stage_name=parsed["stage_name"],
            status=new_status.value,
            tc_committee=tc_committee,
            feed_id=str(feed.id),
        )
        return "new", str(standard.id)

    # No change
    if standard.content_hash == content_hash:
        return "skipped", None

    # ── Change detected ──────────────────────────────────────────────────────
    event_type = _classify_event_from_hint(
        parsed["event_type_hint"],
        entry,
        standard.status,
        new_status,
    )

    old_snapshot: dict = {
        "title": standard.title,
        "edition": standard.edition,
        "status": standard.status.value if standard.status else None,
        "tc_committee": standard.tc_committee,
        "stage": standard.stage_code,
        "stage_name": standard.stage_name,
        "published_date": str(standard.published_date) if standard.published_date else None,
        "content_hash": standard.content_hash,
    }

    standard.title = parsed["title"]
    standard.edition = parsed["edition"] or standard.edition
    standard.status = new_status
    standard.tc_committee = tc_committee
    standard.content_hash = content_hash
    standard.stage_code = parsed["stage"]
    standard.stage_name = parsed["stage_name"]
    standard.published_date = parsed["published_date"]
    if not standard.external_url and parsed["external_url"]:
        standard.external_url = parsed["external_url"]

    new_snapshot: dict = {
        "title": standard.title,
        "edition": standard.edition,
        "status": standard.status.value if standard.status else None,
        "tc_committee": standard.tc_committee,
        "stage": standard.stage_code,
        "stage_name": standard.stage_name,
        "published_date": str(standard.published_date) if standard.published_date else None,
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
        old_status=old_snapshot["status"],
        new_status=new_status.value,
        stage=parsed["stage"],
        feed_id=str(feed.id),
    )
    return event_type.value, str(standard.id)


# ─────────────────────────────────────────────────────────────────────────────
# Async core implementations
# ─────────────────────────────────────────────────────────────────────────────
async def _poll_feed_async(feed_id: str) -> dict:
    """Full async implementation of the poll_feed business logic."""
    from app.database import async_session_factory
    from app.config import settings

    async with async_session_factory() as session:
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

        # Fetch via rss2json API (bypasses ISO.org Cloudflare Managed Challenge)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.rss2json.com/v1/api.json",
                params={
                    "rss_url": feed.url,
                    "api_key": settings.RSS2JSON_API_KEY,
                    "count": 200,
                },
            )
            response.raise_for_status()
            payload = response.json()

        if payload.get("status") != "ok":
            raise ValueError(
                f"rss2json returned non-ok status for '{feed.url}': "
                f"{payload.get('message', 'unknown error')}"
            )

        raw_items = payload.get("items", [])

        # Convert rss2json items to feedparser-compatible dicts so that
        # parse_iso_entry() and compute_content_hash() remain unmodified.
        entries = []
        for item in raw_items:
            pub_date_str = item.get("pubDate", "")
            published_parsed = None
            if pub_date_str:
                try:
                    published_parsed = time.strptime(pub_date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    published_parsed = None

            entries.append({
                "title": item.get("title", ""),
                "summary": item.get("description", ""),
                "link": item.get("link", ""),
                "id": item.get("link", ""),
                "published": pub_date_str,
                "updated": pub_date_str,
                "published_parsed": published_parsed,
            })

        log.info(
            "feed_fetched",
            feed_id=feed_id,
            entry_count=len(entries),
        )

        new_count = 0
        updated_count = 0
        skipped_count = 0
        notifications_to_send = []

        for entry in entries:
            try:
                outcome, std_id = await _process_entry(entry, feed, session)
            except Exception as exc:
                log.warning(
                    "entry_processing_error",
                    entry_title=entry.get("title", "?")[:80],
                    error=str(exc),
                )
                skipped_count += 1
                continue

            if outcome == "skipped":
                skipped_count += 1
            else:
                if outcome == "new":
                    new_count += 1
                else:
                    updated_count += 1
                notifications_to_send.append((outcome, std_id))

        feed.last_polled_at = datetime.now(timezone.utc)
        feed.last_poll_status = PollStatus.ok
        feed.failure_count = 0

        await session.commit()

        from app.tasks.notifications import send_bulk_notification
        for evt_type, std_id in notifications_to_send:
            if std_id:
                send_bulk_notification.delay({
                    "event_type": evt_type,
                    "standard_id": std_id,
                })

    summary = {
        "status": "ok",
        "feed_id": feed_id,
        "new": new_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "total_entries": len(entries),
    }
    log.info("poll_feed_complete", **summary)
    return summary


async def _update_feed_on_failure(
    feed_id: str,
    failure_count: int,
    is_final: bool = False,
) -> None:
    """Persist feed failure state in its own session/transaction."""
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
        )


async def _notify_feed_failure_async(feed_id: str, error_msg: str) -> None:
    """Create critical in-app notification for admins + send email to mapped lists."""
    import uuid
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from app.database import async_session_factory
    from app.models.user import User, UserRole
    from app.models.notification import Notification, NotificationSeverity
    from app.models.distribution_list import DistributionListMember
    from app.models.notification_mapping import NotificationTriggerMapping
    from app.core.smtp_config import get_active_smtp_settings
    from app.services.audit_service import write_audit_log

    async with async_session_factory() as db:
        feed = await db.get(RssFeed, uuid.UUID(feed_id))
        if not feed:
            return

        res = await db.execute(
            select(User).where(User.is_active == True, User.role == UserRole.admin)
        )
        admins = res.scalars().all()

        title = f"Feed Poll Failed: {feed.name}"
        body = (
            f"Feed poll failed consecutively and has been marked as failed.\n"
            f"URL: {feed.url}\nError: {error_msg}"
        )

        for admin in admins:
            db.add(Notification(
                user_id=admin.id,
                event_type="status_change",
                severity=NotificationSeverity.critical,
                title=title,
                body=body,
                is_read=False,
            ))
        await db.flush()

        stmt = (
            select(DistributionListMember.email, DistributionListMember.name)
            .join(
                NotificationTriggerMapping,
                NotificationTriggerMapping.list_id == DistributionListMember.list_id,
            )
            .where(
                NotificationTriggerMapping.event_type == "status_change",
                DistributionListMember.is_active == True,
            )
        )
        members = (await db.execute(stmt)).all()
        recipients = {m_email: (m_name or m_email) for m_email, m_name in members}

        if recipients:
            smtp_settings = await get_active_smtp_settings(db)
            client = aiosmtplib.SMTP(
                hostname=smtp_settings["SMTP_HOST"],
                port=smtp_settings["SMTP_PORT"],
                use_tls=smtp_settings["SMTP_USE_TLS"],
            )
            await client.connect()
            if smtp_settings["SMTP_USER"] and smtp_settings["SMTP_PASSWORD"]:
                await client.login(smtp_settings["SMTP_USER"], smtp_settings["SMTP_PASSWORD"])
            try:
                for email, name in recipients.items():
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = f"[ISTS] CRITICAL: {title}"
                    msg["From"] = smtp_settings["SMTP_FROM_ADDRESS"]
                    msg["To"] = email
                    msg.attach(MIMEText(f"Hello {name},\n\n{body}\n\n--\nISTS", "plain"))
                    msg.attach(MIMEText(
                        f"<html><body><h2 style='color:#ef4444'>{title}</h2>"
                        f"<p>{body}</p></body></html>",
                        "html",
                    ))
                    await client.send_message(msg)
            finally:
                await client.quit()

        await write_audit_log(
            db,
            action="feed.poll_failed_alert",
            resource_type="rss_feed",
            actor_id=None,
            resource_id=feed.id,
            payload={"error": error_msg, "recipients_emailed": list(recipients.keys())},
        )
        await db.commit()


async def _poll_all_feeds_async() -> dict:
    """Async implementation of poll_all_feeds."""
    from app.database import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(RssFeed.id).where(RssFeed.is_enabled == True)
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
def poll_feed(self, feed_id: str) -> dict:
    """Poll a single RSS feed, parse ISO entries, and diff against DB."""
    log.info("poll_feed_starting", feed_id=feed_id, attempt=self.request.retries + 1)

    try:
        return asyncio.run(_poll_feed_async(feed_id))

    except Exception as exc:
        retries = self.request.retries
        is_final = retries >= self.max_retries

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
            try:
                asyncio.run(_notify_feed_failure_async(feed_id, str(exc)))
            except Exception as notify_exc:
                log.exception(
                    "failed_to_send_feed_failure_notification",
                    error=str(notify_exc),
                )
            return {
                "status": "permanently_failed",
                "feed_id": feed_id,
                "error": str(exc),
            }

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
def poll_all_feeds() -> dict:
    """Fan-out dispatcher: query all enabled feeds and dispatch poll_feed for each."""
    return asyncio.run(_poll_all_feeds_async())