"""
Document management service (M4).

Responsibilities:
  - list_documents()      — return all versions for a standard (newest first)
  - upload_document()     — validate MIME, compute SHA-256, check duplicate,
                            auto-assign version_number, flip is_current,
                            save to storage backend, write audit log,
                            create in-app notifications for all active users
  - get_download_info()   — verify doc exists, return (Document, download_url)
  - soft_delete_document()— set is_current=False, write audit log

PRD §3.4, §11, §14 rules enforced here:
  - version_number = MAX(version_number)+1 per standard_id
  - Duplicate SHA-256 within same standard → ConflictError (409)
  - Allowed MIME types: PDF, DOCX, XLSX (magic-byte validated)
  - Storage path: standards/{standard_id}/{version}_{filename}
  - Deletion is soft-only (is_current=False); file remains in storage
  - Upload triggers in-app notifications for all active users (M4 scope)
  - Email delivery is M5
"""

import uuid
from io import BytesIO
from typing import BinaryIO

import magic  # python-magic
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.core.storage import compute_sha256, get_storage_backend
from app.models.document import Document
from app.models.notification import Notification, NotificationSeverity
from app.models.standard import Standard
from app.models.user import User
from app.services.audit_service import write_audit_log

log = structlog.get_logger(__name__)

# Allowed upload types per PRD §3.4 (magic-byte checked, not just header)
_ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",         # .xlsx
    "application/msword",           # legacy .doc — accepted for compatibility
    "application/vnd.ms-excel",     # legacy .xls — accepted for compatibility
}

# Pre-signed URL TTL for S3 downloads (15 minutes per PRD §11.3)
_S3_DOWNLOAD_TTL_SECONDS = 900


async def list_documents(
    standard_id: uuid.UUID,
    db: AsyncSession,
    *,
    include_all_versions: bool = True,
) -> list[Document]:
    """Return all document versions for a standard, newest (highest version) first.

    Args:
        standard_id:          The standard's UUID.
        include_all_versions: If False, return only the current version.
    """
    query = (
        select(Document)
        .where(Document.standard_id == standard_id)
        .order_by(Document.version_number.desc())
    )
    if not include_all_versions:
        query = query.where(Document.is_current == True)  # noqa: E712

    result = await db.execute(query)
    return list(result.scalars().all())


async def upload_document(
    standard_id: uuid.UUID,
    file_data: BinaryIO,
    original_filename: str,
    file_size_bytes: int,
    change_notes: str | None,
    actor_id: uuid.UUID,
    db: AsyncSession,
    ip_address: str | None = None,
) -> Document:
    """Upload a new document version for a standard.

    Steps:
    1. Verify standard exists.
    2. Validate MIME type via magic-byte detection.
    3. Compute SHA-256 and reject duplicates within the same standard.
    4. Assign next version_number.
    5. Mark all prior versions is_current=False.
    6. Persist file to storage backend.
    7. Insert Document row.
    8. Write audit log.
    9. Create in-app Notification for every active user.

    Raises:
        NotFoundError       if the standard does not exist.
        AppValidationError  if the file type is not allowed.
        ConflictError       if an identical file (same SHA-256) already exists
                            for this standard.
    """
    # 1. Verify standard
    standard = await db.get(Standard, standard_id)
    if standard is None:
        raise NotFoundError("Standard")

    # 2. MIME detection (magic-byte, not the Content-Type header)
    header_bytes = file_data.read(2048)
    file_data.seek(0)
    detected_mime: str = magic.from_buffer(header_bytes, mime=True)
    if detected_mime not in _ALLOWED_MIME_TYPES:
        raise AppValidationError(
            f"File type not allowed: {detected_mime!r}. "
            "Accepted types: PDF, DOCX, XLSX."
        )

    # 3. SHA-256 checksum + duplicate detection
    checksum = compute_sha256(file_data)
    existing = await db.execute(
        select(Document).where(
            Document.standard_id == standard_id,
            Document.sha256_checksum == checksum,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(
            f"A document with the same content (SHA-256: {checksum}) already exists "
            "for this standard. Upload a different file or delete the existing version first."
        )

    # 4. Next version number
    max_version_result = await db.execute(
        select(func.max(Document.version_number)).where(
            Document.standard_id == standard_id
        )
    )
    current_max: int = max_version_result.scalar_one() or 0
    next_version = current_max + 1

    # 5. Mark all prior versions is_current=False
    prior_versions = await db.execute(
        select(Document).where(
            Document.standard_id == standard_id,
            Document.is_current == True,  # noqa: E712
        )
    )
    for old_doc in prior_versions.scalars().all():
        old_doc.is_current = False

    # 6. Persist to storage
    storage_key = f"standards/{standard_id}/{next_version}_{original_filename}"
    storage = get_storage_backend()
    # BytesIO wrapper if needed (file_data is already seeked to 0)
    file_data.seek(0)
    storage.upload(file_data, storage_key)

    # 7. Insert Document row
    doc = Document(
        standard_id=standard_id,
        version_number=next_version,
        filename=original_filename,
        storage_path=storage_key,
        file_size_bytes=file_size_bytes,
        sha256_checksum=checksum,
        mime_type=detected_mime,
        change_notes=change_notes,
        uploaded_by=actor_id,
        is_current=True,
    )
    db.add(doc)
    await db.flush()  # get doc.id before audit/notifications

    # 8. Audit log
    await write_audit_log(
        db,
        action="document.uploaded",
        resource_type="document",
        actor_id=actor_id,
        resource_id=doc.id,
        payload={
            "standard_id": str(standard_id),
            "filename": original_filename,
            "version_number": next_version,
            "sha256_checksum": checksum,
            "file_size_bytes": file_size_bytes,
        },
        ip_address=ip_address,
    )

    # 9. In-app notifications for all active users
    await _notify_all_users_document_uploaded(
        db,
        standard=standard,
        document=doc,
    )

    await db.commit()

    # 10. Enqueue email notifications to distribution lists
    from app.tasks.notifications import send_email_notification
    send_email_notification.delay({
        "event_type": "document_uploaded",
        "standard_id": str(standard_id),
        "document_id": str(doc.id),
        "triggered_by_id": str(actor_id),
    })

    log.info(
        "document.uploaded",
        standard_id=str(standard_id),
        document_id=str(doc.id),
        version=next_version,
        filename=original_filename,
        mime_type=detected_mime,
        sha256=checksum,
        actor_id=str(actor_id),
    )

    return doc


async def _notify_all_users_document_uploaded(
    db: AsyncSession,
    *,
    standard: Standard,
    document: Document,
) -> None:
    """Create an in-app Notification row for every active user (M4 scope).

    Email delivery is handled by the M5 Celery task. This function only
    writes in-app notification rows to the `notifications` table.
    """
    active_users_result = await db.execute(
        select(User).where(User.is_active == True)  # noqa: E712
    )
    active_users = active_users_result.scalars().all()

    title = f"Document uploaded: {standard.iso_reference}"
    body = (
        f"A new document version (v{document.version_number}) has been uploaded "
        f"for {standard.iso_reference} — {standard.title}.\n"
        f"File: {document.filename} ({_human_file_size(document.file_size_bytes)})"
    )

    for user in active_users:
        notification = Notification(
            user_id=user.id,
            event_type="document_uploaded",
            severity=NotificationSeverity.info,
            title=title,
            body=body,
            related_standard_id=standard.id,
            is_read=False,
        )
        db.add(notification)

    # Bulk flush in one round-trip (already inside the upload transaction)
    await db.flush()
    log.info(
        "document.notifications_created",
        count=len(active_users),
        standard_id=str(standard.id),
        document_id=str(document.id),
    )


def _human_file_size(size_bytes: int) -> str:
    """Format bytes as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.0f} TB"


async def get_download_info(
    document_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[Document, str]:
    """Return (Document, download_url_or_path) for the given document.

    For local storage the returned value is the filesystem path; the API
    endpoint streams it as a FileResponse.
    For S3 the returned value is a pre-signed URL (15 min TTL).

    Raises:
        NotFoundError if the document doesn't exist.
    """
    doc = await db.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document")

    storage = get_storage_backend()
    from app.config import settings  # avoid circular at module level

    ttl = _S3_DOWNLOAD_TTL_SECONDS if settings.STORAGE_BACKEND.lower() == "s3" else 0
    url = storage.download_url(doc.storage_path, ttl=ttl)

    log.info(
        "document.download_requested",
        document_id=str(document_id),
        filename=doc.filename,
        storage_backend=settings.STORAGE_BACKEND,
    )
    return doc, url


async def soft_delete_document(
    document_id: uuid.UUID,
    actor_id: uuid.UUID,
    db: AsyncSession,
    ip_address: str | None = None,
) -> Document:
    """Soft-delete a document version: sets is_current=False.

    The file remains in storage (physical deletion is a future purge endpoint).
    Raises NotFoundError if the document doesn't exist.
    """
    doc = await db.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document")

    doc.is_current = False
    await db.flush()

    await write_audit_log(
        db,
        action="document.deleted",
        resource_type="document",
        actor_id=actor_id,
        resource_id=doc.id,
        payload={
            "standard_id": str(doc.standard_id),
            "filename": doc.filename,
            "version_number": doc.version_number,
        },
        ip_address=ip_address,
    )

    log.info(
        "document.soft_deleted",
        document_id=str(document_id),
        actor_id=str(actor_id),
    )
    return doc
