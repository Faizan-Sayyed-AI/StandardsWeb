"""
Celery tasks: documents queue.

tag_document(document_id) — POSTs a document's file to the admin-configured
AI tagging service and stores the structured response in document_tags.
See docs/superpowers/specs/2026-07-07-document-ai-tagging-design.md.
"""

import asyncio
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
    from sqlalchemy import select

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

        if storage_ref.startswith("http://") or storage_ref.startswith("https://"):
            async with httpx.AsyncClient(timeout=60) as client:
                file_resp = await client.get(storage_ref)
                file_resp.raise_for_status()
                file_bytes = file_resp.content
        else:
            with open(storage_ref, "rb") as f:
                file_bytes = f.read()

        headers = {}
        api_key = settings_dict.get("DOCUMENT_TAGGING_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                url,
                files={"file": (doc.filename, file_bytes, doc.mime_type)},
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()

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

        if is_final:
            log.error(
                "tag_document_permanently_failed",
                document_id=document_id,
                retries=retries,
                error=str(exc),
            )
            asyncio.run(_mark_tagging_permanently_failed(document_id, str(exc)))
            return {"status": "permanently_failed", "document_id": document_id, "error": str(exc)}

        countdown = 60 * (2 ** retries)
        log.warning(
            "tag_document_retrying",
            document_id=document_id,
            error=str(exc),
            retry_number=retries + 1,
            countdown_seconds=countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)
