# UI Redesign Brief — StandardSphere Frontend

Paste everything below this line to Emergent AI as the starting prompt.

---

## What this product is

StandardSphere tracks the lifecycle of technical standards (ISO, IEC, IEEE, ASTM) for
organizations that need to know — without manually checking — when a standard they rely on is
revised, withdrawn, or replaced. It ingests RSS feeds from standards bodies on a schedule, keeps
a full change history per standard, stores the actual standard documents (auto-tagged by an AI
classifier), and notifies the right people when something changes. Every action is audit-logged.

**Redesign the frontend only.** The backend is a real, working FastAPI + PostgreSQL application
that is not changing — build a new UI that talks to the existing REST API, not a mockup with
fake data. Nothing about auth, permissions, or business logic should change; only the visual
design, layout, and frontend code should be replaced.

## Who uses it

Three roles, and the UI must gate navigation/actions by role exactly as described:

| Role | Sees / can do |
|---|---|
| **admin** | Everything, plus: manage RSS feeds, schedules, users, distribution lists, SMTP settings, document-tagging config, audit log |
| **manager** | Create/edit standards, upload documents, trigger manual feed polls, mark standards purchased |
| **viewer** | Read-only: standards library, documents, their own notifications |

## Hard technical constraints (do not change these)

1. **Must be a React + TypeScript + Vite app.** It replaces the existing `frontend/` directory
   in a Docker Compose project and is served the same way (Vite dev server locally, static
   build behind Nginx in production) — it cannot be a different framework or a hosted-only app.
2. **API base path is `/api/v1`.** All data comes from the existing FastAPI backend at this
   prefix (see endpoint list below). Do not invent endpoints, response shapes, or mock data —
   treat the API as fixed and design the UI to fit it.
3. **Auth token handling is a deliberate security choice — keep it exactly:**
   - The JWT access token is held **in memory only** (a module-level variable), never in
     `localStorage`/`sessionStorage` — this limits XSS blast radius.
   - The refresh token is an **httpOnly cookie** set by the server; the frontend never reads or
     stores it directly. Requests must be sent with credentials included.
   - On a 401, refresh via `POST /api/v1/auth/refresh` **once**, queueing any other requests
     that failed concurrently behind that single refresh call (don't fire one refresh per
     failed request). On refresh failure, clear state and redirect to `/login`.
   - Every authenticated request sends `Authorization: Bearer <access_token>`.
4. **Role-based route/nav gating**, matching the table above — a viewer must never see admin-only
   nav items or be able to reach admin-only routes directly by URL.
5. Preserve **light/dark theme support** — the current app has both; don't ship dark-only or
   light-only.
6. This is compliance/audit-adjacent software used daily by non-technical roles (managers doing
   manual data entry, viewers checking a library) as well as admins — it needs to read as
   trustworthy and precise, not just "an admin panel." Keep accessibility real: visible keyboard
   focus states, sufficient contrast, forms that fail with a specific, actionable error message.

## Design freedom

Palette, typography, layout style, and component design are **open** — propose a direction that
fits a technical standards-tracking tool used across compliance, manufacturing, and medical
device teams. (For reference, the current build uses a dark slate theme with an indigo→teal
accent gradient and a glassy sidebar — you are not constrained to that, feel free to depart from
it entirely if you have a stronger direction.)

## Pages to design (11 total, plus shared shell)

**Shared shell:** a sidebar or nav exposing the items below (admin-only items hidden for
manager/viewer), a header area with a notification bell (unread count badge, polls
`GET /api/v1/notifications/count`), and the current user's name/role with a logout action.

| Page | Route | Purpose | Key endpoints |
|---|---|---|---|
| Login | `/login` | Email + password sign-in, "forgot password" flow | `POST /auth/login`, `POST /auth/password-reset/request`, `POST /auth/password-reset/confirm` |
| Dashboard | `/dashboard` | At-a-glance summary stats (counts by status, recent activity) — all roles | `GET /dashboard/stats` |
| Standards | `/standards` | The core library: searchable/filterable/sortable table of standards (by committee, standards body, status, stage), grouped view for amendments under their parent standard | `GET /standards`, `GET /standards/committees`, `GET /standards/standards-bodies` |
| Standard Detail | `/standards/:id` | Full record for one standard: metadata, status, its documents (upload/download/version history), full change-history timeline, a "mark as purchased" action (manager+) | `GET /standards/:id`, `GET /standards/:id/history`, `POST /standards/:id/purchase`, `GET/POST /standards/:id/documents`, `GET /documents/:id/download`, `POST /documents/:id/retag` |
| Feeds | `/feeds` (admin) | RSS feed CRUD, per-feed poll schedule, manual "poll now" trigger, last-poll status/failure count | `GET/POST/PATCH/DELETE /feeds`, `POST /feeds/:id/poll` |
| API Keys | *(new — needs adding)* (admin) | Manage the pool of rss2json.com API keys feeds are distributed across: list keys with assigned-feed counts and health status (active/rate_limited/expired/disabled), add/rotate/disable a key, reassign a key's feeds elsewhere before retiring it | `GET/POST/PATCH/DELETE /api-keys`, `POST /api-keys/:id/reassign-feeds` |
| Schedule | `/schedule` (admin) | Overview of all feeds' cron schedules in one place | (backed by feed schedule fields) |
| Users | `/users` (admin) | User CRUD, role assignment, activate/deactivate | `GET/POST/PATCH/DELETE /users` |
| Distribution Lists | `/admin/distribution-lists` (admin) | Mailing lists + members, mapped to notification event types | `GET/POST/PATCH/DELETE /distribution-lists`, member sub-endpoints |
| SMTP Settings | `/admin/smtp-config` (admin) | Configure outbound email; password field must stay masked on read, never echoed back in full | `GET/PATCH /admin/smtp-config` |
| Document Tagging | `/admin/document-tagging` (admin) | Configure the external AI tagging service; API key field must stay masked on read | `GET/PATCH /admin/document-tagging-config` |
| Audit Logs | `/admin/audit-logs` (admin) | Filterable, paginated log of every mutating action (actor, action, resource, IP, timestamp, before/after payload); exportable as CSV | `GET /admin/audit-logs` (JSON or CSV via `Accept: text/csv`) |

Note: the **API Keys** page doesn't exist in the current build — it's new backend
functionality (added to split RSS polling across multiple rss2json.com keys once feed count
exceeds one key's limit) that needs a UI surface for the first time. Design it consistently
with the Feeds page since the two are closely related.

## What "done" looks like

A Vite + React + TypeScript app that:
- Implements all 11 pages above plus the shared shell, wired to the real API contract described.
- Preserves the auth/token/role behavior exactly as specified.
- Is visually cohesive end-to-end (one design system, not a per-page patchwork), works in both
  light and dark mode, and is responsive down to a reasonable tablet width.
- Can be dropped into the existing project's `frontend/` directory and run with `npm install &&
  npm run dev` (matching the existing dev workflow) without backend changes.
