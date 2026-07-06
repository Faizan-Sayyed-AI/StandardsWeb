"""
Helper functions for fetching and updating active SMTP settings from database.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.system_config import SystemConfig

MASKED_PASSWORD_PLACEHOLDER = "*" * 8


async def get_active_smtp_settings(db: AsyncSession) -> dict:
    """
    Retrieve SMTP configuration from system_config table,
    falling back to standard environment settings if not configured.
    """
    stmt = select(SystemConfig).where(SystemConfig.key == "smtp_config")
    res = await db.execute(stmt)
    config_row = res.scalar_one_or_none()

    defaults = {
        "SMTP_HOST": settings.SMTP_HOST,
        "SMTP_PORT": settings.SMTP_PORT,
        "SMTP_USER": settings.SMTP_USER,
        "SMTP_PASSWORD": settings.SMTP_PASSWORD,
        "SMTP_USE_TLS": settings.SMTP_USE_TLS,
        "SMTP_FROM_ADDRESS": settings.SMTP_FROM_ADDRESS,
    }

    if config_row:
        row_val = config_row.value
        for k in defaults:
            if k in row_val:
                defaults[k] = row_val[k]

    return defaults


async def set_active_smtp_settings(db: AsyncSession, smtp_data: dict) -> None:
    """
    Save new SMTP config in the system_config table.

    SMTP_PASSWORD is left unchanged when the incoming value is blank or the
    masked placeholder returned by GET /admin/smtp-config — otherwise a plain
    settings-form round-trip (fetch masked config, edit an unrelated field,
    save) silently overwrites the real password with "********".
    """
    stmt = select(SystemConfig).where(SystemConfig.key == "smtp_config")
    res = await db.execute(stmt)
    config_row = res.scalar_one_or_none()

    existing_password = config_row.value.get("SMTP_PASSWORD", "") if config_row else ""
    incoming_password = smtp_data.get("SMTP_PASSWORD", "")
    password = (
        existing_password
        if incoming_password in ("", MASKED_PASSWORD_PLACEHOLDER)
        else incoming_password
    )

    payload = {
        "SMTP_HOST": smtp_data.get("SMTP_HOST", ""),
        "SMTP_PORT": int(smtp_data.get("SMTP_PORT", 1025)),
        "SMTP_USER": smtp_data.get("SMTP_USER", ""),
        "SMTP_PASSWORD": password,
        "SMTP_USE_TLS": bool(smtp_data.get("SMTP_USE_TLS", False)),
        "SMTP_FROM_ADDRESS": smtp_data.get("SMTP_FROM_ADDRESS", "ists@local"),
    }

    if config_row:
        config_row.value = payload
    else:
        config_row = SystemConfig(key="smtp_config", value=payload)
        db.add(config_row)

    await db.flush()
