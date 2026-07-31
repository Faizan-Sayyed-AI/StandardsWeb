"""
Documents router — /api/v1/standards/{id}/documents  and  /api/v1/documents/{id}/*

Endpoints (PRD §7.2):
  GET    /standards/{standard_id}/documents          — list all versions  (viewer+)
  POST   /standards/{standard_id}/documents          — upload new version  (manager+)
  GET    /documents/{document_id}/download            — stream or redirect to download (viewer+)
  DELETE /documents/{document_id}                    — soft-delete version  (admin)

Local storage: download streams file via FileResponse (Content-Disposition: attachment).
S3 storage:    download returns a pre-signed URL (307 redirect).
"""

import uuid

from fastapi import APIRouter, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse

from app.api.deps import AdminUser, CurrentUser, DBSession, ManagerOrAdminUser
from app.config import settings
from app.core.exceptions import AppValidationError, NotFoundError
from app.core.iso_stages import is_draft_stage
from app.models.document import Document
from app.schemas.document import DocumentDownloadResponse, DocumentResponse, DocumentTagResponse
from app.schemas.pagination import Page
from app.services import document_tag_service, document_service, standard_service

router = APIRouter(tags=["Documents"])


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


# ── Nested under /standards/{standard_id}/documents ───────────────────────────


@router.get(
    "/standards/{standard_id}/documents",
    response_model=Page[DocumentResponse],
    summary="List document versions for a standard (viewer+)",
)
async def list_documents(
    standard_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[DocumentResponse]:
    """
    Return all uploaded document versions for a standard, newest first.
    Returns 404 if the standard does not exist.
    """
    docs = await document_service.list_documents(standard_id, db)

    # Manual pagination on the in-memory list (documents per standard are few)
    total = len(docs)
    offset = (page - 1) * page_size
    paged = docs[offset : offset + page_size]

    tag_map = await document_tag_service.get_tags_for_documents([d.id for d in paged], db)
    items = []
    for d in paged:
        resp = DocumentResponse.model_validate(d)
        tag = tag_map.get(d.id)
        resp.tags = DocumentTagResponse.model_validate(tag) if tag else None
        items.append(resp)

    return Page[DocumentResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/standards/{standard_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document version (manager+)",
)
async def upload_document(
    standard_id: uuid.UUID,
    request: Request,
    db: DBSession,
    current_user: ManagerOrAdminUser,
    file: UploadFile,
    change_notes: str | None = Form(default=None),
) -> DocumentResponse:
    """
    Upload a PDF, DOCX, or XLSX file as a new version of the standard's document.

    - MIME type is validated via magic-byte detection (not just the file extension).
    - SHA-256 checksum is computed server-side; duplicate files are rejected (409).
    - Version number is auto-assigned (MAX + 1 per standard).
    - All prior `is_current=True` rows for this standard are flipped to False.
    - An in-app notification is created for every active user.

    Returns 404 if the standard does not exist.
    Returns 409 if an identical file already exists for this standard.
    Returns 413 if the file exceeds MAX_UPLOAD_SIZE_MB.
    Returns 422 if the file type is not allowed, or the standard is a draft.
    """
    # Reject drafts before touching the upload stream or storage. get_standard
    # raises NotFoundError (404) for a missing standard, preserving this
    # endpoint's documented 404 behaviour.
    standard = await standard_service.get_standard(standard_id, db)
    if is_draft_stage(standard.stage_code):
        raise AppValidationError(standard_service.draft_blocked_reason(standard))

    # Starlette has already spooled the upload to a temp file — pass that file
    # object through instead of buffering the whole upload in memory. The service
    # reads it inside a threadpool (asyncio.to_thread) so the disk I/O never
    # blocks the event loop. sha256 is fully streamed; storage upload streams on
    # S3, though the local dev backend still buffers the whole file.
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    upload_stream = file.file
    # Starlette's multipart parser records the spooled size; fall back to a
    # manual measure only if it is unavailable.
    file_size = file.size
    if file_size is None:
        upload_stream.seek(0, 2)
        file_size = upload_stream.tell()
        upload_stream.seek(0)
    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is {file_size / (1024 * 1024):.1f} MB; the maximum allowed size "
            f"is {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )
    original_filename = file.filename or "document"

    doc = await document_service.upload_document(
        standard_id=standard_id,
        file_data=upload_stream,
        original_filename=original_filename,
        file_size_bytes=file_size,
        change_notes=change_notes,
        actor_id=current_user.id,
        db=db,
        ip_address=_client_ip(request),
    )
    resp = DocumentResponse.model_validate(doc)
    tag = await document_tag_service.get_tag_for_document(doc.id, db)
    resp.tags = DocumentTagResponse.model_validate(tag) if tag else None
    return resp


@router.post(
    "/documents/{document_id}/retag",
    response_model=DocumentResponse,
    summary="Re-run AI tagging for a document (manager+)",
)
async def retag_document(
    document_id: uuid.UUID,
    db: DBSession,
    current_user: ManagerOrAdminUser,
) -> DocumentResponse:
    """
    Reset a document's tag status to pending and re-dispatch tagging.

    Available regardless of current tag status (not just failed ones).
    Returns 404 if the document doesn't exist, or if it has never been
    tagged (documents uploaded before this feature shipped have no tag row —
    re-uploading is the only way to get one, since there's nothing to reset).
    """
    from app.tasks.documents import tag_document

    doc = await db.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document")

    tag = await document_tag_service.reset_tag_to_pending(document_id, db)
    await db.commit()

    tag_document.delay(str(document_id))

    resp = DocumentResponse.model_validate(doc)
    resp.tags = DocumentTagResponse.model_validate(tag)
    return resp


# ── Standalone /documents/{document_id}/* ────────────────────────────────────


@router.get(
    "/documents/{document_id}/download",
    response_model=None,  # FileResponse | RedirectResponse can't be a Pydantic schema
    summary="Download a document version (viewer+)",
    responses={
        200: {"description": "File streamed (local storage)"},
        307: {"description": "Redirect to pre-signed S3 URL"},
    },
)
async def download_document(
    document_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,
) -> FileResponse | RedirectResponse:
    """
    Retrieve a document for download.

    - **Local storage**: streams the file directly as a binary attachment.
    - **S3 storage**: returns a 307 redirect to a 15-minute pre-signed URL.

    Returns 404 if the document does not exist.
    """
    doc, download_url = await document_service.get_download_info(document_id, db)

    if settings.STORAGE_BACKEND.lower() == "s3":
        return RedirectResponse(url=download_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Local: stream the file. Content-Disposition is derived from `filename`
    # by FileResponse itself (percent-encoded via urllib.parse.quote), which
    # safely escapes quote/control characters in a user-supplied upload
    # filename — do NOT pass an explicit Content-Disposition header here, it
    # would override that safe default with an unescaped, injectable string.
    return FileResponse(
        path=download_url,
        filename=doc.filename,
        media_type=doc.mime_type,
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a document version (admin)",
)
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    """
    Soft-delete a document version (sets is_current=False).

    The file itself is retained in storage; physical deletion requires a
    future admin purge endpoint.

    Returns 204 No Content on success.
    Returns 404 if the document does not exist.
    """
    await document_service.soft_delete_document(
        document_id,
        actor_id=current_user.id,
        db=db,
        ip_address=_client_ip(request),
    )
