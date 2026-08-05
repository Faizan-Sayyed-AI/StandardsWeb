# StandardSphere

Automated discovery, monitoring, and management of ISO/IEC/IEEE/ASTM technical standards —
RSS feed polling, change history, document storage with AI tagging, notifications, and a
full audit trail. See **[OVERVIEW.md](./OVERVIEW.md)** for a short, non-technical walkthrough
of what the application does end to end.

**Stack:** FastAPI · PostgreSQL 16 · Celery 5 + Beat · Redis 7 · React 19 + Vite · Docker Compose (dev)

---

## Prerequisites

| Tool | Minimum version |
|---|---|
| Docker Desktop | 4.x |
| Docker Compose | v2 (bundled with Docker Desktop) |
| GNU Make | any (via Git Bash / WSL on Windows) |
| Python | 3.12 (only if running locally outside Docker) |

---

## Quick Start

```bash
# 1. Copy and edit environment variables
cp .env.example .env
# Edit .env — at minimum change SECRET_KEY and API_KEY_ENCRYPTION_KEY

# 2. Start all services
make up

# 3. Apply database migrations
make migrate

# 4. Seed the default admin user (admin@ists.local / Admin1234!)
make seed

# 5. Add at least one RSS API key — see "Feeds and API keys" below.
#    Feed creation FAILS without one.

# 6. Open the app
# Frontend: http://localhost:5173
# API docs: http://localhost:8000/docs
```

> **Step 5 is not optional.** Every RSS feed must be assigned to an API key, so
> `POST /feeds` returns *"All active API keys are at capacity"* until a key exists.

---

## Feeds and API keys

Feeds are polled through [rss2json.com](https://rss2json.com), and **each API key can serve
at most 25 distinct feed URLs** — a limit on the *account*, not a rate limit. Once a key's 25
slots are used, any new URL returns HTTP 429 permanently. The `api_keys` table therefore holds
a pool of keys, and each feed is assigned to exactly one of them.

Add a key (values are Fernet-encrypted at rest, so this must go through the API, never SQL):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ists.local","password":"Admin1234!"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/v1/api-keys \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"label":"key-1","key_value":"<your rss2json key>","capacity":25}'
```

Then assign any feeds that have no key yet:

```bash
docker compose exec web python scripts/backfill_api_keys.py
```

Operational notes:

- **`capacity` must match the real plan limit (25).** Setting it higher lets more feeds pile
  onto one key than rss2json will serve, and the surplus feeds fail permanently.
- A key that hits 429 is marked `rate_limited` and **skipped** — feeds on it stop polling
  until it recovers on the next successful call, or is reset via `PATCH /api-keys/{id}`.
- With more feeds than one key allows, add more keys. `n` keys × 25 = total capacity.
- Assignment is least-loaded-first. When migrating existing feeds, keep a key's
  *already-registered* URLs on that key — moving them elsewhere makes them 429.

---

## Configuration

Settings come from three separate places, which is worth knowing before hunting for a value:

| Where | What lives there | How to change it |
|---|---|---|
| **Env file** | `DATABASE_URL`, `SECRET_KEY`, `API_KEY_ENCRYPTION_KEY`, storage/S3, CORS, rate limits | edit file → **restart** |
| **`system_config` table** | SMTP settings, AI document-tagging URL + key | admin UI or `PATCH /admin/*-config` → live |
| **`api_keys` table** | rss2json keys (encrypted) | `POST /api-keys` → live |

Env files load in this order, later winning:

```
defaults  <  .env  <  .env.<APP_ENV>  <  real environment variables
```

`.env.<APP_ENV>` is only read when `APP_ENV` is set in the process environment
(e.g. `APP_ENV=production` loads `.env.production`). With `APP_ENV` unset only `.env` is read.
See **[.env.production.example](./.env.production.example)** for a fully annotated template.

> `SMTP_*` in an env file is only a **fallback**. Once SMTP is saved from the admin UI, the
> database row wins and the env values are ignored. Check which is in effect with
> `GET /api/v1/admin/smtp-config`.

### Document storage

`STORAGE_BACKEND=local` writes to `LOCAL_STORAGE_PATH`; `STORAGE_BACKEND=s3` writes to
`S3_BUCKET_NAME` under the optional `S3_PREFIX`. Keys are stored as
`<standard-id>/<version>_<filename>` and are **backend-agnostic** — the same database row
works for either backend, so switching needs no migration (only moving the files).

S3 mode requires `boto3` (declared in `requirements.txt`) and a bucket **CORS rule** allowing
`GET` from the frontend origin — downloads follow a 307 redirect to a presigned URL via XHR,
so without CORS they fail in the browser while `curl` still works.

---

## Common Commands

| Command | Description |
|---|---|
| `make up` | Build images and start all 7 containers |
| `make down` | Stop and remove all containers |
| `make logs` | Follow web + worker + beat logs |
| `make migrate` | Apply pending Alembic migrations |
| `make revision MSG="..."` | Auto-generate a new migration |
| `make seed` | Insert default admin user |
| `make lint` / `make format` | Run / apply ruff |
| `make typecheck` | Run mypy |
| `make test` | Run pytest (**no tests exist yet**) |
| `make shell` / `make bash` | Python REPL / bash in the web container |

### Maintenance scripts

| Script | Purpose |
|---|---|
| `backend/scripts/seed.py` | Create the default admin user |
| `backend/scripts/backfill_api_keys.py` | Assign feeds with no API key; reports how many more keys are needed |
| `backend/scripts/backfill_base_reference.py` | Recompute `base_reference` for version grouping |
| `backend/scripts/backfill_standards_body.py` | Populate `standards_body` on existing rows |
| `backend/scripts/backfill_celery_beat_schedules.py` | Rebuild Beat entries for all active feeds |
| `scripts/create_missing_standards.py` | Bulk-create standards from an embedded list (`--dry-run` supported) |
| `scripts/db-sync.sh` | Pull a database dump from a server into local Docker |

---

## Service Ports (local dev)

| Service | Port |
|---|---|
| React dev server (frontend) | http://localhost:5173 |
| FastAPI (web) | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| MailHog (dev email capture) | http://localhost:8025 (UI) / 1025 (SMTP) |

---

## Default Credentials (after `make seed`)

| Field | Value |
|---|---|
| Email | `admin@ists.local` |
| Password | `Admin1234!` |
| Role | admin |

> **Change this password immediately in any shared or production environment.** It is
> published in this file, so any deployment still using it is effectively unauthenticated.

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

## Current State

- ✅ **Auth & users** — JWT login, role-based access (admin / manager / viewer), user CRUD.
  Access token held in memory only; refresh token in an httpOnly cookie
- ✅ **Standards library** — search, filter by committee/body/stage/status, version grouping,
  manual entry for standards bodies without an RSS feed. Filters persist in the URL
- ✅ **Feed engine** — per-committee RSS polling on a configurable cron schedule via Celery
  Beat, full change-history timeline per standard
- ✅ **API key pool** — feeds distributed across multiple rss2json keys with per-key capacity,
  health tracking (`active` / `rate_limited` / `expired` / `disabled`), and reassignment
- ✅ **Documents** — upload/version/download per standard (local disk or S3), async AI-based
  auto-tagging via an admin-configurable external service
- ✅ **Purchase gating** — draft-stage standards (ISO stage < 60, i.e. CD/WD/AWI) cannot be
  uploaded to or marked purchased; purchase unlocks only once a document exists. Enforced
  server-side, not just in the UI
- ✅ **Notifications** — in-app + email, distribution lists mapped to event types, SMTP
  configurable from the UI (MailHog in local dev)
- ✅ **Audit log** — every mutating action recorded with actor, IP, and before/after payload
- ✅ **Light/dark theming** across the full frontend
- ⬜ **Automated test suite** — not yet written (`make test` is wired up, no tests exist)
- ⬜ **Password-reset email** — `app/core/email.py` is still a stub that only *logs* the reset
  link; "Forgot password" sends nothing. Notification email (a separate code path) does work
- ⬜ **CI** — no pipeline configured

> Schedule times throughout the app (feed polling, Beat) are in **UTC**, not local time.

---

## Deployment

**[DEPLOYMENT.md](./DEPLOYMENT.md) is out of date** and describes a Docker Compose + nginx
architecture. The live production deployment uses **systemd services on EC2 with no Docker and
no nginx** (an ALB forwards directly to uvicorn on port 8000). Treat that document as
historical until it is rewritten; the authoritative record is the deployment report kept with
the operations team.
