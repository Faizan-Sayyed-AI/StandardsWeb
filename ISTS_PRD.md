# ISO Standards Tracking System (ISTS)
## Product Requirements Document

| Field | Value |
|---|---|
| Version | 1.0 |
| Status | Draft |
| Date | June 2026 |
| Classification | Internal |
| Stack | FastAPI + React + PostgreSQL + Celery |
| Deployment | Local (Dev) → AWS (Prod) |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Requirements Document (PRD)](#2-product-requirements-document-prd)
3. [Functional Requirements](#3-functional-requirements)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [System Architecture](#5-system-architecture)
6. [Database Design](#6-database-design)
7. [API Design](#7-api-design)
8. [Background Job Architecture (Celery)](#8-background-job-architecture-celery)
9. [User Roles & Permissions](#9-user-roles--permissions)
10. [Notification Architecture](#10-notification-architecture)
11. [Document Storage & Versioning](#11-document-storage--versioning)
12. [Deployment Architecture](#12-deployment-architecture)
13. [Security Considerations](#13-security-considerations)
14. [Audit Logging Requirements](#14-audit-logging-requirements)
15. [Scalability Considerations](#15-scalability-considerations)
16. [Suggested Technology Stack](#16-suggested-technology-stack)
17. [Open Questions & Next Steps](#17-open-questions--next-steps)

---

## 1. Executive Summary

The ISO Standards Tracking System (ISTS) is a centralised web application that automates the discovery, monitoring, and management of ISO technical committee standards. It replaces manual RSS monitoring with scheduled background workers, provides a single source of truth for purchased and tracked standards, and delivers timely notifications to relevant stakeholders whenever a standard's status changes.

### 1.1 Problem Statement

- Standards teams manually poll 7+ ISO RSS feeds, which is error-prone and inconsistent.
- There is no central record of which standards have been purchased, who holds them, or whether they have been revised.
- Notifications about updates, withdrawals, and new publications are ad hoc and unreliable.
- Uploaded standards documents are stored in shared drives with no versioning or access control.

### 1.2 Goals

- Automate feed polling on configurable daily or weekly schedules.
- Detect and record status changes (new, updated, amended, withdrawn, replaced) automatically.
- Provide a dashboard for monitoring standards portfolios and recent events.
- Send dashboard and email notifications for all significant events.
- Act as a secure, versioned document repository for purchased standards.
- Support administrator-controlled email distribution lists.

---

## 2. Product Requirements Document (PRD)

### 2.1 Scope

ISTS covers the following domains: RSS feed management, automated standards tracking, document storage and versioning, user and role management, notification delivery, and administrative configuration.

**Out of scope for v1:** direct ISO API integration, e-commerce / purchasing workflow, mobile native apps, multi-tenancy, and ASTM standards tracking (planned for v2).

### 2.2 User Personas

| Persona | Role | Primary Need |
|---|---|---|
| System Admin | Manages users, feeds, schedules, and distribution lists | Full system control |
| Standards Manager | Tracks standards portfolio, uploads documents | Monitor changes, upload docs |
| Authorised Viewer | Views purchased standards and status dashboard | Read-only access to docs |
| Notification Recipient | Receives email alerts (may not log in) | Timely email notifications |

---

## 3. Functional Requirements

### 3.1 RSS Feed Management

- Admin can add, edit, enable/disable, and delete RSS feed URLs.
- Each feed has a configurable polling schedule: daily (specify hour) or weekly (specify day + hour).
- Feed metadata stored: URL, name, TC committee, polling schedule, last polled timestamp, last status.
- Admin can trigger an immediate manual poll for any feed.
- System retries failed polls with exponential backoff (3 attempts before marking as failed).

### 3.2 Standards Tracking

- Each RSS item is parsed and matched against existing standards by ISO reference number.
- Detected lifecycle events trigger a status update and a notification:
  - New publication detected
  - Revision or amendment published
  - Standard withdrawn
  - Standard replaced by a newer edition
  - Status change (e.g., under review, stabilised)
- Change history is appended to the standard record; no history is ever deleted.
- Standards can be manually created, edited, or archived by admins and standards managers.
- Each standard tracks: ISO reference, title, edition, TC committee, status, purchase status, last change date, feed source.

### 3.3 Purchase Management

- Admin or standards manager can mark a standard as Purchased.
- Marking a standard as purchased triggers a system-wide notification to all users and all configured distribution lists.
- Purchase record stores: purchaser name, date, cost centre (optional), licence notes.

### 3.4 Document Storage & Management

- Admins and standards managers can upload documents (PDF, DOCX, XLSX) against a standard record.
- Each upload creates a new version; prior versions are retained and accessible.
- Version metadata: version number, uploader, upload timestamp, change notes, file size, checksum (SHA-256).
- Authorised viewers can download any version of a document they have access to.
- Document upload events trigger a notification.
- Storage backend is abstracted: local filesystem in development, AWS S3 in production.

### 3.5 Dashboard

- Displays a summary of: total standards tracked, standards by status, recent events feed, pending notifications.
- Standards list is filterable and sortable by: status, TC committee, purchase status, last change date.
- Clicking a standard opens a detail view with full history, documents, and notification log.
- Admin dashboard panel shows: feed health, Celery worker status, scheduled job queue depth.

### 3.6 Notification System

- Two delivery channels: in-app (dashboard bell icon) and email.
- Notification triggers:
  - New standard published
  - Standard updated / revised / amended
  - Standard purchased
  - Standard withdrawn or replaced
  - Document uploaded or revised
  - Feed poll failure (admin only)
- Each notification has a severity: Info, Warning, or Critical.
- Users can mark notifications as read; admins can broadcast system-wide notices.
- Admin configures named distribution lists (e.g., 'Engineering Team', 'Management'); each trigger type is mapped to one or more lists.

### 3.7 User & Role Management

- Admin can create, edit, deactivate, and delete user accounts.
- Users authenticate via username + password (bcrypt); JWT tokens for API sessions.
- Password reset via email link (time-limited token).
- Admin can assign or change roles at any time.
- Deactivated users cannot log in but their audit records are preserved.

### 3.8 Admin Configuration

- SMTP server settings (host, port, username, password, TLS/SSL, sender address).
- Global feed polling defaults (fallback schedule if per-feed schedule is not set).
- Notification-to-distribution-list mappings.
- Celery beat schedule management via UI (no manual config file editing required).
- Audit log viewer with filtering by user, action type, date range.

---

## 4. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Performance | Dashboard page load < 2s; API responses < 500ms for list endpoints; document upload/download limited only by network bandwidth. |
| Availability | Local dev: no SLA. AWS prod: 99.5% uptime target using ALB + ECS auto-scaling. |
| Scalability | Designed for <25 users / <500 standards in v1. Architecture supports horizontal scaling of API and Celery workers without schema changes. |
| Reliability | Celery tasks are idempotent; feed polling failures are retried and logged. All DB writes use transactions. |
| Maintainability | 100% of configuration via environment variables. Docker Compose for local; ECS task definitions for AWS. All secrets via `.env` / AWS Secrets Manager. |
| Security | HTTPS enforced in prod (ACM). Passwords hashed with bcrypt (12 rounds). JWT expiry 8h, refresh token 7d. S3 buckets private; documents served via pre-signed URLs (15 min TTL). |
| Usability | React SPA with responsive layout for desktop and tablet. All forms have inline validation. Notification count visible on every page. |
| Observability | Structured JSON logging (structlog). Celery task success/failure events logged. Prometheus metrics endpoint on `/metrics`. Sentry integration for error tracking (optional). |
| Portability | Docker-first: all services run in containers. Docker Compose for local, ECS Fargate for AWS. |

---

## 5. System Architecture

### 5.1 Architecture Overview

ISTS uses a layered architecture with clear separation between the presentation layer (React SPA), API layer (FastAPI), task execution layer (Celery), and data layer (PostgreSQL + file storage). Redis acts as both the Celery message broker and a caching layer.

### 5.2 Component Diagram

```
[ Browser ]
     │  HTTPS / REST + WebSocket
[ React SPA (Vite) ]  ──────────────►  served by Nginx / AWS CloudFront
     │  REST API calls (Axios)
[ FastAPI Application ]  ───────────►  Uvicorn / Gunicorn workers
     ├──  SQLAlchemy ORM  ──────────►  [ PostgreSQL ]
     ├──  Celery client (task dispatch)  ►  [ Redis (broker) ]
     ├──  Storage abstraction  ──────►  [ Local FS | AWS S3 ]
     └──  Email (smtplib / aiosmtplib)  ►  [ SMTP Server ]

[ Celery Worker(s) ]  ◄──────────────  consumes from Redis
     ├──  poll_feeds task: fetches RSS, diffs against DB, fires events
     └──  send_notifications task: assembles emails, writes in-app records

[ Celery Beat ]  ──  database-backed schedule (django-celery-beat equivalent: celery-beat-sqlalchemy)
```

### 5.3 Local Development Stack (Docker Compose)

- `web` — FastAPI app (uvicorn --reload)
- `worker` — Celery worker (solo pool for dev)
- `beat` — Celery Beat scheduler
- `db` — PostgreSQL 16
- `redis` — Redis 7 (Alpine)
- `frontend` — Vite dev server (hot reload)

### 5.4 AWS Production Stack

- ECS Fargate — API service, Celery worker service, Celery Beat service (single task)
- RDS PostgreSQL (Multi-AZ for resilience)
- ElastiCache Redis (single node, cluster mode off for simplicity)
- S3 bucket (private) + CloudFront for static React assets
- ALB (Application Load Balancer) — HTTPS termination via ACM
- Secrets Manager — DB credentials, SMTP credentials, JWT secret
- ECR — Docker image registry
- CloudWatch — logs, metrics, alarms

---

## 6. Database Design

### 6.1 Entity Relationship Overview

The schema is organised around five core domains: Users & Roles, Feeds, Standards, Documents, and Notifications. The Audit Log is a separate append-only table.

### 6.2 Full Schema

#### `users`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK, default gen_random_uuid() | Primary key |
| email | VARCHAR(255) | UNIQUE, NOT NULL | Login email |
| username | VARCHAR(100) | UNIQUE, NOT NULL | Display name |
| hashed_password | VARCHAR(255) | NOT NULL | bcrypt hash |
| role | ENUM | NOT NULL | admin \| manager \| viewer |
| is_active | BOOLEAN | DEFAULT TRUE | Soft-delete flag |
| last_login | TIMESTAMPTZ | NULLABLE | Last successful login |
| created_at | TIMESTAMPTZ | DEFAULT now() | Row creation time |
| updated_at | TIMESTAMPTZ | DEFAULT now() | Last update time |

#### `rss_feeds`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| name | VARCHAR(255) | NOT NULL | Human-readable feed name |
| url | TEXT | UNIQUE, NOT NULL | RSS endpoint URL |
| tc_committee | VARCHAR(100) | NULLABLE | ISO TC committee code |
| schedule_type | ENUM | NOT NULL | daily \| weekly |
| schedule_hour | SMALLINT | 0–23 | UTC hour to run |
| schedule_day_of_week | SMALLINT | NULLABLE, 0–6 | For weekly: 0=Mon |
| is_enabled | BOOLEAN | DEFAULT TRUE | Enable/disable without deleting |
| last_polled_at | TIMESTAMPTZ | NULLABLE | Last successful poll |
| last_poll_status | ENUM | DEFAULT pending | pending\|ok\|failed |
| failure_count | SMALLINT | DEFAULT 0 | Consecutive failure counter |
| created_by | UUID | FK users.id | Creator |
| created_at | TIMESTAMPTZ | DEFAULT now() | Row creation time |

#### `standards`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| iso_reference | VARCHAR(100) | UNIQUE, NOT NULL | e.g. ISO 9001:2015 |
| title | TEXT | NOT NULL | Full standard title |
| edition | VARCHAR(50) | NULLABLE | Edition or year |
| tc_committee | VARCHAR(100) | NULLABLE | TC / SC / WG code |
| status | ENUM | NOT NULL | active\|revised\|amended\|withdrawn\|replaced\|under_review |
| is_purchased | BOOLEAN | DEFAULT FALSE | Purchase flag |
| purchased_at | TIMESTAMPTZ | NULLABLE | Purchase timestamp |
| purchased_by | UUID | FK users.id, NULLABLE | Purchaser |
| purchase_notes | TEXT | NULLABLE | Licence / cost centre notes |
| source_feed_id | UUID | FK rss_feeds.id, NULLABLE | Feed that first discovered this |
| external_url | TEXT | NULLABLE | ISO catalogue link |
| created_at | TIMESTAMPTZ | DEFAULT now() | Row creation time |
| updated_at | TIMESTAMPTZ | DEFAULT now() | Last update time |

#### `standard_history`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| standard_id | UUID | FK standards.id, NOT NULL | Parent standard |
| event_type | ENUM | NOT NULL | new\|updated\|amended\|withdrawn\|replaced\|purchased\|status_change |
| old_value | JSONB | NULLABLE | Snapshot before change |
| new_value | JSONB | NOT NULL | Snapshot after change |
| source | ENUM | NOT NULL | rss \| manual \| system |
| triggered_by | UUID | FK users.id, NULLABLE | User if manual |
| notes | TEXT | NULLABLE | Free-text context |
| created_at | TIMESTAMPTZ | DEFAULT now() | Event timestamp |

#### `documents`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| standard_id | UUID | FK standards.id, NOT NULL | Owning standard |
| version_number | SMALLINT | NOT NULL | Auto-incremented per standard |
| filename | VARCHAR(255) | NOT NULL | Original filename |
| storage_path | TEXT | NOT NULL | FS path or S3 key |
| file_size_bytes | BIGINT | NOT NULL | File size |
| sha256_checksum | CHAR(64) | NOT NULL | Integrity hash |
| mime_type | VARCHAR(100) | NOT NULL | e.g. application/pdf |
| change_notes | TEXT | NULLABLE | What changed in this version |
| uploaded_by | UUID | FK users.id, NOT NULL | Uploader |
| uploaded_at | TIMESTAMPTZ | DEFAULT now() | Upload timestamp |
| is_current | BOOLEAN | DEFAULT TRUE | Latest version flag |

#### `distribution_lists`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| name | VARCHAR(255) | UNIQUE, NOT NULL | e.g. Engineering Team |
| description | TEXT | NULLABLE | Purpose notes |
| created_by | UUID | FK users.id | Creator |
| created_at | TIMESTAMPTZ | DEFAULT now() | Row creation time |

#### `distribution_list_members`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| list_id | UUID | FK distribution_lists.id | Parent list |
| email | VARCHAR(255) | NOT NULL | Recipient address |
| name | VARCHAR(255) | NULLABLE | Display name |
| is_active | BOOLEAN | DEFAULT TRUE | Enable/disable without deleting |

#### `notification_trigger_mappings`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| event_type | ENUM | NOT NULL | Same enum as standard_history.event_type |
| list_id | UUID | FK distribution_lists.id | Target list |
| notify_all_users | BOOLEAN | DEFAULT FALSE | Also send in-app to all users |

#### `notifications`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | UUID | PK | Primary key |
| user_id | UUID | FK users.id, NOT NULL | Recipient user |
| event_type | ENUM | NOT NULL | Event category |
| severity | ENUM | NOT NULL | info \| warning \| critical |
| title | VARCHAR(255) | NOT NULL | Short notification title |
| body | TEXT | NOT NULL | Full notification text |
| related_standard_id | UUID | FK standards.id, NULLABLE | Linked standard |
| is_read | BOOLEAN | DEFAULT FALSE | Read flag |
| created_at | TIMESTAMPTZ | DEFAULT now() | Delivery timestamp |

#### `audit_logs`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | BIGSERIAL | PK | Sequential audit ID |
| actor_id | UUID | FK users.id, NULLABLE | User performing the action (null = system) |
| action | VARCHAR(100) | NOT NULL | e.g. standard.purchased, feed.created |
| resource_type | VARCHAR(100) | NOT NULL | Table / entity name |
| resource_id | UUID | NULLABLE | PK of affected row |
| payload | JSONB | NULLABLE | Diff or context data |
| ip_address | INET | NULLABLE | Client IP |
| created_at | TIMESTAMPTZ | DEFAULT now() | Immutable event time |

#### `celery_schedules`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK SERIAL | Primary key |
| task_name | VARCHAR(255) | NOT NULL | Celery task path |
| feed_id | UUID | FK rss_feeds.id, NULLABLE | Associated feed |
| cron_expression | VARCHAR(100) | NOT NULL | Standard cron string |
| is_enabled | BOOLEAN | DEFAULT TRUE | Active flag |
| last_run_at | TIMESTAMPTZ | NULLABLE | Last execution |
| next_run_at | TIMESTAMPTZ | NULLABLE | Next scheduled execution |

---

## 7. API Design

### 7.1 Conventions

- Base path: `/api/v1`
- Authentication: `Bearer JWT` in `Authorization` header
- Pagination: `?page=1&page_size=20` on all list endpoints
- Error shape: `{ "detail": "...", "code": "ERROR_CODE" }`
- All timestamps in ISO 8601 UTC

### 7.2 Endpoint Reference

| Method | Path | Auth Required | Description |
|---|---|---|---|
| POST | `/auth/login` | No | Exchange credentials for JWT + refresh token |
| POST | `/auth/refresh` | No | Refresh access token |
| POST | `/auth/logout` | User | Invalidate refresh token |
| POST | `/auth/password-reset/request` | No | Send reset email |
| POST | `/auth/password-reset/confirm` | No | Confirm reset with token |
| GET | `/users` | Admin | List all users |
| POST | `/users` | Admin | Create user |
| GET | `/users/{id}` | Admin | Get user detail |
| PATCH | `/users/{id}` | Admin | Update user |
| DELETE | `/users/{id}` | Admin | Deactivate user |
| GET | `/feeds` | Manager+ | List all RSS feeds |
| POST | `/feeds` | Admin | Add new feed |
| GET | `/feeds/{id}` | Manager+ | Get feed detail |
| PATCH | `/feeds/{id}` | Admin | Update feed |
| DELETE | `/feeds/{id}` | Admin | Delete feed |
| POST | `/feeds/{id}/poll` | Admin | Trigger immediate poll |
| GET | `/standards` | Viewer+ | List standards (filterable) |
| POST | `/standards` | Manager+ | Create standard manually |
| GET | `/standards/{id}` | Viewer+ | Get standard detail + history |
| PATCH | `/standards/{id}` | Manager+ | Update standard |
| POST | `/standards/{id}/purchase` | Manager+ | Mark as purchased |
| GET | `/standards/{id}/history` | Viewer+ | Get change history |
| GET | `/standards/{id}/documents` | Viewer+ | List document versions |
| POST | `/standards/{id}/documents` | Manager+ | Upload new document version |
| GET | `/documents/{id}/download` | Viewer+ | Get pre-signed download URL |
| DELETE | `/documents/{id}` | Admin | Soft-delete document version |
| GET | `/notifications` | User | List own notifications |
| PATCH | `/notifications/{id}/read` | User | Mark single as read |
| POST | `/notifications/read-all` | User | Mark all as read |
| GET | `/distribution-lists` | Admin | List all distribution lists |
| POST | `/distribution-lists` | Admin | Create distribution list |
| PATCH | `/distribution-lists/{id}` | Admin | Update list |
| DELETE | `/distribution-lists/{id}` | Admin | Delete list |
| POST | `/distribution-lists/{id}/members` | Admin | Add member email(s) |
| DELETE | `/distribution-lists/{id}/members/{email}` | Admin | Remove member |
| GET | `/admin/schedules` | Admin | List Celery beat schedules |
| PATCH | `/admin/schedules/{id}` | Admin | Update schedule (cron) |
| GET | `/admin/audit-logs` | Admin | Query audit log |
| GET | `/admin/worker-status` | Admin | Celery worker health |
| GET | `/dashboard/summary` | Viewer+ | Aggregated dashboard stats |

---

## 8. Background Job Architecture (Celery)

### 8.1 Broker & Backend

- **Broker:** Redis (reliable delivery, low latency, simple ops)
- **Result backend:** Redis (task state, short TTL of 1 hour)
- **Celery Beat:** database-backed schedule stored in `celery_schedules` table, loaded on startup

### 8.2 Task Inventory

| Task Name | Trigger | Queue | Description |
|---|---|---|---|
| `tasks.feeds.poll_feed` | Celery Beat (per-feed cron) | feeds | Fetches single RSS feed, parses entries, diffs against DB, writes standard_history rows, enqueues notifications |
| `tasks.feeds.poll_all_feeds` | Manual / admin trigger | feeds | Fan-out: iterates enabled feeds and dispatches poll_feed for each |
| `tasks.notifications.send_email_notification` | Chained after standard event | notifications | Assembles HTML email, resolves distribution list members, sends via SMTP, logs result |
| `tasks.notifications.send_bulk_notification` | purchase / withdrawal events | notifications | Sends to all active users (in-app) + all mapped distribution lists (email) |
| `tasks.maintenance.cleanup_old_notifications` | Daily at 02:00 UTC | maintenance | Archives in-app notifications older than 90 days |
| `tasks.maintenance.refresh_worker_heartbeat` | Every 60 seconds | maintenance | Updates worker-health table for admin dashboard |

### 8.3 `poll_feed` Task — Detailed Flow

1. Fetch RSS XML from feed URL (httpx with 10s timeout).
2. Parse entries with `feedparser`.
3. For each entry, extract ISO reference number using regex patterns for ISO/IEC/IEEE formats.
4. Query `standards` table for existing record matching ISO reference.
5. Detect change type by comparing entry content hash, title, and publication date against stored values.
6. If change detected: update `standards` row, append `standard_history` row, enqueue `send_email_notification` task.
7. If new standard: insert `standards` row, append history row with `event_type=new`, enqueue notification.
8. Update `rss_feeds.last_polled_at`, `last_poll_status`, `failure_count`.
9. On exception: increment `failure_count`, retry with backoff (60s, 120s, 240s). After 3 failures, mark `status=failed` and alert admin.

### 8.4 Dynamic Schedule Management

- Each RSS feed has its own Celery Beat entry in `celery_schedules` keyed by `feed_id`.
- Admin changes feed schedule via `PATCH /api/v1/feeds/{id}` → API writes updated cron to `celery_schedules` and re-schedules via Beat API.
- Celery Beat re-reads DB schedule every 5 minutes (`max_interval=300`).

### 8.5 Celery Configuration

```python
# celery_config.py
broker_url = REDIS_URL
result_backend = REDIS_URL
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
task_acks_late = True              # re-queue on worker crash
task_reject_on_worker_lost = True
worker_prefetch_multiplier = 1     # fair dispatch
beat_scheduler = 'celery_sqlalchemy_scheduler:DatabaseScheduler'
beat_max_loop_interval = 300       # 5 min schedule refresh
```

---

## 9. User Roles & Permissions

| Permission | Admin | Manager | Viewer |
|---|:---:|:---:|:---:|
| View standards list & detail | ✓ | ✓ | ✓ |
| View document versions | ✓ | ✓ | ✓ |
| Download documents | ✓ | ✓ | ✓ |
| View dashboard & notifications | ✓ | ✓ | ✓ |
| Mark notifications as read | ✓ | ✓ | ✓ |
| Create / edit standards manually | ✓ | ✓ | ✗ |
| Mark standard as purchased | ✓ | ✓ | ✗ |
| Upload document versions | ✓ | ✓ | ✗ |
| Manage RSS feeds | ✓ | ✗ | ✗ |
| Trigger manual feed polls | ✓ | ✗ | ✗ |
| Manage users & roles | ✓ | ✗ | ✗ |
| Manage distribution lists | ✓ | ✗ | ✗ |
| Configure notification mappings | ✓ | ✗ | ✗ |
| Configure SMTP settings | ✓ | ✗ | ✗ |
| Manage Celery schedules | ✓ | ✗ | ✗ |
| View audit logs | ✓ | ✗ | ✗ |
| Delete / archive records | ✓ | ✗ | ✗ |

---

## 10. Notification Architecture

### 10.1 Event-to-Notification Flow

1. A triggering event occurs (RSS change detected, purchase recorded, document uploaded).
2. FastAPI or Celery task creates a `standard_history` row and calls `notify(event_type, standard_id)`.
3. `notify()` resolves `notification_trigger_mappings` to find target distribution list(s) and whether all-users in-app alert is required.
4. For each distribution list: enqueue `send_email_notification` task with rendered HTML body.
5. If `notify_all_users=True`: create a `notifications` row for every active user.
6. Email task resolves list members, sends individual emails via `aiosmtplib`, logs success/failure per address.

### 10.2 Email Template Structure

- Transactional HTML email with inline CSS (compatible with common mail clients).
- Subject prefix: `[ISTS]` to enable recipient filtering.
- Sections: event summary, affected standard details, action link (view in dashboard), footer with unsubscribe notice.
- Plain-text fallback included in all `multipart/alternative` messages.

### 10.3 In-App Notification

- Stored in `notifications` table per user.
- Unread count returned in every authenticated API response header (`X-Unread-Notifications`).
- Dashboard bell icon polls `GET /notifications?is_read=false` every 30 seconds (short-poll).
- **Future enhancement:** replace polling with WebSocket channel for real-time delivery.

### 10.4 Event Severity Matrix

| Event | Severity | In-App | Email (Dist. List) |
|---|---|---|---|
| New standard published | Info | ✓ all users | ✓ mapped lists |
| Standard updated / revised | Info | ✓ all users | ✓ mapped lists |
| Standard amended | Info | ✓ all users | ✓ mapped lists |
| Standard purchased | Info | ✓ all users | ✓ all mapped lists |
| Standard withdrawn | Warning | ✓ all users | ✓ mapped lists |
| Standard replaced | Warning | ✓ all users | ✓ mapped lists |
| Document uploaded / revised | Info | ✓ all users | ✓ mapped lists |
| Feed poll failed (3 retries) | Critical | ✓ admins only | ✓ admin list |

---

## 11. Document Storage & Versioning

### 11.1 Storage Abstraction

All document I/O goes through a `StorageBackend` interface so switching from local to S3 requires only a configuration change, not code changes.

```python
class StorageBackend(Protocol):
    def upload(self, file: BinaryIO, key: str) -> str: ...
    def download_url(self, key: str, ttl: int) -> str: ...
    def delete(self, key: str) -> None: ...

# LocalStorageBackend  →  STORAGE_BACKEND=local
# S3StorageBackend     →  STORAGE_BACKEND=s3
```

### 11.2 Local Storage Layout

- Base path: `/app/storage` (Docker volume mount)
- File path: `/app/storage/standards/{standard_id}/{version_number}_{filename}`
- Download: API reads file from disk, streams response with `Content-Disposition: attachment`

### 11.3 S3 Storage Layout

- Bucket: `ists-documents-{env}` (private, server-side encryption enabled)
- Key: `standards/{standard_id}/{version_number}_{filename}`
- Download: API generates a pre-signed GET URL with 15-minute TTL, returns URL to client
- Bucket policy: no public access; IAM role for ECS task has `s3:GetObject` and `s3:PutObject` only on `ists-documents-*`

### 11.4 Versioning Rules

- `version_number` is auto-assigned as `MAX(version_number)+1` per `standard_id` on every upload.
- Uploading a new version sets `is_current=TRUE` on the new row and `FALSE` on all prior rows for the same standard.
- Deletion is soft-only (`is_current = FALSE`, file remains in storage). Physical deletion is admin-only via a separate purge endpoint.
- SHA-256 checksum computed server-side on upload; duplicate checksums within the same standard are rejected with HTTP 409.

---

## 12. Deployment Architecture

### 12.1 Local Development (Docker Compose)

| Service | Image | Ports | Notes |
|---|---|---|---|
| web | app:latest | 8000:8000 | FastAPI + uvicorn --reload; mounts ./src |
| worker | app:latest | — | `celery worker -Q feeds,notifications,maintenance` |
| beat | app:latest | — | `celery beat --scheduler=DatabaseScheduler` |
| db | postgres:16-alpine | 5432:5432 | Volume: pgdata |
| redis | redis:7-alpine | 6379:6379 | Persist to volume for Beat schedule |
| frontend | node:20-alpine | 5173:5173 | Vite dev server; `VITE_API_URL=http://localhost:8000` |

### 12.2 AWS Production

- All services run as ECS Fargate tasks in a private VPC subnet.
- ALB sits in a public subnet and terminates HTTPS (ACM certificate). Forwards to ECS API service on port 8000.
- React build artifacts uploaded to S3 static bucket, served by CloudFront (HTTPS, CDN caching).
- RDS PostgreSQL in a private subnet; only ECS security group can reach port 5432.
- ElastiCache Redis in private subnet; only ECS security group can reach port 6379.
- Celery Beat runs as a single ECS task (desired count = 1) to prevent duplicate scheduling.
- Celery Workers scale horizontally (ECS service, min 1 / max 4) based on Redis queue depth CloudWatch alarm.
- ECR stores Docker images; ECS pulls on task definition update.
- CI/CD: GitHub Actions builds image, pushes to ECR, updates ECS service (rolling deployment).

### 12.3 Environment Variables

| Variable | Dev Value | Prod Source |
|---|---|---|
| `DATABASE_URL` | postgresql+asyncpg://... | AWS Secrets Manager |
| `REDIS_URL` | redis://redis:6379/0 | AWS Secrets Manager |
| `SECRET_KEY` | dev-secret-change-me | AWS Secrets Manager |
| `STORAGE_BACKEND` | local | s3 |
| `S3_BUCKET_NAME` | — | ists-documents-prod |
| `AWS_REGION` | — | us-east-1 |
| `SMTP_HOST` | localhost | your-smtp-server |
| `SMTP_PORT` | 1025 (MailHog) | 587 |
| `SMTP_USER` | — | AWS Secrets Manager |
| `SMTP_PASSWORD` | — | AWS Secrets Manager |
| `SMTP_USE_TLS` | false | true |
| `SMTP_FROM_ADDRESS` | ists@local | ists@yourdomain.com |

---

## 13. Security Considerations

### 13.1 Authentication & Authorisation

- **Passwords:** bcrypt with cost factor 12. Never stored in plaintext or logged.
- **Access tokens:** JWT (HS256), signed with `SECRET_KEY`, expiry 8 hours.
- **Refresh tokens:** opaque 256-bit random token stored hashed in DB, expiry 7 days. Single-use (rotated on each refresh).
- **Role enforcement:** FastAPI dependency injection checks role on every protected route. No client-side role bypass possible.
- **Password reset tokens:** 32-byte random, hashed in DB, single-use, 1-hour TTL.

### 13.2 API Security

- **CORS:** configured to allow only the React frontend origin (`CORS_ORIGINS` env var).
- **Rate limiting:** `slowapi` middleware, 60 req/min per IP on auth endpoints; 300 req/min on other endpoints.
- **Request size limit:** 50 MB max (configurable) to prevent memory exhaustion on document uploads.
- **Input validation:** Pydantic schemas on all request bodies; explicit allow-lists for query parameters.
- **SQL injection:** prevented by SQLAlchemy ORM parameterised queries. Raw SQL disallowed in application code.

### 13.3 Document Security

- Documents are never served directly from storage; always via an API-authenticated endpoint.
- **Local:** file paths are server-side only; client never receives a raw filesystem path.
- **S3:** pre-signed URLs are time-limited (15 min) and scoped to a single object key.
- File type validation: magic-byte check on upload (`python-magic`) in addition to MIME type header.

### 13.4 Infrastructure Security (AWS)

- **VPC:** API, DB, and Redis in private subnets. No direct internet access.
- **Security groups:** least-privilege. ALB → ECS (8000 only). ECS → RDS (5432). ECS → Redis (6379).
- **IAM:** ECS task role scoped to `s3:GetObject` and `s3:PutObject` on specific bucket. No wildcard permissions.
- **Secrets:** never in environment variables directly for prod; injected at runtime from AWS Secrets Manager.
- **TLS:** ACM certificate on ALB; Redis and RDS encryption in transit enabled.

### 13.5 SMTP Security

- TLS/STARTTLS enforced in production. Dev uses MailHog (local catch-all).
- SMTP credentials stored in Secrets Manager; never committed to source control.
- From address validated against allowed domain to prevent open relay misuse.

---

## 14. Audit Logging Requirements

### 14.1 Events Logged

| Event | Resource Type | Payload Captured |
|---|---|---|
| User login (success / failure) | user | username, IP, user-agent, outcome |
| User created / updated / deactivated | user | changed fields (before/after) |
| Role changed | user | old role, new role, changed by |
| Feed created / updated / deleted | rss_feed | full record snapshot |
| Manual feed poll triggered | rss_feed | triggered by user ID |
| Standard created / updated | standard | changed fields (before/after) |
| Standard marked as purchased | standard | purchaser, timestamp, notes |
| Standard status change | standard | old status, new status, source |
| Document uploaded | document | filename, version, checksum, uploader |
| Document deleted / purged | document | version, purged by |
| Distribution list created / modified | distribution_list | members added/removed |
| SMTP / system settings changed | system_config | changed keys (values redacted for secrets) |
| Notification sent (email) | notification | recipient count, event type, outcome |
| Password reset requested / completed | user | user ID, IP, token expiry |

### 14.2 Audit Log Integrity

- `audit_logs` uses `BIGSERIAL` PK — gaps indicate potential tampering.
- `created_at` uses `DEFAULT now()` and is never updatable (no `UPDATE` permission on `audit_logs` table granted to application role).
- Application DB role has `INSERT`-only permission on `audit_logs`; `SELECT` granted separately to admin read role.
- In AWS: CloudWatch log group streams a copy of all audit events for independent retention and alerting.

### 14.3 Admin Audit Viewer

- Accessible via `GET /api/v1/admin/audit-logs` (admin only).
- Filterable by: `actor_id`, `action`, `resource_type`, date range.
- Paginated; max 500 rows per page.
- CSV export available via `Accept: text/csv` header.

---

## 15. Scalability Considerations

### 15.1 Current Scale (v1)

| | |
|---|---|
| **Target** | <25 users, <500 standards, 7+ RSS feeds, daily / weekly polling |
| **Approach** | Single Docker Compose stack locally; single ECS cluster on AWS. PostgreSQL on RDS db.t3.medium is sufficient. |

### 15.2 Horizontal Scaling Points

- **FastAPI API:** stateless, scale by increasing ECS task count behind ALB.
- **Celery Workers:** each worker is stateless; increase ECS desired count. Separate queues (`feeds`, `notifications`, `maintenance`) allow independent scaling.
- **Celery Beat:** must remain single instance. Managed by ECS service with desired count = 1.
- **PostgreSQL:** vertical scale first (RDS instance size). Read replicas for reporting queries if needed.
- **Redis:** single node sufficient for this scale. Upgrade to Redis Cluster if queue depth grows beyond 100k messages.

### 15.3 Database Scalability

- All foreign key columns have indexes. Additional composite indexes on `standards(status, is_purchased)` and `notifications(user_id, is_read)`.
- `standard_history` is append-only; archive rows older than 2 years to a separate `history_archive` table if row count grows.
- `audit_logs`: partition by month (`RANGE` on `created_at`) once row count exceeds 1M.
- Connection pooling: asyncpg with pool size 10 per API instance. PgBouncer layer optional for prod.

### 15.4 Feed Scaling

- Currently: 7 feeds. Architecture supports hundreds with no structural changes.
- Adding a feed = inserting a row in `rss_feeds` + a row in `celery_schedules`. No code change.
- If ISO publishes a batch API in future, `poll_feed` can be swapped for a batch variant behind the same interface.

---

## 16. Suggested Technology Stack

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| API Framework | FastAPI | 0.111+ | Async-native, excellent Pydantic integration, auto OpenAPI docs |
| ORM | SQLAlchemy (async) | 2.0+ | Full async support, battle-tested with PostgreSQL |
| DB Migrations | Alembic | Latest | Standard SQLAlchemy migration tool |
| Task Queue | Celery | 5.4+ | Mature, well-documented, Redis broker support |
| Beat Scheduler | celery-sqlalchemy-scheduler | Latest | DB-backed schedule (no file editing) |
| HTTP Client (tasks) | httpx | Latest | Async-capable, modern replacement for requests |
| RSS Parsing | feedparser | 6.x | RFC-compliant, handles ISO feed quirks |
| Email | aiosmtplib | Latest | Async SMTP client; no blocking in Celery tasks |
| Password Hashing | passlib[bcrypt] | Latest | Industry standard, pluggable backend |
| JWT | python-jose | Latest | Lightweight, FastAPI-compatible |
| File Type Detection | python-magic | Latest | Magic-byte validation on uploads |
| Frontend Framework | React + Vite | React 18 | Fast builds, great DX, large ecosystem |
| UI Components | shadcn/ui + Tailwind | Latest | Accessible, unstyled base + utility CSS |
| HTTP Client (FE) | Axios + React Query | Latest | Cache management, background refetch |
| Charts | Recharts | Latest | React-native charting for dashboard |
| Database | PostgreSQL | 16 | ACID, JSONB for history payloads, reliable |
| Cache / Broker | Redis | 7 | Pub/sub, list operations, low latency |
| Containerisation | Docker + Compose | Latest | Dev/prod parity |
| Cloud (prod) | AWS ECS Fargate + RDS + S3 | N/A | Serverless containers, managed DB, object storage |
| CI/CD | GitHub Actions | N/A | Free for small teams, ECR push + ECS deploy actions |
| Logging | structlog | Latest | Structured JSON logs, easy CloudWatch ingestion |
| Monitoring | CloudWatch + Sentry (opt.) | N/A | Metrics/alarms + exception tracking |

---

## 17. Open Questions & Next Steps

### 17.1 Open Questions for Stakeholders

1. Should document access be per-standard (all viewers see all purchased docs) or should individual documents be access-controlled to specific users or groups?
2. Should the system attempt to auto-parse and extract metadata (TC committee, edition, ICS codes) from ISO RSS entry content, or rely on manual entry?
3. Is there a requirement to retain notification email delivery receipts (bounces, opens)? This would require an ESP rather than direct SMTP.
4. Should withdrawn or replaced standards be hidden from the default list view, or shown with a visual indicator?
5. Is there a budget approval workflow for purchasing standards, or is the purchase action itself the final step?
6. Should the admin be able to set a per-user notification preference (e.g., daily digest instead of immediate)?

### 17.2 Recommended Build Order (Milestones)

| Milestone | Scope | Outcome |
|---|---|---|
| M1 — Foundation | Docker Compose, FastAPI skeleton, PostgreSQL schema + Alembic, JWT auth, basic user CRUD | Runnable dev environment with auth |
| M2 — Feed Engine | RSS feed model, poll_feed Celery task, feedparser integration, standard_history writes, manual poll endpoint | Automated RSS ingestion working |
| M3 — Core UI | React + Vite setup, Dashboard page, Standards list + detail, Feed management UI, Admin schedule config | Usable frontend for all core flows |
| M4 — Documents | Upload endpoint, StorageBackend abstraction (local), versioning logic, download via API, document list UI | Full document lifecycle |
| M5 — Notifications | In-app notifications table + bell UI, email task, distribution list management, SMTP config UI | Full notification delivery |
| M6 — Audit & Polish | Audit log, admin viewer, feed failure alerting, Celery worker health panel, error handling, e2e tests | Production-ready |
| M7 — AWS Deployment | Dockerfile prod build, ECS task definitions, RDS, ElastiCache, S3 backend, ALB, GitHub Actions CI/CD | Live on AWS |

---

*— End of Document —*

*Confidential — Internal Use Only*
