# Deleted Document Watermark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a diagonal "Deleted" watermark on a document version's card only when it was explicitly soft-deleted (trash icon) — not when it was merely superseded by a newer upload, which look identical today since both just set `is_current=False`.

**Architecture:** Add a nullable `deleted_at` timestamp column to `documents`, set only by the existing soft-delete path. The frontend renders the watermark purely off `Boolean(doc.deleted_at)`, independent of the existing `is_current`-driven "archived"/"Current" styling, which is untouched.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, React + TypeScript + TanStack Query. No new dependencies.

## Global Constraints

- **No automated test suite exists in this repo** (backend or frontend). Verification for every task is live: `docker compose exec` + `psql`/`curl` for backend, `npx tsc --noEmit` + manual browser check for frontend — matching this codebase's established practice (see e.g. `docs/superpowers/plans/2026-07-08-manual-standard-entry.md`'s Global Constraints).
- **Migration numbering**: current head is `0013_add_api_keys.py`. The new migration is `0014`.
- **`deleted_at` is set only by `soft_delete_document()`** (`app/services/document_service.py`) — never by the version-upload path that flips `is_current=False` on a superseded row (`upload_document()`, same file, lines ~156-164). Do not touch that path.
- **Actions stay unchanged on a deleted row** — no gating of download/retag/delete buttons on deletion state, no restore endpoint. The watermark is purely visual.
- **Stamp must not block clicks**: the overlay `<div>` needs `pointer-events-none` so it never intercepts clicks meant for the download/retag/delete buttons underneath it.

---

### Task 1: `deleted_at` migration and model field

**Files:**
- Create: `backend/alembic/versions/0014_add_document_deleted_at.py`
- Modify: `backend/app/models/document.py`

**Interfaces:**
- Produces: `Document.deleted_at: datetime | None` column — consumed by Task 2 (`soft_delete_document()`) and Task 2's schema change.

- [ ] **Step 1: Write the migration**

```python
"""Add deleted_at to documents (distinguishes explicit delete from supersession).

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-28

deleted_at is set only by the explicit soft-delete action (soft_delete_document()),
never by the normal upload flow flipping an old version's is_current to False.
Existing rows are all NULL, which is correct — nothing already soft-deleted before
this column existed should retroactively show as deleted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column(
        'deleted_at', sa.DateTime(timezone=True), nullable=True,
        comment="Set only by an explicit soft-delete, never by version supersession — "
                "distinguishes 'deleted' from merely 'not the current version'."
    ))


def downgrade() -> None:
    op.drop_column('documents', 'deleted_at')
```

- [ ] **Step 2: Add the column to the model**

In `backend/app/models/document.py`, the field list currently ends with `is_current` (line 59):

```python
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
```

Add `deleted_at` right after it:

```python
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`datetime` and `DateTime` are already imported at the top of this file (`from datetime import datetime` and `from sqlalchemy import ... DateTime ...`) — no new imports needed.

Also update the module docstring's schema comment block at the top of the file (after the `is_current` line) to add:
```
  deleted_at       TIMESTAMPTZ NULLABLE  (set only by explicit soft-delete, not supersession)
```

- [ ] **Step 3: Verify — apply the migration against the live stack**

```bash
docker compose up -d db redis web worker beat mailhog
docker compose exec -T web alembic upgrade head
docker compose exec -T web alembic current
```
Expected: last line prints `0014 (head)`.

```bash
docker compose exec -T db psql -U ists -d ists -c "\d documents" | grep deleted_at
```
Expected: shows `deleted_at | timestamp with time zone |`.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/0014_add_document_deleted_at.py backend/app/models/document.py
git commit -m "feat: add deleted_at column to documents"
```

---

### Task 2: Set `deleted_at` on soft-delete and expose it in the API

**Files:**
- Modify: `backend/app/services/document_service.py:23-39` (imports), `:333-368` (`soft_delete_document`)
- Modify: `backend/app/schemas/document.py:32-48` (`DocumentResponse`)

**Interfaces:**
- Consumes: `Document.deleted_at` from Task 1.
- Produces: `DocumentResponse.deleted_at: datetime | None` in every `GET /standards/{id}/documents` list item — consumed by Task 3's frontend `Document` interface and render logic.

- [ ] **Step 1: Add the `datetime`/`timezone` import**

`document_service.py` currently has no `datetime` import (verify with `grep -n "^from datetime" backend/app/services/document_service.py` — expect no output before this change). Add it alongside the existing stdlib imports at the top of the file:

```python
import asyncio
import uuid
from datetime import datetime, timezone
from typing import BinaryIO
```

- [ ] **Step 2: Set `deleted_at` in `soft_delete_document()`**

Current code (`document_service.py`, in `soft_delete_document`):

```python
    doc.is_current = False
    await db.flush()
```

Change to:

```python
    doc.is_current = False
    doc.deleted_at = datetime.now(timezone.utc)
    await db.flush()
```

- [ ] **Step 3: Add `deleted_at` to the response schema**

In `backend/app/schemas/document.py`, `DocumentResponse` currently ends its field list with:

```python
    is_current: bool
    tags: DocumentTagResponse | None = None
```

Add `deleted_at` between them (matches the model's field order):

```python
    is_current: bool
    deleted_at: datetime | None
    tags: DocumentTagResponse | None = None
```

`datetime` is already imported at the top of this file. No change needed to `app/api/v1/documents.py` — `DocumentResponse.model_validate(d)` (line 68) already picks up every ORM attribute via `from_attributes=True`.

- [ ] **Step 4: Verify — exercise the live delete flow end-to-end**

Pick a real `standard_id`/`document_id` pair from your dev data (or upload a fresh test document first via the UI at `http://localhost:5173`), then:

```bash
docker compose exec -T db psql -U ists -d ists -c \
  "SELECT id, is_current, deleted_at FROM documents ORDER BY uploaded_at DESC LIMIT 3;"
```
Note a `document_id` with `deleted_at` currently `NULL`.

Log in as an admin in the running frontend (`http://localhost:5173`), delete that document version from its standard's detail page, then re-run the same `psql` query.

Expected: that row's `is_current` is now `f` and `deleted_at` is a non-null timestamp close to "now."

Also confirm the list endpoint returns the new field (curl is not installed inside the `web` container — run this from the host, since port 8000 is published there per `docker-compose.yml`):
```bash
curl -s -H "Authorization: Bearer <a valid admin token>" \
  "http://localhost:8000/api/v1/standards/<standard_id>/documents" | python3 -m json.tool | grep -A1 deleted_at
```
Expected: the deleted document's entry shows a non-null `deleted_at`; any other, non-deleted version in the same output shows `"deleted_at": null`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/document_service.py backend/app/schemas/document.py
git commit -m "feat: set deleted_at on soft-delete and expose it in the documents API"
```

---

### Task 3: Frontend "Deleted" watermark

**Files:**
- Modify: `frontend/src/api/documents.ts:6-19` (`Document` interface)
- Modify: `frontend/src/pages/StandardDetailPage.tsx:832-846` (document card render)

**Interfaces:**
- Consumes: `DocumentResponse.deleted_at` from Task 2, surfaced on `Document.deleted_at: string | null`.

- [ ] **Step 1: Add `deleted_at` to the `Document` interface**

Current (`frontend/src/api/documents.ts:6-19`):

```typescript
export interface Document {
  id: string;
  standard_id: string;
  version_number: number;
  filename: string;
  file_size_bytes: number;
  sha256_checksum: string;
  mime_type: string;
  change_notes: string | null;
  uploaded_by: string;
  uploaded_at: string;
  is_current: boolean;
  tags: DocumentTag | null;
}
```

Change to:

```typescript
export interface Document {
  id: string;
  standard_id: string;
  version_number: number;
  filename: string;
  file_size_bytes: number;
  sha256_checksum: string;
  mime_type: string;
  change_notes: string | null;
  uploaded_by: string;
  uploaded_at: string;
  is_current: boolean;
  deleted_at: string | null;
  tags: DocumentTag | null;
}
```

- [ ] **Step 2: Compute `isDeleted` and mark the card as a stamp container**

Current (`StandardDetailPage.tsx:832-846`):

```tsx
          {docs.map((doc) => {
            const typeLabel = mimeTypeLabel(doc.mime_type);
            const badgeClass =
              MIME_BADGE_COLORS[typeLabel] ?? "bg-foreground/10 text-muted-foreground border-border";
            const isCurrent = doc.is_current;

            return (
              <div
                key={doc.id}
                className={`flex items-center gap-4 rounded-xl border p-4 transition-colors
                  ${isCurrent
                    ? "border-border bg-foreground/4 hover:bg-foreground/6"
                    : "border-border/50 bg-foreground/2 opacity-60 hover:opacity-80"
                  }`}
              >
```

Change to:

```tsx
          {docs.map((doc) => {
            const typeLabel = mimeTypeLabel(doc.mime_type);
            const badgeClass =
              MIME_BADGE_COLORS[typeLabel] ?? "bg-foreground/10 text-muted-foreground border-border";
            const isCurrent = doc.is_current;
            const isDeleted = Boolean(doc.deleted_at);

            return (
              <div
                key={doc.id}
                className={`relative overflow-hidden flex items-center gap-4 rounded-xl border p-4 transition-colors
                  ${isCurrent
                    ? "border-border bg-foreground/4 hover:bg-foreground/6"
                    : "border-border/50 bg-foreground/2 opacity-60 hover:opacity-80"
                  }`}
              >
                {isDeleted && (
                  <div className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden">
                    <span className="rotate-[-12deg] select-none rounded border-4 border-red-500/70 px-4 py-1
                                      text-xl font-extrabold uppercase tracking-widest text-red-500/70">
                      Deleted
                    </span>
                  </div>
                )}
```

Only these two spots change: the `const isCurrent = doc.is_current;` line gains a sibling `isDeleted` line, the outer `<div>`'s className gains `relative overflow-hidden`, and the stamp `<div>` is inserted as the first child — everything else in the card (file icon, filename, badges, action buttons) is unchanged and stays exactly where it is after this inserted block.

- [ ] **Step 3: Verify — type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors (in particular, no "Property 'deleted_at' is missing" or "does not exist" errors touching `Document`/`StandardDetailPage.tsx`).

- [ ] **Step 4: Verify — manual browser check**

With the stack running (`docker compose up -d`, frontend at `http://localhost:5173`):

1. Open a standard with at least one document, or upload one.
2. As an admin, delete that document version (trash icon) → confirm the card now shows a diagonal red "Deleted" stamp, and the row is still dimmed as before (existing `opacity-60` treatment for non-current rows is untouched).
3. Confirm the download button on that stamped card still works (click it, file downloads) — the stamp must not block it.
4. Upload a new version of a different, non-deleted document (superseding its previous version) → confirm the now-superseded old version shows the existing dimmed "archived" look with **no** stamp.
5. Log in as a non-admin viewer (or check without the admin-only delete button rendering) → confirm the stamp is still visible, but no delete button — matches the "everyone sees it" decision.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/documents.ts frontend/src/pages/StandardDetailPage.tsx
git commit -m "feat: show a Deleted watermark on explicitly deleted document versions"
```
