"""
Celery tasks: notifications queue.

M5 implementation:
  - Real SMTP email delivery via aiosmtplib.
  - HTML templates with inline CSS.
  - In-app notification creation for active users.
  - Audit logging.
"""

import asyncio
import structlog
import uuid

from app.celery_app import celery

log = structlog.get_logger(__name__)


def get_notification_content(event_type: str, standard) -> tuple[str, str]:
    ref = standard.iso_reference
    title = standard.title

    if event_type == "new":
        return (
            f"New Standard Published: {ref}",
            f"A new standard has been published: {ref} — {title}"
        )
    elif event_type == "updated":
        return (
            f"Standard Updated: {ref}",
            f"Standard has been updated: {ref} — {title}"
        )
    elif event_type == "amended":
        return (
            f"Standard Amended: {ref}",
            f"Standard amendment published: {ref} — {title}"
        )
    elif event_type == "withdrawn":
        return (
            f"Standard Withdrawn: {ref}",
            f"WARNING: Standard has been withdrawn: {ref} — {title}"
        )
    elif event_type == "replaced":
        return (
            f"Standard Replaced: {ref}",
            f"WARNING: Standard has been replaced by a newer edition: {ref} — {title}"
        )
    elif event_type == "purchased":
        return (
            f"Standard Purchased: {ref}",
            f"Standard is now purchased: {ref} — {title}"
        )
    elif event_type == "document_uploaded":
        return (
            f"Document Uploaded: {ref}",
            f"A new document has been uploaded for: {ref} — {title}"
        )
    else:
        return (
            f"Notification: {ref}",
            f"Event {event_type} occurred on: {ref} — {title}"
        )


def render_html_template(event_title: str, event_desc: str, recipient_name: str, standard, document=None) -> str:
    standard_url = f"http://localhost:5173/standards/{standard.id}"

    doc_section = ""
    if document:
        doc_section = f"""
        <tr>
            <td style="padding: 10px 0; border-bottom: 1px solid #f1f5f9; font-weight: bold; color: #475569;">Document Version</td>
            <td style="padding: 10px 0; border-bottom: 1px solid #f1f5f9; color: #334155;">v{document.version_number} ({document.filename})</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{event_title}</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; color: #1e293b; -webkit-font-smoothing: antialiased;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03); overflow: hidden;">
                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); padding: 32px; text-align: center;">
                            <h1 style="color: #ffffff; font-size: 24px; font-weight: 700; margin: 0; letter-spacing: -0.025em;">ISTS</h1>
                            <p style="color: #ccfbf1; font-size: 14px; margin: 8px 0 0 0; font-weight: 500;">ISO Standards Tracking System</p>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px 32px;">
                            <p style="font-size: 16px; line-height: 24px; margin-top: 0; color: #334155;">Hello {recipient_name},</p>
                            <p style="font-size: 16px; line-height: 24px; color: #334155; margin-bottom: 24px;">{event_desc}</p>
                            
                            <!-- Standard Card -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; border-radius: 8px; padding: 20px; margin-bottom: 32px;">
                                <tr>
                                    <td colspan="2" style="font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; padding-bottom: 12px;">Standard Details</td>
                                </tr>
                                <tr>
                                    <td width="35%" style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #475569;">Reference</td>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; color: #0f766e; font-weight: 600;">{standard.iso_reference}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #475569;">Title</td>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; color: #334155;">{standard.title}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #475569;">Status</td>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; color: #334155;">
                                        <span style="background-color: #ccfbf1; color: #0f766e; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{standard.status.value.upper() if hasattr(standard.status, 'value') else str(standard.status).upper()}</span>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #475569;">Edition</td>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; color: #334155;">{standard.edition or "—"}</td>
                                </tr>
                                <tr>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; font-weight: bold; color: #475569;">TC Committee</td>
                                    <td style="padding: 10px 0; border-bottom: 1px solid #e2e8f0; color: #334155;">{standard.tc_committee or "—"}</td>
                                </tr>
                                {doc_section}
                            </table>
                            
                            <!-- Action Button -->
                            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td align="center">
                                        <a href="{standard_url}" target="_blank" style="background-color: #0d9488; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 6px; font-weight: 600; font-size: 15px; display: inline-block;">View in Dashboard</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8fafc; padding: 24px; text-align: center; border-top: 1px solid #f1f5f9;">
                            <p style="font-size: 12px; color: #94a3b8; margin: 0 0 8px 0;">This is an automated notification from the ISTS tracking system.</p>
                            <p style="font-size: 12px; color: #94a3b8; margin: 0;">You received this because your email is mapped to these lifecycle events.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
    return html


def render_text_template(event_title: str, event_desc: str, recipient_name: str, standard, document=None) -> str:
    standard_url = f"http://localhost:5173/standards/{standard.id}"

    doc_str = ""
    if document:
        doc_str = f"Document Version: v{document.version_number} ({document.filename})\n"

    text = f"""Hello {recipient_name},

{event_desc}

--- STANDARD DETAILS ---
Reference: {standard.iso_reference}
Title: {standard.title}
Status: {standard.status.value if hasattr(standard.status, 'value') else str(standard.status)}
Edition: {standard.edition or "—"}
TC Committee: {standard.tc_committee or "—"}
{doc_str}
View standard in dashboard: {standard_url}

--
This is an automated notification from the ISTS tracking system.
You received this because your email is mapped to these lifecycle events.
"""
    return text


async def _send_bulk_notification_async(event_type: str, standard_id: str, triggered_by_id: str | None = None) -> dict:
    from app.database import async_session_factory
    from app.models.user import User
    from app.models.standard import Standard
    from app.models.notification import Notification, NotificationSeverity
    from sqlalchemy import select

    async with async_session_factory() as db:
        # Get standard details
        standard_uuid = uuid.UUID(standard_id)
        standard = await db.get(Standard, standard_uuid)
        if not standard:
            log.error("send_bulk_notification_standard_not_found", standard_id=standard_id)
            return {"status": "error", "reason": "standard_not_found"}

        # Get all active users
        res = await db.execute(select(User).where(User.is_active == True))
        active_users = res.scalars().all()

        # Set title and body depending on event
        title, body = get_notification_content(event_type, standard)
        severity = NotificationSeverity.info
        if event_type in ("withdrawn", "replaced"):
            severity = NotificationSeverity.warning

        # Add Notification in-app records
        for u in active_users:
            notif = Notification(
                user_id=u.id,
                event_type=event_type,
                severity=severity,
                title=title,
                body=body,
                related_standard_id=standard.id,
                is_read=False,
            )
            db.add(notif)

        await db.commit()
        log.info("send_bulk_notification_in_app_created", count=len(active_users), event_type=event_type)

    # Dispatch email notifications
    send_email_notification.delay({
        "event_type": event_type,
        "standard_id": standard_id,
        "triggered_by_id": triggered_by_id,
    })
    return {"status": "ok", "in_app_count": len(active_users)}


async def _send_email_notification_async(
    event_type: str,
    standard_id: str,
    document_id: str | None = None,
    triggered_by_id: str | None = None
) -> dict:
    from app.database import async_session_factory
    from app.models.standard import Standard
    from app.models.document import Document
    from app.models.distribution_list import DistributionListMember
    from app.models.notification_mapping import NotificationTriggerMapping
    from app.core.smtp_config import get_active_smtp_settings
    from app.services.audit_service import write_audit_log
    from sqlalchemy import select
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    async with async_session_factory() as db:
        # Load standard
        standard_uuid = uuid.UUID(standard_id)
        standard = await db.get(Standard, standard_uuid)
        if not standard:
            log.error("send_email_notification_standard_not_found", standard_id=standard_id)
            return {"status": "error", "reason": "standard_not_found"}

        # Load document if exists
        doc = None
        if document_id:
            doc = await db.get(Document, uuid.UUID(document_id))

        # Query mapped distribution lists
        stmt = (
            select(DistributionListMember.email, DistributionListMember.name)
            .join(NotificationTriggerMapping, NotificationTriggerMapping.list_id == DistributionListMember.list_id)
            .where(
                NotificationTriggerMapping.event_type == event_type,
                DistributionListMember.is_active == True
            )
        )
        res = await db.execute(stmt)
        members = res.all()

        # De-duplicate recipients by email
        recipients = {}
        for m_email, m_name in members:
            recipients[m_email] = m_name or m_email

        if not recipients:
            log.info("send_email_notification_no_recipients", event_type=event_type, standard_id=standard_id)
            return {"status": "ok", "recipient_count": 0}

        # Load SMTP settings dynamically from DB
        smtp_settings = await get_active_smtp_settings(db)

        # Event description/summary
        event_title, event_desc = get_notification_content(event_type, standard)

        # Build email templates
        subject = f"[ISTS] {event_title}"

        success_count = 0
        failure_count = 0
        failed_emails = []

        # Connect to SMTP server
        client = aiosmtplib.SMTP(
            hostname=smtp_settings["SMTP_HOST"],
            port=smtp_settings["SMTP_PORT"],
            use_tls=smtp_settings["SMTP_USE_TLS"]
        )
        await client.connect()
        if smtp_settings["SMTP_USER"] and smtp_settings["SMTP_PASSWORD"]:
            await client.login(smtp_settings["SMTP_USER"], smtp_settings["SMTP_PASSWORD"])

        try:
            for email, name in recipients.items():
                try:
                    html_body = render_html_template(
                        event_title=event_title,
                        event_desc=event_desc,
                        recipient_name=name,
                        standard=standard,
                        document=doc
                    )
                    text_body = render_text_template(
                        event_title=event_title,
                        event_desc=event_desc,
                        recipient_name=name,
                        standard=standard,
                        document=doc
                    )

                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"] = smtp_settings["SMTP_FROM_ADDRESS"]
                    msg["To"] = email

                    msg.attach(MIMEText(text_body, "plain"))
                    msg.attach(MIMEText(html_body, "html"))

                    await client.send_message(msg)
                    success_count += 1
                except Exception as e:
                    failure_count += 1
                    failed_emails.append((email, str(e)))
                    log.warning("send_email_failed_for_recipient", email=email, error=str(e))
        finally:
            await client.quit()

        # Audit logging
        actor_uuid = uuid.UUID(triggered_by_id) if triggered_by_id else None
        await write_audit_log(
            db,
            action="notification.email_sent",
            resource_type="standard",
            actor_id=actor_uuid,
            resource_id=standard.id,
            payload={
                "event_type": event_type,
                "recipient_count": len(recipients),
                "success_count": success_count,
                "failure_count": failure_count,
                "failures": failed_emails
            }
        )
        await db.commit()

    return {
        "status": "ok",
        "total_recipients": len(recipients),
        "success_count": success_count,
        "failure_count": failure_count
    }


@celery.task(name="app.tasks.notifications.send_email_notification", queue="notifications")
def send_email_notification(payload: dict) -> dict:  # type: ignore[no-untyped-def]
    """
    Assemble and send HTML email notifications to mapped distribution lists.

    Accepts payload with event_type, standard_id, and optional document_id, triggered_by_id.
    """
    log.info("send_email_notification_called", payload=payload)
    event_type = payload.get("event_type")
    standard_id = payload.get("standard_id")
    document_id = payload.get("document_id")
    triggered_by_id = payload.get("triggered_by_id")

    if not event_type or not standard_id:
        return {"status": "error", "reason": "missing_required_fields"}

    return asyncio.run(_send_email_notification_async(event_type, standard_id, document_id, triggered_by_id))


@celery.task(name="app.tasks.notifications.send_bulk_notification", queue="notifications")
def send_bulk_notification(payload: dict) -> dict:  # type: ignore[no-untyped-def]
    """
    Broadcast in-app notifications to all active users, then trigger email notifications.

    Accepts payload with event_type, standard_id, and optional triggered_by_id.
    """
    log.info("send_bulk_notification_called", payload=payload)
    event_type = payload.get("event_type")
    standard_id = payload.get("standard_id")
    triggered_by_id = payload.get("triggered_by_id")

    if not event_type or not standard_id:
        return {"status": "error", "reason": "missing_required_fields"}

    return asyncio.run(_send_bulk_notification_async(event_type, standard_id, triggered_by_id))
