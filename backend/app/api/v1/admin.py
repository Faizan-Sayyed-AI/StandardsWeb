import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, status, Query, Request
from fastapi.responses import StreamingResponse
import redis.asyncio as aioredis
import structlog
from sqlalchemy import select, desc, func

from app.api.deps import AdminUser, DBSession
from app.config import settings
from app.celery_app import celery
from app.core.exceptions import ConflictError, NotFoundError
from app.core.smtp_config import get_active_smtp_settings, set_active_smtp_settings
from app.models.distribution_list import DistributionList
from app.models.notification_mapping import NotificationTriggerMapping
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.admin import (
    NotificationTriggerMappingCreate,
    NotificationTriggerMappingResponse,
    SMTPConfigResponse,
    SMTPConfigUpdate,
    AuditLogResponse,
    WorkerStatusResponse,
    QueueDepths,
)
from app.schemas.pagination import Page
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/admin", tags=["Admin Settings"])


@router.get(
    "/smtp-config",
    response_model=SMTPConfigResponse,
    summary="Get the active SMTP configuration with masked password (admin)",
)
async def get_smtp_config(
    db: DBSession,
    current_user: AdminUser,
) -> SMTPConfigResponse:
    smtp_data = await get_active_smtp_settings(db)
    return SMTPConfigResponse.from_dict_masked(smtp_data)


@router.patch(
    "/smtp-config",
    response_model=SMTPConfigResponse,
    summary="Update the dynamic SMTP configuration (admin)",
)
async def update_smtp_config(
    payload: SMTPConfigUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> SMTPConfigResponse:
    # Get current to see what changes
    current_settings = await get_active_smtp_settings(db)
    new_settings = payload.model_dump()

    # Log only updated keys to audit log, redacting values
    changed_keys = []
    for k, v in new_settings.items():
        if current_settings.get(k) != v:
            changed_keys.append(k)

    # Save to database system_config
    await set_active_smtp_settings(db, new_settings)

    # Write audit log with values redacted
    await write_audit_log(
        db,
        action="system_config.smtp_updated",
        resource_type="system_config",
        actor_id=current_user.id,
        resource_id=None,
        payload={"updated_keys": changed_keys},
    )

    # Return masked
    return SMTPConfigResponse.from_dict_masked(new_settings)


@router.get(
    "/trigger-mappings",
    response_model=list[NotificationTriggerMappingResponse],
    summary="List all event-to-list trigger mappings (admin)",
)
async def list_trigger_mappings(
    db: DBSession,
    current_user: AdminUser,
) -> list[NotificationTriggerMappingResponse]:
    stmt = (
        select(NotificationTriggerMapping, DistributionList.name)
        .join(DistributionList, DistributionList.id == NotificationTriggerMapping.list_id)
        .order_by(NotificationTriggerMapping.event_type.asc())
    )
    res = await db.execute(stmt)
    items = []
    for mapping, list_name in res.all():
        items.append(
            NotificationTriggerMappingResponse(
                id=mapping.id,
                event_type=mapping.event_type,
                list_id=mapping.list_id,
                notify_all_users=mapping.notify_all_users,
                list_name=list_name,
            )
        )
    return items


@router.post(
    "/trigger-mappings",
    response_model=NotificationTriggerMappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new event-to-list trigger mapping (admin)",
)
async def create_trigger_mapping(
    payload: NotificationTriggerMappingCreate,
    db: DBSession,
    current_user: AdminUser,
) -> NotificationTriggerMappingResponse:
    # Verify list exists
    dl = await db.get(DistributionList, payload.list_id)
    if not dl:
        raise NotFoundError("DistributionList")

    # Check if duplicate mapping exists
    stmt = select(NotificationTriggerMapping).where(
        NotificationTriggerMapping.event_type == payload.event_type,
        NotificationTriggerMapping.list_id == payload.list_id,
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise ConflictError(
            f"A trigger mapping already exists between event '{payload.event_type}' and this list."
        )

    mapping = NotificationTriggerMapping(
        event_type=payload.event_type,
        list_id=payload.list_id,
        notify_all_users=payload.notify_all_users,
    )
    db.add(mapping)
    await db.flush()

    await write_audit_log(
        db,
        action="notification_trigger_mapping.created",
        resource_type="notification_trigger_mapping",
        actor_id=current_user.id,
        resource_id=mapping.id,
        payload={
            "event_type": mapping.event_type,
            "list_id": str(mapping.list_id),
            "notify_all_users": mapping.notify_all_users,
        },
    )

    return NotificationTriggerMappingResponse(
        id=mapping.id,
        event_type=mapping.event_type,
        list_id=mapping.list_id,
        notify_all_users=mapping.notify_all_users,
        list_name=dl.name,
    )


@router.delete(
    "/trigger-mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an event-to-list trigger mapping (admin)",
)
async def delete_trigger_mapping(
    mapping_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    mapping = await db.get(NotificationTriggerMapping, mapping_id)
    if not mapping:
        raise NotFoundError("NotificationTriggerMapping")

    await db.delete(mapping)
    await db.flush()

    await write_audit_log(
        db,
        action="notification_trigger_mapping.deleted",
        resource_type="notification_trigger_mapping",
        actor_id=current_user.id,
        resource_id=mapping_id,
        payload={"event_type": mapping.event_type, "list_id": str(mapping.list_id)},
    )


@router.get(
    "/worker-status",
    response_model=WorkerStatusResponse,
    summary="Get Celery worker status and queue depths (admin)",
)
async def get_worker_status(
    db: DBSession,
    current_user: AdminUser,
) -> WorkerStatusResponse:
    # Check worker ping status
    def _ping():
        try:
            inspect = celery.control.inspect(timeout=1.0)
            ping_res = inspect.ping()
            if ping_res:
                return "online"
        except Exception:
            pass
        return None

    status_str = await asyncio.to_thread(_ping)

    # If ping failed, fallback to checking worker:heartbeat key in Redis
    if not status_str:
        try:
            import redis
            r_sync = redis.Redis.from_url(settings.REDIS_URL)
            heartbeat_val = r_sync.get("worker:heartbeat")
            if heartbeat_val:
                heartbeat_dt = datetime.fromisoformat(heartbeat_val.decode())
                # If heartbeat was updated in the last 120 seconds, count as online
                if (datetime.now(timezone.utc) - heartbeat_dt).total_seconds() < 120:
                    status_str = "online"
        except Exception:
            pass

    if not status_str:
        status_str = "offline"

    # Get queue depths
    queues = {"feeds": 0, "notifications": 0, "maintenance": 0}
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        for q in queues.keys():
            queues[q] = await r.llen(q)
        await r.aclose()
    except Exception as e:
        log.error("failed_to_get_queue_depths", error=str(e))

    return WorkerStatusResponse(
        status=status_str,
        queues=QueueDepths(
            feeds=queues["feeds"],
            notifications=queues["notifications"],
            maintenance=queues["maintenance"]
        )
    )


@router.get(
    "/audit-logs",
    summary="List/Export system audit logs (admin)",
)
async def get_audit_logs(
    request: Request,
    db: DBSession,
    current_user: AdminUser,
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
):
    # Determine format from accept header
    accept_header = request.headers.get("accept", "")
    is_csv = "text/csv" in accept_header

    # Build sqlalchemy query
    stmt = select(AuditLog, User.username).outerjoin(User, AuditLog.actor_id == User.id)

    # Filters
    if actor:
        try:
            actor_uuid = uuid.UUID(actor)
            stmt = stmt.where(AuditLog.actor_id == actor_uuid)
        except ValueError:
            stmt = stmt.where(
                (User.username.ilike(f"%{actor}%")) |
                (User.email.ilike(f"%{actor}%"))
            )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if start_date:
        stmt = stmt.where(AuditLog.created_at >= start_date)
    if end_date:
        stmt = stmt.where(AuditLog.created_at <= end_date)

    if is_csv:
        import csv
        import io
        from fastapi.responses import StreamingResponse

        # Return full results ordered by created_at desc
        stmt = stmt.order_by(desc(AuditLog.created_at))
        res = await db.execute(stmt)
        rows = res.all()

        def generate():
            output = io.StringIO()
            writer = csv.writer(output)
            # CSV headers
            writer.writerow([
                "ID", "Timestamp", "Actor ID", "Actor Username", "Action", "Resource Type", "Resource ID", "IP Address", "Payload"
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

            for log_entry, username in rows:
                writer.writerow([
                    log_entry.id,
                    log_entry.created_at.isoformat(),
                    str(log_entry.actor_id) if log_entry.actor_id else "system",
                    username or "system",
                    log_entry.action,
                    log_entry.resource_type,
                    str(log_entry.resource_id) if log_entry.resource_id else "",
                    log_entry.ip_address or "",
                    str(log_entry.payload) if log_entry.payload else ""
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return StreamingResponse(
            generate(),
            media_type="text/csv",
            headers={
                "Content-Type": "text/csv",
                "Content-Disposition": f"attachment; filename=audit_logs_{today}.csv"
            }
        )

    # JSON response - Paginated
    # Count total
    count_stmt = select(func.count()).select_from(AuditLog).outerjoin(User, AuditLog.actor_id == User.id)
    if actor:
        try:
            actor_uuid = uuid.UUID(actor)
            count_stmt = count_stmt.where(AuditLog.actor_id == actor_uuid)
        except ValueError:
            count_stmt = count_stmt.where(
                (User.username.ilike(f"%{actor}%")) |
                (User.email.ilike(f"%{actor}%"))
            )
    if action:
        count_stmt = count_stmt.where(AuditLog.action == action)
    if resource_type:
        count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)
    if start_date:
        count_stmt = count_stmt.where(AuditLog.created_at >= start_date)
    if end_date:
        count_stmt = count_stmt.where(AuditLog.created_at <= end_date)

    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Paginated query
    offset = (page - 1) * page_size
    stmt = stmt.order_by(desc(AuditLog.created_at)).offset(offset).limit(page_size)
    res = await db.execute(stmt)
    rows = res.all()

    items = []
    for log_entry, username in rows:
        items.append(
            AuditLogResponse(
                id=log_entry.id,
                actor_id=log_entry.actor_id,
                actor_username=username,
                action=log_entry.action,
                resource_type=log_entry.resource_type,
                resource_id=log_entry.resource_id,
                payload=log_entry.payload,
                ip_address=log_entry.ip_address,
                created_at=log_entry.created_at
            )
        )

    return Page[AuditLogResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )

