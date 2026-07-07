"""
document_tags read/write service.

Owns all access to the document_tags table — the Celery tagging task, the
upload flow, and the manual retry endpoint all go through these functions
rather than touching the table directly.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.document_tag import DocumentTag, DocumentTagStatus

log = structlog.get_logger(__name__)


async def create_pending_tag(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag:
    """Create the initial pending tag row for a freshly-uploaded document."""
    tag = DocumentTag(document_id=document_id, status=DocumentTagStatus.pending)
    db.add(tag)
    await db.flush()
    return tag


async def get_tag_for_document(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag | None:
    """Return the tag row for one document, or None if it has none (pre-feature upload)."""
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.document_id == document_id)
    )
    return result.scalar_one_or_none()


async def get_tags_for_documents(
    document_ids: list[uuid.UUID], db: AsyncSession
) -> dict[uuid.UUID, DocumentTag]:
    """Bulk-fetch tag rows for a list of documents, keyed by document_id (avoids N+1 queries)."""
    if not document_ids:
        return {}
    result = await db.execute(
        select(DocumentTag).where(DocumentTag.document_id.in_(document_ids))
    )
    return {tag.document_id: tag for tag in result.scalars().all()}


async def mark_tag_result(
    document_id: uuid.UUID,
    db: AsyncSession,
    *,
    status: DocumentTagStatus,
    document_type: str | None = None,
    summary: str | None = None,
    department: str | None = None,
    raw_response: dict[str, Any] | None = None,
    search_text: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update a tag row with the outcome of a tagging attempt (success or failure)."""
    tag = await get_tag_for_document(document_id, db)
    if tag is None:
        log.error("document_tag_missing_on_result", document_id=str(document_id))
        return

    tag.status = status
    tag.document_type = document_type
    tag.summary = summary
    tag.department = department
    tag.raw_response = raw_response
    tag.search_text = search_text
    tag.error_message = error_message
    tag.completed_at = datetime.now(timezone.utc)
    await db.flush()


async def reset_tag_to_pending(document_id: uuid.UUID, db: AsyncSession) -> DocumentTag:
    """Reset a tag row to pending ahead of a manual re-tag. Raises NotFoundError if missing."""
    tag = await get_tag_for_document(document_id, db)
    if tag is None:
        raise NotFoundError("DocumentTag")

    tag.status = DocumentTagStatus.pending
    tag.error_message = None
    tag.completed_at = None
    await db.flush()
    return tag
