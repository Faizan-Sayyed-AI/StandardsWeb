"""
Custom application exceptions.

All domain exceptions extend ISTSException, which is NOT a subclass of
FastAPI's HTTPException. A global exception handler in main.py converts
ISTSException → JSONResponse with the PRD error shape:
  { "detail": "...", "code": "ERROR_CODE" }

Usage:
  raise NotFoundError("Standard")         → 404 { detail: "Standard not found", code: "NOT_FOUND" }
  raise AuthError("Invalid token")        → 401 { detail: "Invalid token",       code: "AUTH_ERROR" }
  raise ForbiddenError()                  → 403 { detail: "Permission denied",   code: "FORBIDDEN" }
  raise ConflictError("Email in use")     → 409 { detail: "Email in use",        code: "CONFLICT" }
  raise AppValidationError("Bad format")  → 422 { detail: "Bad format",          code: "VALIDATION_ERROR" }
"""


class ISTSException(Exception):
    """Base class for all ISTS domain exceptions."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, detail: str = "An unexpected error occurred") -> None:
        self.detail = detail
        super().__init__(detail)


class AuthError(ISTSException):
    """401 — Authentication failure (missing/invalid/expired token)."""

    status_code = 401
    error_code = "AUTH_ERROR"

    def __init__(self, detail: str = "Authentication failed") -> None:
        super().__init__(detail)


class ForbiddenError(ISTSException):
    """403 — Authorisation failure (valid user, insufficient role)."""

    status_code = 403
    error_code = "FORBIDDEN"

    def __init__(self, detail: str = "You do not have permission to perform this action") -> None:
        super().__init__(detail)


class NotFoundError(ISTSException):
    """404 — Requested resource does not exist."""

    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(f"{resource} not found")


class ConflictError(ISTSException):
    """409 — Resource already exists or violates a uniqueness constraint."""

    status_code = 409
    error_code = "CONFLICT"

    def __init__(self, detail: str = "Resource already exists") -> None:
        super().__init__(detail)


class AppValidationError(ISTSException):
    """422 — Business-logic validation error (distinct from Pydantic schema errors)."""

    status_code = 422
    error_code = "VALIDATION_ERROR"

    def __init__(self, detail: str = "Validation failed") -> None:
        super().__init__(detail)
