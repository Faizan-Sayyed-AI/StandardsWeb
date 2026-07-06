# ISTS — Automation Overview

This document inventories every automated / background process in the ISO Standards
Tracking System: what runs on its own, what triggers it, and where the code lives.
It complements `ARCHITECTURE.drawio` (static system topology) by focusing on
**behavior over time** — schedules, task queues, retries, and notification fan-out.

---

## 1. RSS Feed Polling

This is the core automation loop: RSS feeds describing ISO/IEC/IEEE standards are
polled on a schedule, parsed, diffed against the `standards` table, and any change
is recorded and broadcast as a notification.

**Configuring a schedule (admin, per feed)**
- `RssFeed.schedule_type` supports **`daily`** or **`weekly`** only
  (`backend/app/models/rss_feed.py:31-33`) — plus `schedule_hour` (0–23) and,
  for weekly, `schedule_day_of_week` (0=Mon–6=Sun).
- Admin sets this via `POST /api/v1/feeds` or `PATCH /api/v1/feeds/{id}`
  (`backend/app/api/v1/feeds.py`), handled by `feed_service.py`.
- `_cron_from_schedule()` (`backend/app/services/feed_service.py:27-43`) turns those
  fields into a 5-field cron string, e.g. daily 06:00 → `0 6 * * *`, weekly Mon 06:00
  → `0 6 * * 0`.
- `_upsert_celery_schedule()` (same file) writes that cron string into
  the app's own `celery_schedules` table (`backend/app/models/celery_schedule.py`)
  **and** calls `celery_beat_sync.sync_feed_schedule()`
  (`backend/app/services/celery_beat_sync.py`) to materialize the same cron
  expression into `celery_sqlalchemy_scheduler`'s own tables (`celery_crontab_schedule`,
  `celery_periodic_task`) — the tables Celery Beat's `DatabaseScheduler` actually
  reads. Deleting a feed removes its `PeriodicTask` row via
  `celery_beat_sync.delete_feed_schedule()`.

> **Fixed gap (previously: `celery_schedules` was UI-only metadata never
> synced into Beat's own tables).** `celery_beat_sync.py` writes into
> `celery_sqlalchemy_scheduler`'s own tables (`celery_crontab_schedule`,
> `celery_periodic_task`) using the package's real `Table` objects — but via
> plain SQLAlchemy Core `insert`/`update`/`select`, not an ORM `Session`.
> This is deliberate: the package's own mapper event listeners
> (`PeriodicTaskChanged.update_changed`, registered on `after_insert`/
> `after_update` in its `models.py`) use SQLAlchemy 1.x's removed
> `select([Model])` list syntax and raise `ArgumentError` under our pinned
> SQLAlchemy 2.0 — confirmed empirically, and it's the same root cause as the
> pre-existing `Cannot add entry 'refresh-worker-heartbeat-60s'` /
> `celery.backend_cleanup` errors already seen in the `beat` container log
> (those go through the same broken code path when Beat's own
> `update_from_dict` tries to write its static `beat_schedule` dict entries).
> Because Core-level statements bypass the ORM unit-of-work, those broken
> listeners never fire — but that also means nothing bumps
> `celery_periodic_task_changed` for us automatically, so `celery_beat_sync.py`
> does it explicitly on every write. Feeds created before this fix need a
> one-time backfill: `docker compose exec web python
> scripts/backfill_celery_beat_schedules.py`.
>
> **Verified against a live Beat log (2026-07-06):** created a feed via the
> API, pointed its schedule at `* * * * *` directly through
> `celery_beat_sync.sync_feed_schedule()`, and confirmed in the `beat`
> container log `DatabaseScheduler: Schedule changed.` followed by
> `Scheduler: Sending due task feed-poll-<id> (app.tasks.feeds.poll_feed)`
> every minute, with the `worker` log showing `poll_feed_starting` for that
> feed_id in lockstep. Deleting the feed via `DELETE /feeds/{id}` was also
> confirmed to remove the `PeriodicTask` row. `POST /feeds/{id}/poll` (manual
> trigger) continues to work regardless of Beat state.

**What a poll run does** (`backend/app/tasks/feeds.py`)
1. `poll_all_feeds` — fan-out dispatcher: loads all `is_enabled` feeds, calls
   `poll_feed.delay(feed_id)` per feed.
2. `poll_feed(feed_id)` — for one feed:
   - Fetches via `https://api.rss2json.com/v1/api.json` (bypasses ISO.org's
     Cloudflare challenge) using `httpx`.
   - Parses each entry with `parse_iso_entry()` — a tag/regex-based extractor that
     pulls the ISO reference, edition, ISO stage code (36 stage codes mapped to
     `active` / `under_review` / `withdrawn`), TC committee, and amendment/corrigendum
     markers straight out of the RSS title/description.
   - Diffs the parsed result against the existing `Standard` row by `content_hash`
     (SHA-256 of title/link/dates/summary). No change → skipped.
   - New standard → inserts `Standard` + a `StandardHistory` row
     (`event_type=new`). Changed standard → classifies the change
     (`updated` / `amended` / `withdrawn` / `replaced`) and writes a history row
     with before/after snapshots.
   - Auto-links amendments/corrigenda (`ISO 27874:2008/AMD 1`) to their parent
     standard via `parent_standard_id`.
   - Enqueues `send_bulk_notification.delay(...)` for every new/changed standard.
3. **Retries:** up to 3 attempts, exponential backoff (`60 * 2^retries` seconds).
   On the final failure, the feed is marked `failed` and
   `_notify_feed_failure_async()` creates a critical in-app notification for all
   admins **and** emails the distribution lists mapped to `status_change`.

## 2. Notification Automation

`backend/app/tasks/notifications.py`, queue `notifications`.

- `send_bulk_notification` — writes an in-app `Notification` row for every active
  user, then dispatches `send_email_notification`.
- `send_email_notification` — resolves recipients by joining
  `DistributionListMember` → `NotificationTriggerMapping` on `event_type`
  (new / updated / amended / withdrawn / replaced / purchased / document_uploaded /
  status_change), loads SMTP settings dynamically from `SystemConfig`
  (admin-editable via `GET/PATCH /api/v1/admin/smtp`), and sends an HTML + plain
  text email per recipient via `aiosmtplib`.
- Every email send writes an audit log row (`notification.email_sent`) with
  success/failure counts — this is the system explaining its own automated
  actions after the fact.

## 3. Maintenance Automation

`backend/app/tasks/maintenance.py`, queue `maintenance`.

- `refresh_worker_heartbeat` — writes a `worker:heartbeat` timestamp to Redis every
  **60 seconds**. This is the one entry statically registered in
  `celery_app.py`'s `beat_schedule` dict and confirmed to run.
- `cleanup_old_notifications` — **currently a no-op stub** (`return {"status": "stub"}`).
  It is not registered in any Beat schedule either, so notification archival does
  not happen automatically yet.

## 4. Database Migrations

- Alembic migrations live in `backend/alembic/versions/` (7 revisions as of this
  writing). There is **no auto-migrate-on-boot** — the `web` container's `CMD` is
  a plain `uvicorn` invocation with no entrypoint script that runs `alembic upgrade`.
- Migrations are applied manually: `make migrate` → `docker compose exec web
  alembic upgrade head`.
- `backend/scripts/backfill_base_reference.py`, `backend/scripts/backfill_celery_beat_schedules.py`,
  and `backend/scripts/seed.py` are one-off manual scripts, not scheduled jobs.

## 5. Docker Compose Orchestration

`docker-compose.yml` defines 6 services, all `restart: unless-stopped` except
`frontend` (dev-only Vite server, no restart policy):

| Service    | Image / build         | Role                                              | Ports |
|------------|------------------------|----------------------------------------------------|-------|
| `db`       | postgres:16-alpine      | Primary datastore                                   | 5432  |
| `redis`    | redis:7-alpine          | Celery broker + result backend                      | 6379  |
| `web`      | backend (uvicorn)       | FastAPI, hot-reload                                 | 8000  |
| `worker`   | backend (celery worker) | Executes `feeds`, `notifications`, `maintenance` queues | —  |
| `beat`     | backend (celery beat)   | `celery_sqlalchemy_scheduler.DatabaseScheduler`     | —     |
| `frontend` | node:20-alpine (vite)   | React dev server                                    | 5173  |
| `mailhog`  | mailhog/mailhog         | SMTP catch-all for local email testing              | 1025 / 8025 |

Beat re-reads its schedule table at most every 5 minutes
(`beat_max_loop_interval=300`, `backend/app/celery_app.py:50`).

## 6. Audit Logging of Automated Actions

`write_audit_log()` (`backend/app/services/audit_service.py`) inserts append-only
rows into `audit_logs`. Automation code paths that call it directly today:

- `app.tasks.feeds._notify_feed_failure_async` → `feed.poll_failed_alert`
- `app.tasks.notifications._send_email_notification_async` → `notification.email_sent`

Note that the *successful* poll path and in-app notification creation do **not**
write an audit row — only failures and outbound emails are self-logged.

## 7. CI/CD

None found. There is no `.github/workflows` directory and no pre-commit config in
this repository. The `Makefile` provides manual developer shortcuts
(`up`, `migrate`, `revision`, `seed`, `lint`, `test`) — these are run by hand, not
triggered by any pipeline.

---

## Automation Flow Diagram

Open `AUTOMATION_FLOW.drawio` (below, inline XML) in [diagrams.net](https://app.diagrams.net)
— File → Import From → Device, or copy the XML block into a blank canvas via
Extras → Edit Diagram.

```xml
<mxfile host="app.diagrams.net" version="21.0.0">
  <diagram id="ists-automation-flow" name="ISTS Automation Flow">
    <mxGraphModel dx="1400" dy="800" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1650" pageHeight="1150" math="0" shadow="0">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />

        <mxCell id="title" value="ISTS — Automation Flow: Scheduling → Polling → Diffing → Notifying"
          style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;fontSize=18;fontStyle=1;"
          vertex="1" parent="1">
          <mxGeometry x="380" y="10" width="900" height="40" as="geometry" />
        </mxCell>

        <!-- ═══ ADMIN CONFIG ═══ -->
        <mxCell id="admin" value="&lt;b&gt;Admin&lt;/b&gt;&lt;br&gt;Sets schedule_type&lt;br&gt;(daily / weekly),&lt;br&gt;schedule_hour,&lt;br&gt;schedule_day_of_week"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="40" y="90" width="150" height="90" as="geometry" />
        </mxCell>

        <mxCell id="feedapi" value="&lt;b&gt;PATCH /feeds/{id}&lt;/b&gt;&lt;br&gt;feed_service.py&lt;br&gt;_cron_from_schedule()&lt;br&gt;_upsert_celery_schedule()"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="250" y="90" width="180" height="90" as="geometry" />
        </mxCell>

        <mxCell id="schedtable" value="&lt;b&gt;celery_schedules&lt;/b&gt; table&lt;br&gt;cron_expression&lt;br&gt;is_enabled&lt;br&gt;(admin-facing metadata)"
          style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=16;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="490" y="90" width="170" height="90" as="geometry" />
        </mxCell>

        <mxCell id="gapnote" value="✓ celery_beat_sync.py syncs into celery_sqlalchemy_scheduler's own PeriodicTask / CrontabSchedule tables via Core SQL (ORM path is broken under SQLAlchemy 2.0) — verified dispatching live against Beat logs 2026-07-06."
          style="text;html=1;strokeColor=#d6b656;fillColor=#fffde7;align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;rounded=1;fontSize=9;fontStyle=2;"
          vertex="1" parent="1">
          <mxGeometry x="490" y="195" width="330" height="70" as="geometry" />
        </mxCell>

        <!-- ═══ BEAT / WORKER ═══ -->
        <mxCell id="beat" value="&lt;b&gt;Celery Beat&lt;/b&gt;&lt;br&gt;DatabaseScheduler&lt;br&gt;re-reads every ≤5 min&lt;br&gt;&lt;br&gt;Confirmed static entry:&lt;br&gt;refresh_worker_heartbeat&lt;br&gt;(every 60s)"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="850" y="80" width="200" height="120" as="geometry" />
        </mxCell>

        <mxCell id="heartbeat" value="&lt;b&gt;refresh_worker_heartbeat&lt;/b&gt;&lt;br&gt;writes worker:heartbeat&lt;br&gt;to Redis every 60s"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=9;"
          vertex="1" parent="1">
          <mxGeometry x="1110" y="90" width="180" height="70" as="geometry" />
        </mxCell>

        <mxCell id="manualtrigger" value="&lt;b&gt;Admin: POST&lt;/b&gt;&lt;br&gt;/feeds/{id}/poll&lt;br&gt;(always works —&lt;br&gt;bypasses scheduling)"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=9;"
          vertex="1" parent="1">
          <mxGeometry x="850" y="230" width="200" height="80" as="geometry" />
        </mxCell>

        <!-- ═══ POLL PIPELINE ═══ -->
        <mxCell id="pollall" value="&lt;b&gt;poll_all_feeds&lt;/b&gt;&lt;br&gt;fan-out dispatcher&lt;br&gt;one poll_feed.delay()&lt;br&gt;per enabled feed"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="850" y="350" width="200" height="90" as="geometry" />
        </mxCell>

        <mxCell id="pollfeed" value="&lt;b&gt;poll_feed(feed_id)&lt;/b&gt;&lt;br&gt;queue: feeds&lt;br&gt;retries: 3, backoff 60·2^n"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="850" y="470" width="200" height="90" as="geometry" />
        </mxCell>

        <mxCell id="rss2json" value="&lt;b&gt;rss2json.com&lt;/b&gt;&lt;br&gt;RSS → JSON proxy&lt;br&gt;(bypasses Cloudflare)"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="1130" y="470" width="180" height="70" as="geometry" />
        </mxCell>

        <mxCell id="parse" value="&lt;b&gt;parse_iso_entry()&lt;/b&gt;&lt;br&gt;regex extract: reference,&lt;br&gt;stage, TC committee,&lt;br&gt;amendment markers"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="850" y="590" width="200" height="90" as="geometry" />
        </mxCell>

        <mxCell id="diff" value="&lt;b&gt;Diff vs Standard&lt;/b&gt;&lt;br&gt;by content_hash&lt;br&gt;(SHA-256)"
          style="rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="875" y="710" width="150" height="90" as="geometry" />
        </mxCell>

        <mxCell id="skipped" value="No change → skipped&lt;br&gt;(no DB write)"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#999999;fontSize=9;"
          vertex="1" parent="1">
          <mxGeometry x="620" y="730" width="170" height="50" as="geometry" />
        </mxCell>

        <mxCell id="standardhistory" value="&lt;b&gt;Standard&lt;/b&gt; upsert +&lt;br&gt;&lt;b&gt;StandardHistory&lt;/b&gt; row&lt;br&gt;(new / updated / amended /&lt;br&gt;withdrawn / replaced)"
          style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=16;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="850" y="840" width="200" height="100" as="geometry" />
        </mxCell>

        <!-- ═══ NOTIFICATION FAN-OUT ═══ -->
        <mxCell id="bulknotif" value="&lt;b&gt;send_bulk_notification&lt;/b&gt;&lt;br&gt;queue: notifications&lt;br&gt;in-app Notification row&lt;br&gt;per active user"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="1130" y="840" width="200" height="90" as="geometry" />
        </mxCell>

        <mxCell id="emailnotif" value="&lt;b&gt;send_email_notification&lt;/b&gt;&lt;br&gt;join DistributionListMember&lt;br&gt;⋈ NotificationTriggerMapping&lt;br&gt;on event_type"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="1130" y="960" width="200" height="90" as="geometry" />
        </mxCell>

        <mxCell id="smtp" value="&lt;b&gt;SMTP&lt;/b&gt;&lt;br&gt;aiosmtplib&lt;br&gt;HTML + text email"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=10;"
          vertex="1" parent="1">
          <mxGeometry x="1400" y="960" width="160" height="70" as="geometry" />
        </mxCell>

        <mxCell id="auditemail" value="&lt;b&gt;audit_logs&lt;/b&gt;&lt;br&gt;notification.email_sent"
          style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=14;fillColor=#f8cecc;strokeColor=#b85450;fontSize=9;"
          vertex="1" parent="1">
          <mxGeometry x="1130" y="1080" width="200" height="60" as="geometry" />
        </mxCell>

        <!-- ═══ FAILURE PATH ═══ -->
        <mxCell id="failure" value="&lt;b&gt;3 retries exhausted&lt;/b&gt;&lt;br&gt;feed marked failed"
          style="rhombus;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=9;"
          vertex="1" parent="1">
          <mxGeometry x="590" y="470" width="150" height="90" as="geometry" />
        </mxCell>

        <mxCell id="failnotify" value="&lt;b&gt;_notify_feed_failure_async&lt;/b&gt;&lt;br&gt;critical in-app alert to admins&lt;br&gt;+ email to status_change lists&lt;br&gt;+ audit log: feed.poll_failed_alert"
          style="rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=9;"
          vertex="1" parent="1">
          <mxGeometry x="330" y="470" width="220" height="100" as="geometry" />
        </mxCell>

        <!-- ═══ MAINTENANCE NOTE ═══ -->
        <mxCell id="maintnote" value="&lt;b&gt;cleanup_old_notifications&lt;/b&gt; — stub only, returns immediately, NOT registered in any Beat schedule. No automatic notification archival occurs today."
          style="text;html=1;strokeColor=#999999;fillColor=#f5f5f5;align=left;verticalAlign=top;spacingLeft=8;spacingTop=6;rounded=1;fontSize=9;fontStyle=2;"
          vertex="1" parent="1">
          <mxGeometry x="40" y="230" width="400" height="70" as="geometry" />
        </mxCell>

        <!-- ═══ EDGES ═══ -->
        <mxCell id="e1" edge="1" source="admin" target="feedapi" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e2" edge="1" source="feedapi" target="schedtable" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e3" value="reads (≤5 min lag)" edge="1" source="beat" target="schedtable" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;dashed=1;fontSize=9;fontStyle=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e4" edge="1" source="beat" target="heartbeat" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e5" value="dispatches (per feed cron schedule)" edge="1" source="beat" target="pollall" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;dashed=1;fontSize=9;fontStyle=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e6" edge="1" source="manualtrigger" target="pollfeed" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e7" edge="1" source="pollall" target="pollfeed" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e8" edge="1" source="pollfeed" target="rss2json" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;dashed=1;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e9" edge="1" source="pollfeed" target="parse" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e10" edge="1" source="parse" target="diff" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e11" value="no" edge="1" source="diff" target="skipped" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e12" value="changed" edge="1" source="diff" target="standardhistory" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e13" edge="1" source="standardhistory" target="bulknotif" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e14" edge="1" source="bulknotif" target="emailnotif" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e15" edge="1" source="emailnotif" target="smtp" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;dashed=1;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e16" edge="1" source="emailnotif" target="auditemail" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e17" value="3× retry exhausted" edge="1" source="pollfeed" target="failure" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;fontStyle=2;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        <mxCell id="e18" edge="1" source="failure" target="failnotify" parent="1" style="edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=0;fontSize=9;">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

A standalone copy of the same diagram is saved at `AUTOMATION_FLOW.drawio` for
direct opening in the draw.io desktop app or VS Code draw.io extension.
