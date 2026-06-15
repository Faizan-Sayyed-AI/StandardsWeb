"""
Pydantic schemas for the documents API (M4).

Endpoints:
  GET  /standards/{id}/documents      → Page[DocumentResponse]
  POST /standards/{id}/documents      → DocumentUploadResponse
  GET  /documents/{id}/download       → DocumentDownloadResponse
  DELETE /documents/{id}              → 204 No Content
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    """Full document metadata — returned in list and after upload."""

    id: uuid.UUID
    standard_id: uuid.UUID
    version_number: int
    filename: str
    file_size_bytes: int
    sha256_checksum: str
    mime_type: str
    change_notes: str | None
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    is_current: bool

    model_config = {"from_attributes": True}


class DocumentUploadResponse(DocumentResponse):
    """Returned after a successful upload — identical to DocumentResponse for now."""

    pass


class DocumentDownloadResponse(BaseModel):
    """Returned by the download endpoint.

    For local storage: `download_url` is a signed path token; the frontend
    should follow this URL which FastAPI will stream as a file attachment.
    For S3: `download_url` is a pre-signed S3 URL valid for 15 minutes.
    """

    document_id: uuid.UUID
    filename: str
    download_url: str
    expires_in_seconds: int | None  # None for local (no expiry — streamed directly)
