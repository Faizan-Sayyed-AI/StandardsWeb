"""
ASGI middleware stack.

RequestIDMiddleware       — attaches a unique X-Request-ID to every request/response
UnreadNotificationMiddleware — appends X-Unread-Notifications count to authenticated responses
"""

import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from sqlalchemy import func, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from app.core.security import decode_access_token

log = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Inject a unique request ID into every request and response.

    - Reads X-Request-ID from incoming headers if present (forwarded by ALB).
    - Falls back to a newly generated UUIDv4.
    - Binds the request_id to structlog context so all log lines within a
      request automatically include it.
    - Adds X-Request-ID to the response headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> StarletteResponse:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class UnreadNotificationMiddleware(BaseHTTPMiddleware):
    """
    Append X-Unread-Notifications: <count> to all authenticated API responses.

    Extracts the user_id from the Bearer JWT (no DB round-trip for auth itself),
    then counts unread notification rows for that user.

    Falls back silently on any error (bad token, DB error) — the header is
    simply omitted rather than failing the request.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> StarletteResponse:
        response = await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return response

        token = auth_header[len("Bearer "):]
        try:
            payload = decode_access_token(token)
            user_id: str | None = payload.get("sub")
            if not user_id:
                return response

            # Lazy import to avoid circular imports at module load time
            from app.database import async_session_factory
            from app.models.notification import Notification

            async with async_session_factory() as session:
                result = await session.execute(
                    select(func.count(Notification.id)).where(
                        Notification.user_id == user_id,  # type: ignore[arg-type]
                        Notification.is_read == False,  # noqa: E712
                    )
                )
                unread_count: int = result.scalar_one_or_none() or 0

            response.headers["X-Unread-Notifications"] = str(unread_count)

        except Exception:
            # Never let middleware failures affect the response
            pass

        return response
