"""
Helper functions for fetching and updating the document AI tagging service
configuration from the database (system_config table).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.smtp_config import MASKED_PASSWORD_PLACEHOLDER
from app.models.system_config import SystemConfig

_CONFIG_KEY = "document_tagging_config"


async def get_active_document_tagging_settings(db: AsyncSession) -> dict:
    """Retrieve the document tagging service config, defaulting to blank/unconfigured."""
    stmt = select(SystemConfig).where(SystemConfig.key == _CONFIG_KEY)
    res = await db.execute(stmt)
    config_row = res.scalar_one_or_none()

    defaults = {
        "DOCUMENT_TAGGING_URL": "",
        "DOCUMENT_TAGGING_API_KEY": "",
    }

    if config_row:
        row_val = config_row.value
        for k in defaults:
            if k in row_val:
                defaults[k] = row_val[k]

    return defaults


async def set_active_document_tagging_settings(db: AsyncSession, data: dict) -> None:
    """
    Save the document tagging config.

    DOCUMENT_TAGGING_API_KEY is left unchanged when the incoming value is
    blank or the masked placeholder — same round-trip-safety fix already
    applied to SMTP_PASSWORD in smtp_config.py.
    """
    stmt = select(SystemConfig).where(SystemConfig.key == _CONFIG_KEY)
    res = await db.execute(stmt)
    config_row = res.scalar_one_or_none()

    existing_key = config_row.value.get("DOCUMENT_TAGGING_API_KEY", "") if config_row else ""
    incoming_key = data.get("DOCUMENT_TAGGING_API_KEY", "")
    api_key = (
        existing_key
        if incoming_key in ("", MASKED_PASSWORD_PLACEHOLDER)
        else incoming_key
    )

    payload = {
        "DOCUMENT_TAGGING_URL": data.get("DOCUMENT_TAGGING_URL", ""),
        "DOCUMENT_TAGGING_API_KEY": api_key,
    }

    if config_row:
        config_row.value = payload
    else:
        config_row = SystemConfig(key=_CONFIG_KEY, value=payload)
        db.add(config_row)

    await db.flush()
