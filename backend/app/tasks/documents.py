"""
Celery tasks: documents queue.

tag_document(document_id) — POSTs a document's file to the admin-configured
AI tagging service and stores the structured response in document_tags.
See docs/superpowers/specs/2026-07-07-document-ai-tagging-design.md.
"""

import asyncio
import os
import tempfile
import uuid

import httpx
import structlog

from app.celery_app import celery

log = structlog.get_logger(__name__)

# The response's fixed category keys — every value across all of these,
# plus summary and department, gets flattened into search_text.
_CATEGORY_KEYS = [
    "category_01_metadata",
    "category_02_primary_subject",
    "category_03_technical_methods",
    "category_04_nlp_ai_models",
    "category_05_application_domain",
    "category_06_system_architecture",
    "category_07_statistical_mathematical",
    "category_08_semantic_conceptual",
    "category_09_long_tail_phrases",
]


def _build_search_text(payload: dict) -> str:
    """Flatten summary + department + every category tag into one lowercase, space-joined string."""
    parts: list[str] = []
    if payload.get("summary"):
        parts.append(str(payload["summary"]))
    if payload.get("department"):
        parts.append(str(payload["department"]))
    for key in _CATEGORY_KEYS:
        for value in payload.get(key) or []:
            parts.append(str(value))
    return " ".join(parts).lower()


async def _tag_document_async(document_id: str) -> dict:
    from app.database import async_session_factory
    from app.core.document_tagging_config import get_active_document_tagging_settings
    from app.core.storage import get_storage_backend
    from app.models.document import Document
    from app.models.document_tag import DocumentTagStatus
    from app.services import document_tag_service

    doc_uuid = uuid.UUID(document_id)

    async with async_session_factory() as db:
        doc = await db.get(Document, doc_uuid)
        if doc is None:
            log.error("tag_document_not_found", document_id=document_id)
            return {"status": "error", "reason": "document_not_found"}

        settings_dict = await get_active_document_tagging_settings(db)
        url = settings_dict.get("DOCUMENT_TAGGING_URL", "")

        if not url:
            log.info("tag_document_not_configured", document_id=document_id)
            await document_tag_service.mark_tag_result(
                doc_uuid, db,
                status=DocumentTagStatus.failed,
                error_message="Document tagging is not configured",
            )
            await db.commit()
            return {"status": "skipped", "reason": "not_configured"}

        storage = get_storage_backend()
        storage_ref = storage.download_url(doc.storage_path, ttl=300)

        headers = {}
        api_key = settings_dict.get("DOCUMENT_TAGGING_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Never hold the whole file in memory (uploads can be tens of MB and
        # the worker shares a small host): S3 files are streamed to a temp
        # file, and the multipart POST streams from an open file handle —
        # httpx chunks file-like objects instead of buffering the body.
        tmp_path: str | None = None
        try:
            if storage_ref.startswith("http://") or storage_ref.startswith("https://"):
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp_path = tmp.name
                    async with httpx.AsyncClient(timeout=60) as client:
                        async with client.stream("GET", storage_ref) as file_resp:
                            file_resp.raise_for_status()
                            async for chunk in file_resp.aiter_bytes(1024 * 1024):
                                tmp.write(chunk)
                file_path = tmp_path
            else:
                file_path = storage_ref

            # Generous read timeout: the tagging service is LLM-backed and has been
            # observed to take well over 120s on larger PDFs (ReadTimeout at exactly
            # 120s on documents that later tagged fine).
            with open(file_path, "rb") as fh:
                async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15)) as client:
                    response = await client.post(
                        url,
                        files={"file": (doc.filename, fh, doc.mime_type)},
                        headers=headers,
                    )
                    response.raise_for_status()
                    result = response.json()
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        search_text = _build_search_text(result)
        await document_tag_service.mark_tag_result(
            doc_uuid, db,
            status=DocumentTagStatus.ok,
            document_type=result.get("document_type"),
            summary=result.get("summary"),
            department=result.get("department"),
            raw_response=result,
            search_text=search_text,
        )
        await db.commit()

    log.info("tag_document_complete", document_id=document_id)
    return {"status": "ok", "document_id": document_id}


async def _mark_tagging_permanently_failed(document_id: str, error_msg: str) -> None:
    from app.database import async_session_factory
    from app.models.document_tag import DocumentTagStatus
    from app.services import document_tag_service
    from app.services.audit_service import write_audit_log

    doc_uuid = uuid.UUID(document_id)
    async with async_session_factory() as db:
        await document_tag_service.mark_tag_result(
            doc_uuid, db,
            status=DocumentTagStatus.failed,
            error_message=error_msg,
        )
        await write_audit_log(
            db,
            action="document.tagging_failed",
            resource_type="document",
            resource_id=doc_uuid,
            payload={"error": error_msg},
        )
        await db.commit()


@celery.task(
    name="app.tasks.documents.tag_document",
    queue="documents",
    bind=True,
    max_retries=3,
)
def tag_document(self, document_id: str) -> dict:
    """Tag a document via the external AI service. Retries on failure; see module docstring."""
    log.info("tag_document_starting", document_id=document_id, attempt=self.request.retries + 1)

    try:
        return asyncio.run(_tag_document_async(document_id))
    except Exception as exc:
        retries = self.request.retries
        is_final = retries >= self.max_retries
        # str() of httpx transport errors (ReadTimeout(''), ConnectError('')) is
        # empty, which left error_message blank in the UI and `error=` in logs.
        error_msg = str(exc) or type(exc).__name__

        if is_final:
            log.error(
                "tag_document_permanently_failed",
                document_id=document_id,
                retries=retries,
                error=error_msg,
            )
            asyncio.run(_mark_tagging_permanently_failed(document_id, error_msg))
            return {"status": "permanently_failed", "document_id": document_id, "error": error_msg}

        countdown = 60 * (2 ** retries)
        log.warning(
            "tag_document_retrying",
            document_id=document_id,
            error=error_msg,
            retry_number=retries + 1,
            countdown_seconds=countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)
