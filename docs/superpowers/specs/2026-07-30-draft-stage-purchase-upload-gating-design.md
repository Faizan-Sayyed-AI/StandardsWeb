# Draft-stage gating for document upload and purchase

**Date:** 2026-07-30
**Status:** Approved, ready for implementation plan

## Context

Standards enter the catalogue at every point in the ISO lifecycle, including
pre-publication drafts (committee drafts, working drafts, approved work items).
A draft cannot be bought — there is no published document to buy — yet the UI
currently offers "Mark as Purchased" and "Upload Document" on every standard
regardless of stage. Both actions are also unguarded on the API.

Separately, "purchased" is meant to record that the organisation *holds* the
document. Today a standard can be marked purchased with no document attached,
so the flag can drift from reality.

Two rules follow:

1. A standard at a draft stage offers neither document upload nor purchase.
2. Purchase becomes available only once a document has been successfully
   uploaded.

Data as of the 2026-07-30 production snapshot (3,283 standards): 249 are at a
draft stage, 8 have a document, 2 are purchased. Both purchased standards are
published *and* already have a document, so no existing row violates either
rule — this change needs no data migration.

## The draft rule

A standard is a draft when its ISO `stage_code` major number is below 60.

| Stage | Meaning | Count | Gated |
|---|---|---|---|
| 10 | Preliminary / proposal | 23 | yes |
| 20 | Working draft (WD) | 90 | yes |
| 30 | Committee draft (CD) | 134 | yes |
| 40 | DIS | 2 | yes |
| 60 | Published | 504 | no |
| 90 | Reviewed / confirmed | 1,154 | no |
| 95 | Withdrawn | 1,376 | no |

Stage code is used rather than the reference prefix (`ISO/CD`, `ISO/WD`,
`ISO/AWI`) because it is ISO's own lifecycle model and is strictly more
accurate on real data: it catches all 244 standards the prefix catches, plus 5
plain-named standards that are mid-revision at stage 20/30 and which a prefix
match misses. There are zero cases where the prefix says draft but the stage
says published. `ISO/TS`, `ISO/TR` and `ISO/PAS` remain purchasable — they are
published deliverables, and the stage rule treats them correctly.

`stage_code` is populated for all 3,283 existing standards. When it is absent
(possible for a manually created standard) the standard is treated as **not** a
draft, so manual entries are never silently locked out.

## Architecture

The backend owns the rules and exposes the outcome; the frontend renders it and
contains no stage logic of its own.

This matters for two concrete reasons:

- The purchase button lives in the page's parent component, while documents are
  fetched separately inside `DocumentsTab` (`["documents", standardId]`). The
  button therefore has no access to the document count. A server-derived flag
  removes the need to restructure the component tree or duplicate the query.
- A frontend rebuild is planned. Rules expressed as API fields carry over to a
  new UI unchanged; rules expressed as TypeScript do not.

### Derived fields on `StandardDetail`

| Field | Type | Meaning |
|---|---|---|
| `is_draft` | bool | stage major < 60 |
| `document_count` | int | documents with `is_current = True` |
| `can_upload` | bool | `not is_draft` |
| `can_purchase` | bool | `not is_draft` and `document_count > 0` and not already purchased |
| `purchase_blocked_reason` | str \| None | short user-facing sentence; `None` when not blocked |

`document_count` counts only `is_current = True`. Soft-deleting a document sets
`is_current = False` (`document_service.soft_delete_document`), so a deleted
document must not keep purchase unlocked.

`can_purchase` is false for an already-purchased standard, since the action
would be a no-op. The UI continues to branch on `is_purchased` to render the
purchased state, exactly as it does now.

Reason strings:

- draft: `"Not available — standard is still at draft stage ({stage_code} {stage_name}). Available once published."`
- no document: `"Upload the standard document before marking it as purchased."`
- already purchased: `None`

## Components

### New: `backend/app/core/iso_stages.py`

```python
def is_draft_stage(stage_code: str | None) -> bool:
    """True when the ISO stage code is pre-publication (major < 60)."""
```

A dependency-free helper. It lives in `core/` rather than being imported from
`app/tasks/feeds.py`, which already holds stage tables but is a Celery task
module that services should not import. Migrating `_STAGE_STATUS_MAP` and
`_STAGE_NAME_MAP` here later is a natural follow-up but is out of scope.

### `backend/app/services/standard_service.py`

Add:

```python
async def get_purchasability(standard: Standard, db: AsyncSession) -> dict
```

Returns the five derived fields above. It must be an `async` function that
takes the session and issues its own `COUNT` — the values must **not** be
exposed as ORM properties on `Standard`, because a lazy attribute access from
synchronous code raises `MissingGreenlet` under async SQLAlchemy (see
`0211de5`, the same failure mode fixed in `api_key_service`).

Guard `purchase_standard()`, after the existing not-found and
already-purchased checks:

- draft → `AppValidationError` with the draft reason
- zero current documents → `AppValidationError` with the no-document reason

Ordering note: the existing already-purchased early return stays first, so
re-purchasing remains an idempotent no-op rather than becoming a 422.

### `backend/app/api/v1/standards.py`

All three sites that build a `StandardDetail` must populate the new fields:

| Line | Endpoint |
|---|---|
| 130 | `POST /standards` (manual create) |
| 171 | `GET /standards/{id}` |
| 239 | `POST /standards/{id}/purchase` |

Each calls `get_purchasability()` and spreads the result into the response
model, following the pattern already used for `amendments` at line 171.

### `backend/app/api/v1/documents.py`

The upload endpoint rejects a draft standard with `AppValidationError` before
any file is read or written to storage.

### Frontend

`frontend/src/api/standards.ts` — add the five fields to the `Standard` type.

`frontend/src/pages/StandardDetailPage.tsx`:

- Purchase button (~line 1109): `disabled` when `!can_purchase`, with
  `purchase_blocked_reason` rendered beneath it. Buttons stay visible and
  greyed rather than being hidden, so the rule is legible to users.
- `DocumentsTab` currently receives only `standardId`; pass `canUpload` in and
  apply it to the upload button alongside the existing role check
  (`isAdmin || isManager`). The role check and the stage check are both
  required.
- **The upload mutation's `onSuccess` must invalidate `["standard", id]` in
  addition to `["documents", standardId]`.** Without this the purchase button
  stays greyed until a manual page refresh, which is the entire point of the
  second requirement. The delete-document mutation needs the same invalidation,
  so removing the last document re-disables purchase.

## Error handling

Both guards raise `AppValidationError`, which the global handler in `main.py`
already renders as `422 {"detail": ..., "code": "VALIDATION_ERROR"}`. No new
error plumbing. The upload modal already surfaces `detail` via
`setUploadError(detail ?? …)`, so a rejected draft upload displays the reason
without further work.

## Out of scope

- Withdrawn standards (stage 95, 1,376 rows) remain purchasable.
- Deleting the last document does not un-purchase an already-purchased
  standard; it only re-disables the button for standards not yet purchased.
- No backfill or migration. No change to `rss_feeds`, polling, or the API-key
  pool.

## Verification

No automated test suite exists in this repository (`make test` is wired up but
there are no tests), so verification is manual against the restored production
snapshot, which contains every case needed.

| Case | Example available | Expected |
|---|---|---|
| Draft, no document | any of 249 drafts | upload + purchase both disabled; API returns 422 for each |
| Published, no document | any of ~3,026 | upload enabled, purchase disabled with the no-document reason |
| Published, has document | 6 unpurchased with 1 doc | both enabled; purchase succeeds |
| Already purchased | ISO 45010, ISO/IEEE 11073 | stays purchased; repeat call still a no-op, not a 422 |
| Live enablement | any published standard | upload a document and confirm the purchase button enables without a page refresh |

Direct API checks with `curl` confirm the 422s independently of the UI, since
the UI disabling a button does not prove the server enforces the rule.
