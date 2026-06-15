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

from fastapi import APIRouter, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse

from app.api.deps import AdminUser, CurrentUser, DBSession, ManagerOrAdminUser
from app.config import settings
from app.schemas.document import DocumentDownloadResponse, DocumentResponse
from app.schemas.pagination import Page
from app.services import document_service

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

    return Page[DocumentResponse](
        items=[DocumentResponse.model_validate(d) for d in paged],
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
    Returns 422 if the file type is not allowed.
    """
    file_bytes = await file.read()
    file_size = len(file_bytes)
    original_filename = file.filename or "document"

    from io import BytesIO
    file_io = BytesIO(file_bytes)

    doc = await document_service.upload_document(
        standard_id=standard_id,
        file_data=file_io,
        original_filename=original_filename,
        file_size_bytes=file_size,
        change_notes=change_notes,
        actor_id=current_user.id,
        db=db,
        ip_address=_client_ip(request),
    )
    return DocumentResponse.model_validate(doc)


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

    # Local: stream the file
    return FileResponse(
        path=download_url,
        filename=doc.filename,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.filename}"',
        },
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
