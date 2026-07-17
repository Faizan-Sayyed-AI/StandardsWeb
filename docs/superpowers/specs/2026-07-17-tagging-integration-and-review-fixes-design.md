# Tagging Integration + Code-Review Fixes — Design

Date: 2026-07-17

Two pieces of work bundled into one branch:

1. Integrate the async job-based AI tagging service (`/jobs` + SSE stream) into the
   existing document-tagging pipeline.
2. Apply the verified findings from the high-effort code review of commit `e804a6f`.

---

## Part A — Code-review fixes

### Mechanical

- **#2 / #9 / #10 — upload path** (`backend/app/api/v1/documents.py`, upload block):
  one combined edit.
  - Keep the streamed upload (do **not** restore `await file.read()`, which would
    refill up to 50 MB into RAM and defeat the commit's memory goal).
  - Offload the synchronous `document_service.upload_document(...)` call to a
    threadpool via `asyncio.to_thread(...)` so hashing + storage no longer run
    inline on the event loop.
  - Replace the hand-rolled `seek(0,2)/tell()/seek(0)` size measurement with
    Starlette's `file.size`.
  - Correct the comment: the streaming/memory goal fully holds only for the S3
    backend; `LocalStorageBackend.upload` still buffers the whole file.
- **#3 — flat pagination** (`standard_service.py`, `list_standards`): add
  `Standard.id` as a secondary sort key so OFFSET/LIMIT pages are stable when the
  primary sort column has ties (mirrors the grouped path).
- **#4 — S3 prune** (`scripts/deploy-frontend.ps1`): the only `--delete` pass
  excludes `*.js`/`*.css`, so hashed bundles are never pruned. Restructure so old
  hashed JS/CSS bundles are actually deleted, without breaking the forced
  Content-Type headers on the js/css upload passes.
- **#6 — empty-string group key** (`standard_service.py`, `get_grouped_standards`):
  `coalesce(base_reference, id)` only substitutes SQL NULL, so `base_reference=''`
  rows collapse into one group. Use `coalesce(nullif(base_reference, ''), id)` so
  empty strings behave like NULL (singleton group).

### Judgment calls (decisions made with the user)

- **#1 — Celery acks_late**: leave `task_acks_late=False`. It is a deliberate
  tradeoff (avoids crash-loop redelivery + duplicate notification emails). Rewrite
  the comment to state honestly that a hard worker crash (OOM/SIGKILL) drops the
  in-flight task with no automatic recovery, and that recovery is manual re-tag.
- **#5 — status sort order**: no change. Grouped and flat paths both sort status by
  Postgres native-enum declaration order and are therefore consistent with each
  other. Add a one-line note recording that the consistency is intentional.
- **#7 — toast dedup**: dedup **only** destructive/error toasts (the background
  poller spam path via the `api-error` event). Non-destructive user-action toasts
  always show. Update `toastQueue.test.ts` accordingly.
- **#8 — test typecheck exclusion**: keep test files excluded from `tsc -b` (vitest
  globals aren't in the typecheck `types`; they still run under vitest). Add a
  comment in `tsconfig.app.json` explaining the exclusion.
- **Encoding cleanup**: remove the UTF-8 BOM and fix the `—` mojibake introduced in
  `standard_service.py` docstrings.

---

## Part B — Tagging integration

The external service is an async, job-based API behind a free ngrok tunnel:

- `POST {base}/jobs` (multipart `file=`) → returns a job, including `job_id`.
- `GET {base}/jobs/{job_id}/stream` → Server-Sent Events stream emitting
  `data: {json}` lines. Each event carries `status` and, on completion, a `result`
  object. Terminal statuses: `completed`, `failed`.
- The `result` object matches the existing schema exactly: `document_type`,
  `summary`, `department`, `category_01..09` arrays (plus a `truncated` flag), so
  the existing `_build_search_text` and `mark_tag_result` code is reused unchanged.

### Wiring

Via the existing admin `DOCUMENT_TAGGING_URL` system-config setting. The operator
sets it to `https://<tunnel>/jobs`. The stream URL is derived by appending
`/{job_id}/stream`. No hardcoded URL.

### Changed component

Only `_tag_document_async` in `backend/app/tasks/documents.py`:

1. **Submit** — stream the file (existing temp-file / S3-download logic) to
   `POST {url}`. Parse `job_id` from the JSON response. Defensive fallback: if the
   POST body already contains `status:"completed"` with a `result`, use it directly
   (covers a synchronous deployment of the service).
2. **Poll via SSE** — open `GET {url_without_trailing_slash}/{job_id}/stream`, read
   `data:` events, parse JSON, until a terminal status:
   - `completed` → `result` → `_build_search_text` → `mark_tag_result(ok, ...)`.
   - `failed` (or `error` non-null) → raise, so the existing retry path fires.
   - stream ends without a terminal status → raise → retry.
3. **Headers** — keep `Authorization: Bearer <key>` when an API key is configured;
   add `ngrok-skip-browser-warning: true` so the free-tunnel interstitial can't
   corrupt the response body.
4. **Timeouts** — long read timeout (300 s) on the stream; observed jobs take
   ~2 min. Connect timeout stays short.

### Offline / error behavior

Unchanged: 3 retries with exponential backoff, then `mark_tag_result(failed, ...)`
with the error message. The operator re-tags from the UI once the tunnel is back.
An offline tunnel is the common steady state for this free-tier service.

### Verification

The tunnel is offline at authoring time, so this cannot be end-to-end verified
during implementation. Completion requires a live check: bring the tunnel online,
set `DOCUMENT_TAGGING_URL`, upload the sample PDF
(`ISO 14630 (2012) - Non-active surgical implants.pdf`), and confirm the document
reaches `ok` tag status with a populated `search_text`. This live-verify is a real
completion criterion.

## Out of scope

- No change to the tagging response schema or `document_tag` model.
- No change to how tagging is dispatched on upload/retag.
- No broader refactor of the storage backends (the local-backend buffering is
  documented, not fixed).
