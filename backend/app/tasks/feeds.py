"""
Celery tasks: feeds queue.

M2 full implementation + feed parser fix (pre-M6):
  - Tag-based ISO entry parsing (replaces regex-only approach)
  - Full 36-entry ISO stage code → StandardStatus mapping
  - TC committee extracted directly from RSS description field
  - All ISO prefix variants handled: ISO/TS, ISO/TR, ISO/WD, ISO/AWI,
    IEC/CD, IEC/TR, IEC/AWI, ISO/IEC, ISO/IEC/IEEE, etc.

Tasks:
  poll_feed(feed_id)  — Fetch, parse, diff and persist one feed
  poll_all_feeds()    — Fan-out dispatcher for all enabled feeds (Beat entry)

poll_feed flow (PRD §8.3):
  1. Load feed record from DB; skip if disabled.
  2. Fetch RSS XML via httpx (10 s timeout, follow redirects).
  3. Parse with feedparser.
  4. For each entry:
       a. Parse ISO reference + title + stage + tc_committee from tags.
       b. Compute SHA-256 content hash.
       c. Query standards table by iso_reference.
       d. INSERT new standard + history row (event_type=new) if not found.
       e. UPDATE standard + append history row if content_hash differs.
       f. Skip if hash unchanged (no-op).
  5. Update rss_feeds: last_polled_at, last_poll_status=ok, failure_count=0.
  6. Commit.

Retry policy (exponential backoff — PRD §8.3 step 9):
  Attempt 1 fails → retry after  60 s
  Attempt 2 fails → retry after 120 s
  Attempt 3 fails → retry after 240 s
  Attempt 4 fails → mark permanently failed, log critical alert
"""

import asyncio
import hashlib
import re
from datetime import date, datetime, timezone
import time
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
# ISO Reference Pattern — anchored to START of title string
#
# Handles all prefix variants found in real ISO RSS feeds:
#   ISO, ISO/TS, ISO/TR, ISO/WD, ISO/AWI, ISO/CD, ISO/NP, ISO/PAS
#   IEC, IEC/TR, IEC/CD, IEC/AWI, IEC/TS
#   IEEE
#   ISO/IEC, ISO/IEC/IEEE
#   Combinations: ISO/WD TS, IEC/CD TS, etc.
#
# Also handles amendment/corrigendum suffixes:
#   ISO 15223-1:2021/Amd 1:2025
#   IEC 80369-5:2016/Cor 2:2021
# ─────────────────────────────────────────────────────────────────────────────
_REFERENCE_RE = re.compile(
    r"^"
    r"("
    r"(?:ISO|IEC|IEEE)"                             # base org
    r"(?:/(?:IEC|IEEE|TS|TR|WD|AWI|CD|NP|PAS|GUIDE))*"  # optional slash-suffixes
    r"(?:\s+(?:TS|TR|WD|AWI|CD|NP|PAS|GUIDE))?"    # optional space-suffixes e.g. "ISO/WD TS"
    r")"                                            # end org group
    r"\s+"
    r"("
    r"\d+(?:[.\-]\d+)*"                             # main number + optional parts
    r"(?::\d{4})?"                                  # optional year :2021
    r"(?:/(?:Amd|Cor|DAmd|DCor)\s*\d+(?::\d{4})?)?"  # optional amendment/corrigendum
    r")",
    re.IGNORECASE,
)

_EDITION_RE = re.compile(r":(\d{4})\b")

# ─────────────────────────────────────────────────────────────────────────────
# Full ISO stage code → StandardStatus mapping (all 36 defined stage codes)
# Source: ISO/IEC Directives, Supplement — Procedures specific to ISO
# ─────────────────────────────────────────────────────────────────────────────
_STAGE_STATUS_MAP: dict[str, StandardStatus] = {
    # Preliminary / New work
    "10.00": StandardStatus.under_review,
    "10.99": StandardStatus.under_review,
    # Working Draft
    "20.00": StandardStatus.under_review,
    "20.20": StandardStatus.under_review,
    "20.60": StandardStatus.under_review,
    "20.98": StandardStatus.withdrawn,    # Project deleted at WD stage
    "20.99": StandardStatus.under_review,
    # Committee Draft
    "30.00": StandardStatus.under_review,
    "30.20": StandardStatus.under_review,
    "30.60": StandardStatus.under_review,
    "30.92": StandardStatus.under_review,
    "30.98": StandardStatus.withdrawn,    # Project deleted at CD stage
    "30.99": StandardStatus.under_review,
    # DIS (Draft International Standard)
    "40.00": StandardStatus.under_review,
    "40.20": StandardStatus.under_review,
    "40.60": StandardStatus.under_review,
    "40.92": StandardStatus.under_review,
    "40.98": StandardStatus.withdrawn,    # Project deleted at DIS stage
    "40.99": StandardStatus.under_review,
    # FDIS (Final Draft International Standard)
    "50.00": StandardStatus.under_review,
    "50.20": StandardStatus.under_review,
    "50.60": StandardStatus.under_review,
    "50.92": StandardStatus.under_review,
    "50.98": StandardStatus.withdrawn,    # Project deleted at FDIS stage
    "50.99": StandardStatus.under_review,
    # Publication
    "60.00": StandardStatus.active,       # Under publication
    "60.60": StandardStatus.active,       # Published
    # Review / Confirmation
    "90.00": StandardStatus.active,
    "90.20": StandardStatus.active,       # Under periodical review
    "90.60": StandardStatus.active,
    "90.92": StandardStatus.active,       # To be revised
    "90.93": StandardStatus.active,       # Confirmed
    "90.99": StandardStatus.withdrawn,    # Withdrawal approved
    # Withdrawal
    "95.00": StandardStatus.withdrawn,
    "95.20": StandardStatus.withdrawn,
    "95.60": StandardStatus.withdrawn,
    "95.92": StandardStatus.active,       # Decision NOT to withdraw — remains active
    "95.99": StandardStatus.withdrawn,    # Officially withdrawn
}

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
    """
    Map an ISO stage code string to StandardStatus.

    Tries exact match first, then falls back to major-number heuristic.
    """
    if not stage:
        return StandardStatus.active

    # Exact match
    if stage in _STAGE_STATUS_MAP:
        return _STAGE_STATUS_MAP[stage]

    # Fallback: use major number only
    try:
        major = int(stage.split(".")[0])
    except (ValueError, IndexError):
        return StandardStatus.active

    if major == 95 or major == 20 and stage.endswith(".98"):
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
      iso_reference, title, edition, stage, status,
      tc_committee, last_change_date, external_url, event_type_hint

    Returns None if the entry has no recognisable ISO reference.

    Title format expected:
      "ISO/TS 24971-2 - Medical devices — Guidance on..."
      "ISO 80369-7:2021 - Small-bore connectors — Part 7: ..."
      "ISO 15223-1:2021/Amd 1:2025 - Medical devices — Symbols..."
      "ISO/WD TS 24971-3 - Medical devices - Guidance on..."

    Description format expected:
      "This document reached stage 90.93 on 2025-10-31, TC/SC: ISO/TC 210, ICS: 11.040.01"
    """
    raw_title = entry.get("title", "").strip()
    description = entry.get("summary", entry.get("description", "")).strip()
    link = entry.get("link", "") or entry.get("id", "")

    # ── Step 1: Extract ISO reference from START of title ────────────────────
    match = _REFERENCE_RE.match(raw_title)
    if not match:
        log.debug("entry_no_iso_reference", title=raw_title[:80])
        return None

    org_part = match.group(1).strip()       # e.g. "ISO/TS" or "ISO/WD TS" or "IEC"
    num_part = match.group(2).strip()       # e.g. "24971-2" or "80369-7:2021"
    iso_reference = f"{org_part} {num_part}".upper()

    # ── Step 2: Extract clean title (everything after reference + separator) ─
    remainder = raw_title[match.end():].strip()
    remainder = remainder.strip()
    for sep in (" - ", "- ", " — ", "— ", "—", " – ", "– ", "–"):
        if remainder.startswith(sep):
            remainder = remainder[len(sep):]
            break
    title = re.sub(r"\s+", " ", remainder).strip() or raw_title

    # ── Step 3: Parse description field ─────────────────────────────────────
    # Description: "This document reached stage 90.93 on 2025-10-31, TC/SC: ISO/TC 210"
    stage: str | None = None
    tc_committee: str | None = None
    last_change_date: str | None = None

    if "stage " in description:
        after_stage = description.split("stage ")[1]
        stage_candidate = after_stage.split(" ")[0].rstrip(",")
        # Validate it looks like a stage code e.g. "90.93"
        if re.match(r"^\d{2}\.\d{2}$", stage_candidate):
            stage = stage_candidate

    if " on " in description:
        after_on = description.split(" on ")[1]
        date_candidate = after_on.split(",")[0].strip()
        # Validate date format YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_candidate):
            last_change_date = date_candidate

    if "TC/SC: " in description:
        after_tc = description.split("TC/SC: ")[1]
        tc_committee = after_tc.split(",")[0].strip()   # "ISO/TC 210"

    # ── Step 4: Map stage to status ──────────────────────────────────────────
    status = _map_stage_to_status(stage)

    # ── Step 5: Determine event_type hint from reference + stage ─────────────
    ref_upper = iso_reference.upper()
    event_type_hint: str = "new"  # default; overridden on update

    if "/AMD" in ref_upper or "/DAMD" in ref_upper:
        event_type_hint = "amended"
    elif "/COR" in ref_upper or "/DCOR" in ref_upper:
        event_type_hint = "amended"
    elif status == StandardStatus.withdrawn:
        event_type_hint = "withdrawn"

    # ── Step 6: Extract edition year from reference ──────────────────────────
    edition_match = _EDITION_RE.search(iso_reference)
    edition = edition_match.group(1) if edition_match else None

    # ── Step 7: Parse published date ──────────────────────────────────────────
    parsed_time = entry.get("published_parsed")
    published_date = None
    if parsed_time:
        try:
            published_date = date(*parsed_time[:3])
        except (TypeError, ValueError):
            published_date = None

    return {
        "iso_reference": iso_reference,
        "title": title,
        "edition": edition,
        "stage": stage,
        "stage_name": _STAGE_NAME_MAP.get(stage) if stage else None,
        "published_date": published_date,
        "status": status,
        "tc_committee": tc_committee,
        "last_change_date": last_change_date,
        "external_url": link or None,
        "event_type_hint": event_type_hint,
    }


def compute_content_hash(entry: Any) -> str:
    """
    Compute a SHA-256 fingerprint of an RSS entry.

    Fields hashed: title, link, published, updated, summary (first 500 chars).
    A different hash on subsequent polls indicates content has changed.
    """
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
    """
    Determine EventType for an update.

    Priority:
      1. hint from parse_iso_entry (amendment/corrigendum in reference)
      2. Status transition to withdrawn
      3. Title/summary keyword scan as fallback
    """
    if hint == "amended":
        return EventType.amended

    if new_status == StandardStatus.withdrawn and current_status != StandardStatus.withdrawn:
        return EventType.withdrawn

    # Keyword fallback
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
    """
    Process one RSS entry against the standards database.

    Performs upsert + history append inside the caller's transaction.
    Returns (event_type_str, standard_id | None).
    """
    # Parse entry using tag-based approach
    parsed = parse_iso_entry(entry)
    if parsed is None:
        return "skipped", None

    iso_ref = parsed["iso_reference"]
    content_hash = compute_content_hash(entry)

    # Use tc_committee from RSS description if available, else fall back to feed setting
    tc_committee = parsed["tc_committee"] or feed.tc_committee

    # Look up existing standard
    result = await session.execute(
        select(Standard).where(Standard.iso_reference == iso_ref)
    )
    standard = result.scalar_one_or_none()

    if standard is None:
        # ── New standard discovered ──────────────────────────────────────────
        new_status = parsed["status"]
        # Amendment/corrigendum references always get amended status
        if parsed['event_type_hint'] == 'amended':
            new_status = StandardStatus.amended

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
                "published_date": parsed["published_date"].isoformat() if parsed["published_date"] else None,
                "status": new_status.value,
                "tc_committee": tc_committee,
                "source_feed_id": str(feed.id),
            },
            source=EventSource.rss,
        )
        session.add(history)

        log.info(
            "standard_discovered",
            iso_reference=iso_ref,
            stage=parsed["stage"],
            status=parsed["status"].value,
            tc_committee=tc_committee,
            feed_id=str(feed.id),
        )
        return "new", str(standard.id)

    # No change — content hash matches
    if standard.content_hash == content_hash:
        return "skipped", None

    # ── Change detected ──────────────────────────────────────────────────────
    new_status = parsed["status"]
    # Amendment/corrigendum references always get amended status
    if parsed['event_type_hint'] == 'amended':
        new_status = StandardStatus.amended

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
        "content_hash": standard.content_hash,
        "stage_code": standard.stage_code,
        "stage_name": standard.stage_name,
        "published_date": standard.published_date.isoformat() if standard.published_date else None,
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
        "stage": parsed["stage"],
        "stage_name": parsed["stage_name"],
        "published_date": parsed["published_date"].isoformat() if parsed["published_date"] else None,
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

        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Referer": "https://www.iso.org/",
            },
        ) as client:
            response = await client.get(feed.url)
            response.raise_for_status()
            raw_content = response.text

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
        notifications_to_send = []

        for entry in parsed.entries:
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
        "total_entries": len(parsed.entries),
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