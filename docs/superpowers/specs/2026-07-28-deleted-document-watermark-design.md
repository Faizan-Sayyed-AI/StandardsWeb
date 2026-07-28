# Deleted Document Watermark

## Context

`DELETE /documents/{id}` already soft-deletes a document version (`soft_delete_document()`,
`app/services/document_service.py:333`): it sets `is_current=False` and writes an audit log; the
row is never removed and the file stays in storage. `list_documents()` returns every version for
a standard regardless of `is_current`, so a deleted version doesn't disappear from the UI — it
stays in the list, rendered dimmed (`opacity-60`, no "Current" badge) by
`StandardDetailPage.tsx:836-845`, and counted in the "N archived" footer.

The problem: `is_current=False` is set for two different reasons that look identical today — an
admin explicitly deleted that version (trash icon), or it was simply superseded when someone
uploaded a newer version of the same document. There is currently no visible, unambiguous signal
that a specific version was *deleted* rather than just superseded.

This spec adds an explicit "Deleted" watermark to a document's card, shown only for versions that
were actually deleted — not for ordinary superseded old versions.

## Decisions (user-confirmed)

- **Scope**: the watermark appears only on versions explicitly removed via the trash/delete
  action, not on every non-current version. Requires distinguishing "deleted" from "superseded"
  in the data model, since both currently collapse into `is_current=False`.
- **Data model**: add a `deleted_at` timestamp column (Approach A of three considered — see
  "Approaches considered" below), rather than inferring deletion from the audit log or adding a
  plain boolean with no timestamp.
- **Visibility**: everyone who can view the standard sees the watermark (viewers, managers,
  admins) — consistent with the document list already showing all versions to anyone with access.
- **Actions**: purely visual. Download, retry-tagging, and delete buttons keep working exactly as
  they do today on a deleted row. No restore/undo action is added.
- **Visual style**: a diagonal red "DELETED" stamp across the whole card, rubber-stamp style —
  not a badge/pill, not a full-card tint.

## Approaches considered

1. **`deleted_at: TIMESTAMPTZ NULL` column (chosen).** Soft-delete sets it; supersession never
   touches it. One nullable column, deletion state lives as real document state (not derived),
   and it gives a "deleted N days ago" tooltip almost for free if ever wanted later.
2. **Infer from the audit log** (`document.deleted` action is already written on every delete).
   No migration, but means joining/querying audit logs on every document-list fetch — slower, and
   audit logs aren't designed as a live-state source of truth for this kind of per-row check.
3. **Plain `is_deleted` boolean, no timestamp.** Simplest possible column, but discards "when"
   information for no real savings over option 1.

## Data model

New migration `0014_add_document_deleted_at.py` (current head is `0013_add_api_keys.py`):

```python
op.add_column('documents', sa.Column(
    'deleted_at', sa.DateTime(timezone=True), nullable=True,
    comment="Set only by an explicit soft-delete, never by version supersession — "
            "distinguishes 'deleted' from merely 'not the current version'."
))
```

No backfill: existing rows are all `NULL`, i.e. "not deleted," which is correct — nothing already
soft-deleted before this column existed should retroactively show the watermark.

`app/models/document.py`: add

```python
deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`app/services/document_service.py`, `soft_delete_document()` (line ~348): alongside the existing
`doc.is_current = False`, add `doc.deleted_at = datetime.now(timezone.utc)`.

## Backend API

`app/schemas/document.py`, `DocumentResponse`: add `deleted_at: datetime | None`. No other schema
or endpoint changes — `DocumentResponse.model_validate(d)` (`app/api/v1/documents.py:68`) already
picks up ORM attributes via `from_attributes=True`, and `download`/`retag`/`delete` all continue
to operate on `document_id` regardless of deletion state, matching the "actions stay as-is"
decision. No restore endpoint is added.

## Frontend

`frontend/src/api/documents.ts`, `Document` interface: add `deleted_at: string | null;`.

`frontend/src/pages/StandardDetailPage.tsx`, in the document-row render (~line 832 onward):

- Compute `const isDeleted = Boolean(doc.deleted_at);` alongside the existing `const isCurrent = doc.is_current;`.
- Add `relative overflow-hidden` to the card's outer `<div>` className (needed so the stamp can be
  absolutely positioned and clipped to the card bounds).
- When `isDeleted`, render a stamp overlay as a sibling inside that div:

```tsx
{isDeleted && (
  <div className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden">
    <span className="rotate-[-12deg] select-none rounded border-4 border-red-500/70 px-4 py-1
                      text-xl font-extrabold uppercase tracking-widest text-red-500/70">
      Deleted
    </span>
  </div>
)}
```

- `pointer-events-none` ensures the stamp never blocks clicks on the download/retag/delete
  buttons underneath.
- This sits on top of the existing dimmed (`opacity-60`) treatment for non-current rows: an
  explicitly-deleted row is dimmed *and* stamped; a merely-superseded old version stays dimmed
  with no stamp, exactly as today.
- All other `is_current`-driven logic (the "Current" badge, the "N archived" footer count) is
  unchanged — that logic is about version currency, not deletion, and stays keyed off
  `is_current` as it already is.

## Error handling & edge cases

- A version can be both the "current" one and deleted at the same time if an admin deletes the
  current version without uploading a replacement first — this is pre-existing behavior
  (the delete button isn't gated on `isCurrent` today) and out of scope to change. In that case
  the card would show both the "Current" badge and the "Deleted" stamp simultaneously, which is
  accurate: it is the current version, and it has been deleted.
- Re-deleting an already-deleted row (the trash button isn't hidden after deletion, per the
  "keep actions as-is" decision) is idempotent: `deleted_at` is simply overwritten with a newer
  timestamp.

## Testing

No automated test suite exists anywhere in this repo (backend or frontend) at present, so this
ships with manual verification:

1. Upload a document, delete it → the diagonal "Deleted" stamp appears immediately (the existing
   delete mutation already invalidates the query cache), download/retag buttons still work.
2. Upload a second version over an existing one (superseding the first) → the superseded version
   shows the existing dimmed "archived" look with **no** stamp.
3. Reload as a non-admin viewer → the stamp is still visible, but no delete button.
4. `SELECT id, is_current, deleted_at FROM documents WHERE ...` after each step to confirm
   `deleted_at` is set only by explicit delete, never by supersession.

## Out of scope (explicitly deferred)

- Restore/undo for a deleted version.
- Disabling download/retry-tagging on a deleted row.
- A "deleted N days ago" tooltip (the `deleted_at` timestamp makes this cheap later, but it's not
  requested now).
- Filtering deleted versions out of the list for any role — everyone continues to see all
  versions, deleted or not.
