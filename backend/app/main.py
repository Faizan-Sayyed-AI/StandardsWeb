"""
FastAPI application factory.

Startup sequence:
  1. Setup structlog logging
  2. Verify PostgreSQL connectivity
  3. Register middleware (RequestID, UnreadNotifications, CORS, SlowAPI)
  4. Register all v1 API routers
  5. Register global exception handler for ISTSException → JSON

GET /healthz  — Liveness probe (no auth required)
GET /metrics  — Prometheus metrics stub (M6)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.api.v1 import router as v1_router
from app.config import settings
from app.core.exceptions import ISTSException
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware, UnreadNotificationMiddleware
from app.database import engine

# ── Logging ───────────────────────────────────────────────────────────────────
setup_logging()
log = structlog.get_logger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    # ── Startup ──
    log.info("ists_starting", environment=settings.ENVIRONMENT, log_level=settings.LOG_LEVEL)

    # Verify database connectivity
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("database_connection_ok")
    except Exception as exc:
        log.error("database_connection_failed", error=str(exc))
        raise

    log.info("ists_ready", docs_url="http://localhost:8000/docs")
    yield

    # ── Shutdown ──
    await engine.dispose()
    log.info("ists_shutdown")


# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="ISO Standards Tracking System (ISTS)",
    description=(
        "Automated discovery, monitoring, and management of ISO technical committee standards. "
        "Provides RSS feed polling, standards lifecycle tracking, document versioning, "
        "in-app and email notifications, and full audit logging."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── Middleware (order matters — outermost is applied last) ────────────────────

# 1. Request ID (outermost — wraps everything)
app.add_middleware(RequestIDMiddleware)

# 2. Unread notification count header
app.add_middleware(UnreadNotificationMiddleware)

# 3. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Unread-Notifications"],
)

# 4. Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(ISTSException)
async def ists_exception_handler(request: Request, exc: ISTSException) -> JSONResponse:
    """Convert all ISTSException subclasses to the PRD error shape: {detail, code}."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.error_code},
    )


# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(v1_router)


# ── Utility endpoints ─────────────────────────────────────────────────────────
@app.get(
    "/healthz",
    tags=["System"],
    summary="Liveness health check",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def healthz() -> dict:
    """Simple liveness probe used by Docker health checks and load balancers."""
    return {"status": "ok"}


@app.get(
    "/metrics",
    tags=["System"],
    summary="Prometheus metrics endpoint (stub — implemented in M6)",
    include_in_schema=False,
)
async def metrics() -> dict:
    """Prometheus metrics stub. Full implementation with prometheus-fastapi-instrumentator in M6."""
    return {"note": "Metrics endpoint will be implemented in M6"}
