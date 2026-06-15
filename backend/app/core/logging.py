"""
Structured logging setup using structlog.

Call setup_logging() once at application startup (in main.py lifespan).
Afterwards, obtain loggers with: log = structlog.get_logger()

Dev environment: human-readable ConsoleRenderer (coloured, aligned)
Prod environment: JSON lines (compatible with CloudWatch Logs Insights)
"""

import logging
import sys

import structlog

from app.config import settings


def setup_logging() -> None:
    """Configure structlog and stdlib logging."""

    log_level_int = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Configure stdlib logging (used by uvicorn, sqlalchemy, etc.)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level_int,
    )

    # Shared processors applied regardless of renderer
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    if settings.is_development:
        # Pretty coloured output for local dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON lines for production log aggregators
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

