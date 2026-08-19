# StandardSphere — Application Overview

StandardSphere is a web application that automates the discovery, tracking, and lifecycle
management of technical standards (ISO, IEC, IEEE, ASTM, and others) for an organization
that needs to know reliably and without manual checking  when a standard it relies
on is revised, withdrawn, or replaced.

## What problem it solves

Teams that depend on published standards (medical devices, manufacturing, compliance) have
historically tracked changes by hand someone periodically checks standards-body websites, cross-references a spreadsheet, and emails the relevant people. This doesn't
scale, is error-prone, and has no audit trail. StandardSphere replaces that manual loop with
a scheduled background pipeline, a searchable single source of truth (Using AI Tagging), and automatic
notifications while keeping a full history of every change and who did what.

## Who uses it

Three roles, enforced on both the API and the UI:

- **Admin** — full control: manage feeds, schedules, users, distribution lists, SMTP
  settings, document-tagging configuration; sees audit logs.
- **Manager** — day-to-day standards work: create/edit standards, upload documents, trigger
  manual polls (If needed), mark standards as purchased.
- **Viewer** — read-only access to the standards library and documents.

## How it works, end to end

1. **Feed ingestion.** An admin registers an RSS feed per standards committee (e.g. ISO/TC
   210) with a polling schedule (daily/weekly, at a chosen UTC hour).
2. **Change detection.** New standards are inserted; existing ones that changed stage
   get a new row in the standard's history with a full before/after snapshot nothing is
   overwritten, so the timeline is always reconstructable.
3. **Notifications.** When a standard changes, in-app notifications and (optionally) email
   go out to users or distribution lists mapped to that event type.
4. **Documents.** Managers can upload the actual standard PDF/DOCX/XLSX per version. An
   AI tagging service is called to auto-classify each document
   (subject, methods, department, a plain-language summary) so the library stays
   searchable beyond just the reference number.
5. **Everything is audited.** Every create/update/delete of a standard, feed, user, or
   config touches the audit log with actor, IP, and a before/after payload.

--- 

**Stack:** FastAPI · PostgreSQL 16 · Celery 5 + Beat · Redis 7 · React 19 + Vite 

## Current State

- **Auth & users** — JWT login, role-based access (admin / manager / viewer), user CRUD.
  Access token held in memory only; refresh token in an httpOnly cookie
- **Standards library** — search, filter by committee/body/stage/status, version grouping,
  manual entry for standards bodies without automation. Filters persist in the URL
- **Feed engine** — per-committee RSS polling on a configurable cron schedule via Celery
  Beat, full change-history timeline per standard
- **API key pool** — feeds distributed across multiple rss2json keys with per-key capacity,
  health tracking (`active` / `rate_limited` / `expired` / `disabled`), and reassignment
- **Documents** — upload/version/download per standard (S3), async AI-based
  auto-tagging via an admin-configurable external service
- **Purchase gating** — draft-stage standards (ISO stage < 60, i.e. CD/WD/AWI) cannot be
  uploaded to or marked purchased; purchase unlocks only once a document exists. Enforced
  server-side, not just in the UI
- **Notifications** — in-app + email, distribution lists mapped to event types, SMTP
  configurable from the UI (MailHog in local dev)
- **Audit log** — every mutating action recorded with actor, IP, and before/after payload
- **Light/dark theming** across the full frontend


---

## How change detection works

Every poll compares the incoming feed entry against what is already stored, so only real
changes are recorded.

Each RSS entry is reduced to a SHA-256 fingerprint of its title, link, published and updated
dates, and the first 500 characters of its description. That fingerprint is compared with the
`content_hash` saved on the matching standard coressponting to the stages chneged with in the feed:

| Comparison | Outcome |
|---|---|
| No standard with this reference | **new** — standard created |
| Fingerprint matches the stored one | **skipped** — nothing changed, no history, no notification |
| Fingerprint differs | **changed** — classified as `updated`, `amended`, `withdrawn` or `replaced` |

On a change, a `standard_history` row is appended holding a full before/after snapshot, the
standard is updated, and a notification is dispatched. History is append-only nothing is
overwritten, so the timeline can always be replayed.


---

---

## Project Structure

```
StandardsWeb/
├── backend/
│   ├── app/
│   │   ├── api/v1/       REST endpoints (auth, standards, feeds, api-keys, documents,
│   │   │                 notifications, distribution-lists, users, dashboard, admin)
│   │   ├── models/       SQLAlchemy models (standards, history, feeds, api keys, documents,
│   │   │                 users, notifications, audit log, celery schedules)
│   │   ├── services/     Business logic per domain (one service per model area)
│   │   ├── tasks/        Celery tasks: feeds, documents, notifications, maintenance
│   │   ├── core/         Cross-cutting: security, crypto, storage backends, iso_stages,
│   │   │                 email, logging, middleware, config helpers
│   │   └── celery_app.py Celery app + Beat scheduler wiring
│   ├── alembic/versions/ Database migrations (0001 … 0013)
│   └── scripts/          One-off maintenance/backfill scripts
├── frontend/
│   └── src/
│       ├── pages/         One page per feature (Standards, Feeds, Schedule, Users,
│       │                   Distribution Lists, SMTP Settings, Document Tagging,
│       │                   Audit Logs, Dashboard, Standard Detail, Login)
│       ├── components/    Shared UI: Sidebar, Layout, NotificationBell, ui/ primitives
│       ├── api/           Typed API client functions (axios)
│       └── contexts/      Auth + Toast React contexts
├── scripts/               Operational scripts (db-sync, bulk standard creation)
├── docs/superpowers/      Design specs and implementation plans
├── docker-compose.yml     Local dev orchestration (7 services: web, worker, beat, db,
│                           redis, frontend, mailhog)
├── .env.example           Development environment template
├── .env.production.example Production environment template (annotated)
└── Makefile               Dev workflow shortcuts
```

`Standards/` (bulk source PDFs) and all `*.sql` dumps are gitignored — they hold licensed
documents and real user data.

---

`Developer: Faizan Sayyed `
`Project Manager : Anit Despande `