import uuid
from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import AdminUser, DBSession
from app.core.exceptions import ConflictError, NotFoundError
from app.core.smtp_config import get_active_smtp_settings, set_active_smtp_settings
from app.models.distribution_list import DistributionList
from app.models.notification_mapping import NotificationTriggerMapping
from app.schemas.admin import (
    NotificationTriggerMappingCreate,
    NotificationTriggerMappingResponse,
    SMTPConfigResponse,
    SMTPConfigUpdate,
)
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
