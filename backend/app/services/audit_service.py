"""
Audit logging service.

write_audit_log() is called from service methods after every state-changing
operation. It inserts an immutable row into the audit_logs table.

In production, the application DB role has INSERT-only permission on
audit_logs (enforced at the PostgreSQL level, not in application code).
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

log = structlog.get_logger(__name__)


async def write_audit_log(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    actor_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Insert an immutable audit log row.

    Args:
        db:            Active async database session (will flush, not commit).
        action:        Dot-notation action name, e.g. "standard.purchased".
        resource_type: Table / entity name, e.g. "standard".
        actor_id:      UUID of the user performing the action; None = system.
        resource_id:   PK of the affected row.
        payload:       JSON-serialisable diff or context data.
        ip_address:    Client IP string (e.g. "203.0.113.1").

    Returns:
        The flushed AuditLog ORM instance.
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload=payload,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()  # assign PK without committing the parent transaction

    log.debug(
        "audit_log_written",
        action=action,
        resource_type=resource_type,
        actor_id=str(actor_id) if actor_id else None,
        resource_id=str(resource_id) if resource_id else None,
    )
    return entry
