# StandardSphere

Automated discovery, monitoring, and management of ISO/IEC/IEEE/ASTM technical standards —
RSS feed polling, change history, document storage with AI tagging, notifications, and a
full audit trail. See **[OVERVIEW.md](./OVERVIEW.md)** for a short, non-technical walkthrough
of what the application does end to end.

**Stack:** FastAPI · PostgreSQL 16 · Celery 5 + Beat · Redis 7 · React 19 + Vite · Docker Compose

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
# Edit .env — at minimum change SECRET_KEY

# 2. Start all services
make up

# 3. Apply database migrations
make migrate

# 4. Seed the default admin user (admin@ists.local / Admin1234!)
make seed

# 5. Open the app
# Frontend: http://localhost:5173
# API docs: http://localhost:8000/docs
```

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
| `make lint` | Run ruff linter |
| `make test` | Run pytest |
| `make shell` | Open Python REPL in the web container |

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

> **Change this password immediately in any shared or production environment.**

---

## Project Structure

```
Standards_Version_Control_Project/
├── backend/
│   ├── app/
│   │   ├── api/v1/       REST endpoints (auth, standards, feeds, documents,
│   │   │                 notifications, distribution-lists, users, dashboard, admin)
│   │   ├── models/       SQLAlchemy models (standards, history, feeds, documents,
│   │   │                 users, notifications, audit log, celery schedules)
│   │   ├── services/     Business logic per domain (one service per model area)
│   │   ├── tasks/        Celery tasks: feeds, documents, notifications, maintenance
│   │   ├── core/         Cross-cutting: security, storage backend, email, config
│   │   └── celery_app.py Celery app + Beat scheduler wiring
│   ├── alembic/versions/ Database migrations
│   └── scripts/          One-off maintenance/backfill scripts
├── frontend/
│   └── src/
│       ├── pages/         One page per feature (Standards, Feeds, Schedule, Users,
│       │                   Distribution Lists, SMTP Settings, Document Tagging,
│       │                   Audit Logs, Dashboard, Standard Detail, Login)
│       ├── components/    Shared UI: Sidebar, Layout, NotificationBell, ui/ primitives
│       ├── api/           Typed API client functions (axios)
│       └── contexts/      Auth + Toast React contexts
├── docker/             Supplementary Docker assets (nginx, etc.)
├── .github/workflows/  CI/CD pipelines
├── docker-compose.yml  Local dev orchestration (7 services: web, worker, beat, db,
│                        redis, frontend, mailhog)
├── .env.example        Environment variable template
└── Makefile            Dev workflow shortcuts
```

## Current State

The application is feature-complete for local development and in active use:

- ✅ **Auth & users** — JWT login, role-based access (admin / manager / viewer), user CRUD
- ✅ **Standards library** — search, filter by committee/body/stage/status, version grouping,
  manual entry for standards bodies without an RSS feed
- ✅ **Feed engine** — per-committee RSS polling on a configurable cron schedule via Celery
  Beat, full change-history timeline per standard
- ✅ **Documents** — upload/version/download per standard, async AI-based auto-tagging
  (admin-configurable external tagging service)
- ✅ **Notifications** — in-app + email, distribution lists mapped to event types, SMTP
  configurable from the UI (MailHog in local dev)
- ✅ **Audit log** — every mutating action recorded with actor, IP, and before/after payload
- ✅ **Light/dark theming** across the full frontend
- ⬜ **Automated test suite** — not yet written (`make test` is wired up, no tests exist yet)
- ⬜ **AWS deployment** — planned, see `DEPLOYMENT.md` (currently Docker Compose only)

> Schedule times throughout the app (feed polling, Beat) are in **UTC**, not local time.
