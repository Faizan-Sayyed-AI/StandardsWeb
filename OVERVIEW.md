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
  manual polls, mark standards as purchased.
- **Viewer** — read-only access to the standards library and documents.

## How it works, end to end

1. **Feed ingestion.** An admin registers an RSS feed per standards committee (e.g. ISO/TC
   210) with a polling schedule (daily/weekly, at a chosen UTC hour).
2. **Change detection.** New standards are inserted; existing ones that changed stage/status
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

## Stack

**Backend:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Celery 5 + Redis, PostgreSQL 16,
`celery-sqlalchemy-scheduler`, JWT auth (python-jose + passlib/bcrypt), structlog.
**Frontend:** React 19 + Vite, TypeScript, Tailwind CSS, Radix UI primitives, TanStack
Query, React Router.

