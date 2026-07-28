"""
Celery tasks: documents queue.

tag_document(document_id) — submits a document's file to the admin-configured
AI tagging service and stores the structured response in document_tags.

The service is an async, job-based API:
  POST {DOCUMENT_TAGGING_URL}            (multipart file=) -> {"job_id": ...}
  GET  {DOCUMENT_TAGGING_URL}/{id}/stream -> Server-Sent Events, each
                                            `data: {json}` carrying `status`
                                            and, once done, a `result` object.
The `result` object matches the document_tags schema (document_type, summary,
department, category_01..09), so _build_search_text/mark_tag_result are reused.
See docs/superpowers/specs/2026-07-07-document-ai-tagging-design.md and
docs/superpowers/specs/2026-07-17-tagging-integration-and-review-fixes-design.md.
"""

import asyncio
import json
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


# Terminal job statuses reported by the tagging service. Anything else
# (e.g. "pending", "processing") means the job is still running.
_STATUS_COMPLETED = "completed"
_STATUS_FAILED = "failed"

# Read timeout for the tagging request scales with file size — larger files
# take the LLM-backed service longer to process — capped so a request can
# never hang past 30 minutes.
_TAGGING_TIMEOUT_BASE_SECONDS = 300
_TAGGING_TIMEOUT_PER_MB_SECONDS = 30
_TAGGING_TIMEOUT_MAX_SECONDS = 1800


def _compute_tagging_timeout_seconds(file_size_bytes: int) -> float:
    size_mb = file_size_bytes / (1024 * 1024)
    return min(
        _TAGGING_TIMEOUT_MAX_SECONDS,
        _TAGGING_TIMEOUT_BASE_SECONDS + size_mb * _TAGGING_TIMEOUT_PER_MB_SECONDS,
    )


def _extract_result_from_event(event: dict) -> dict | None:
    """Interpret one job-status object.

    Returns the completed `result` dict, raises RuntimeError on failure, or
    returns None if the job is not in a terminal state yet.
    """
    status_val = str(event.get("status") or "").lower()
    if status_val == _STATUS_COMPLETED:
        result = event.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Tagging job completed with no result payload")
        return result
    if status_val == _STATUS_FAILED:
        raise RuntimeError(event.get("error") or "Tagging job failed")
    return None


def _consume_sse_event(data_lines: list[str], document_id: str) -> dict | None:
    """Parse one buffered SSE event's data lines; delegate to _extract_result_from_event."""
    if not data_lines:
        return None
    payload = "\n".join(data_lines)
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("tag_document_bad_sse_event", document_id=document_id, payload=payload[:200])
        return None
    return _extract_result_from_event(event)


async def _stream_job_result(
    client: httpx.AsyncClient, stream_url: str, headers: dict, document_id: str
) -> dict:
    """Consume the job's SSE stream until a terminal status; return the completed result.

    Raises RuntimeError on job failure or if the stream closes with no terminal event.
    """
    buffer: list[str] = []
    async with client.stream("GET", stream_url, headers=headers) as resp:
        resp.raise_for_status()
        async for raw_line in resp.aiter_lines():
            line = raw_line.rstrip("\r")
            if line.startswith("data:"):
                buffer.append(line[len("data:"):].lstrip(" "))
            elif line == "":
                # Blank line terminates one SSE event.
                result = _consume_sse_event(buffer, document_id)
                buffer.clear()
                if result is not None:
                    return result
            # Other SSE fields (event:, id:, retry:, ":" comments) are ignored.
        # Flush a trailing event the server didn't terminate with a blank line.
        result = _consume_sse_event(buffer, document_id)
        if result is not None:
            return result
    raise RuntimeError("Tagging job stream closed before a terminal status")


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

        headers = {
            # Bypass the ngrok free-tier browser interstitial, which would
            # otherwise replace the JSON body with an HTML warning page.
            "ngrok-skip-browser-warning": "true",
        }
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

            # Read timeout scales with file size (see _compute_tagging_timeout_seconds);
            # it also bounds the gap between SSE events on the stream below.
            timeout_seconds = _compute_tagging_timeout_seconds(doc.file_size_bytes)
            with open(file_path, "rb") as fh:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=15)) as client:
                    # 1. Submit the job.
                    submit_resp = await client.post(
                        url,
                        files={"file": (doc.filename, fh, doc.mime_type)},
                        headers=headers,
                    )
                    submit_resp.raise_for_status()
                    submit_body = submit_resp.json()

                    # 2. If the POST already returned a completed result, use it
                    # directly (covers a synchronous deployment). Otherwise poll
                    # the per-job SSE stream until it reaches a terminal status.
                    result = _extract_result_from_event(submit_body)
                    if result is None:
                        job_id = submit_body.get("job_id")
                        if not job_id:
                            raise RuntimeError(
                                f"Tagging service returned no job_id: {submit_body!r}"
                            )
                        stream_url = f"{url.rstrip('/')}/{job_id}/stream"
                        result = await _stream_job_result(
                            client, stream_url, headers, document_id
                        )
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
