# ISO Standards Tracking System (ISTS)

Automated discovery, monitoring, and management of ISO technical committee standards.

**Stack:** FastAPI · PostgreSQL 16 · Celery 5 · Redis 7 · React + Vite · Docker Compose

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

# 5. Open API docs
# http://localhost:8000/docs
```

---

## Common Commands

| Command | Description |
|---|---|
| `make up` | Build images and start all 6 containers |
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
| FastAPI (web) | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| React dev server | http://localhost:5173 (M3) |

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
├── backend/            FastAPI app, Celery workers, Alembic migrations
├── frontend/           React + Vite SPA (scaffold in M3)
├── docker/             Supplementary Docker assets (nginx, etc.)
├── .github/workflows/  CI/CD pipelines
├── docker-compose.yml  Local dev orchestration (6 services)
├── .env.example        Environment variable template
└── Makefile            Dev workflow shortcuts
```

## Milestone Build Order

| Milestone | Status | Scope |
|---|---|---|
| **M1 — Foundation** | ✅ Complete | Docker Compose, FastAPI skeleton, DB schema, JWT auth, User CRUD |
| M2 — Feed Engine | ⬜ | RSS polling, Celery tasks, standard_history |
| M3 — Core UI | ⬜ | React + Vite, Dashboard, Standards list |
| M4 — Documents | ⬜ | Upload, versioning, StorageBackend |
| M5 — Notifications | ⬜ | In-app + email, distribution lists |
| M6 — Audit & Polish | ⬜ | Audit log, worker health, e2e tests |
| M7 — AWS Deployment | ⬜ | ECS, RDS, S3, ALB, CI/CD |
