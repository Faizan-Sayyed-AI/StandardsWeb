# StandardSphere — Application Overview

StandardSphere is a web application that automates the discovery, tracking, and lifecycle
management of technical standards (ISO, IEC, IEEE, ASTM, and others) for an organization
that needs to know — reliably and without manual RSS-checking — when a standard it relies
on is revised, withdrawn, or replaced.

## What problem it solves

Teams that depend on published standards (medical devices, manufacturing, compliance) have
historically tracked changes by hand: someone periodically checks standards-body websites
or RSS feeds, cross-references a spreadsheet, and emails the relevant people. This doesn't
scale, is error-prone, and has no audit trail. StandardSphere replaces that manual loop with
a scheduled background pipeline, a searchable single source of truth, and automatic
notifications — while keeping a full history of every change and who did what.

## Who uses it

Three roles, enforced on both the API and the UI:

- **Admin** — full control: manage feeds, schedules, users, distribution lists, SMTP
  settings, document-tagging configuration; sees audit logs.
- **Manager** — day-to-day standards work: create/edit standards, upload documents, trigger
  manual polls, mark standards as purchased.
- **Viewer** — read-only access to the standards library and documents.

## How it works, end to end

1. **Feed ingestion.** An admin registers an RSS feed per standards committee (e.g. ISO/TC
   210) with a polling schedule (daily/weekly, at a chosen UTC hour). A Celery task fetches
   and parses the feed, extracts the standard reference, stage, status, and committee, and
   diffs it against what's already stored.
2. **Change detection.** New standards are inserted; existing ones that changed stage/status
   get a new row in the standard's history with a full before/after snapshot — nothing is
   overwritten, so the timeline is always reconstructable.
3. **Notifications.** When a standard changes, in-app notifications and (optionally) email
   go out to users or distribution lists mapped to that event type.
4. **Documents.** Managers can upload the actual standard PDF/DOCX/XLSX per version. An
   external AI tagging service is called asynchronously to auto-classify each document
   (subject, methods, department, a plain-language summary) so the library stays
   searchable beyond just the reference number.
5. **Everything is audited.** Every create/update/delete of a standard, feed, user, or
   config touches the audit log with actor, IP, and a before/after payload.

## Scheduling, precisely

Feed polling runs on Celery Beat, reading cron-style schedules materialized into
`celery-sqlalchemy-scheduler`'s own tables (a small bridge module keeps the app's
human-editable schedule config in sync with what Beat actually reads). All schedule times
are **UTC**. A lightweight worker heartbeat task and periodic cleanup jobs run the same way.

## System shape

```
React SPA  ──HTTP──▶  FastAPI (JWT auth, role checks)  ──▶  PostgreSQL
                              │                              ▲
                              ├─ enqueues ──▶  Redis (broker) │
                              │                     │          │
                              │                     ▼          │
                              │              Celery worker ─────┘
                              │              (feeds / docs / notifications / maintenance queues)
                              │                     ▲
                              └─ schedules ──▶ Celery Beat ─────┘
```

Seven containers in local dev: `web` (FastAPI), `worker`, `beat`, `db` (Postgres 16),
`redis`, `frontend` (Vite dev server), and `mailhog` (catches outgoing email locally).

## Stack

**Backend:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Celery 5 + Redis, PostgreSQL 16,
`celery-sqlalchemy-scheduler`, JWT auth (python-jose + passlib/bcrypt), structlog.
**Frontend:** React 19 + Vite, TypeScript, Tailwind CSS, Radix UI primitives, TanStack
Query, React Router, Recharts.
**Infra:** Docker Compose for local dev; designed to move to AWS (ECS/RDS/S3/ALB) per
`DEPLOYMENT.md`.

## Where to go next

- **README.md** — get it running locally in five commands.
- **ISTS_PRD.md** — full product requirements, data model, and API design.
- **AUTOMATION.md** — how the Celery/Beat scheduling pipeline actually works.
- **DEPLOYMENT.md** — the AWS production deployment plan.
