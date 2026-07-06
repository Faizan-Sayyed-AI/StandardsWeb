"""
Shared slowapi Limiter instance.

Lives in its own module (rather than app/main.py) so route modules like
app/api/v1/auth.py can import it and apply @limiter.limit(...) to individual
endpoints without a circular import (main.py imports the v1 router, which
imports auth.py).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])
