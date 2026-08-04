"""
Application configuration.

Settings come from (lowest to highest precedence):

  1. the defaults in this file
  2. `.env`                       — shared/base values
  3. `.env.<APP_ENV>`             — only when APP_ENV is set (e.g. .env.production)
  4. real process environment variables

Access the singleton via: from app.config import settings

APP_ENV selects the second env file and nothing else — it is read from the
process environment, never from an env file, because it decides which file to
read. With APP_ENV unset the behaviour is exactly as before: `.env` only.
Note this is distinct from ENVIRONMENT, which stays a *value* controlling
production safety checks (see _reject_insecure_secret_in_production).

Example (systemd unit):
    Environment=APP_ENV=production
"""

import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_SECRET_KEY = "dev-secret-change-me-in-production-use-32-random-bytes"
_INSECURE_DEFAULT_API_KEY_ENCRYPTION_KEY = "cGdh0W0zLiiPteRJHYaymhXCJ9Vco-Bq9T1ZjeIKChM="


def _env_files() -> tuple[str, ...]:
    """
    Env files in load order — later files override earlier ones, and a file
    that does not exist is simply skipped.

    Returns just (".env",) when APP_ENV is unset, so existing deployments that
    only have a .env are unaffected.
    """
    app_env = os.environ.get("APP_ENV", "").strip()
    if not app_env:
        return (".env",)
    return (".env", f".env.{app_env}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )
    # ── RSS Feed API keys ─────────────────────────────────
    # Fernet key used to encrypt/decrypt api_keys.key_value at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Keep this separate from SECRET_KEY — rotating the JWT secret must not
    # strand already-encrypted API key values.
    API_KEY_ENCRYPTION_KEY: str = _INSECURE_DEFAULT_API_KEY_ENCRYPTION_KEY

    # ── Database ──────────────────────────────────────────
    # Async URL used by FastAPI / SQLAlchemy (asyncpg driver)
    DATABASE_URL: str = "postgresql+asyncpg://ists:ists_dev_password@localhost:5432/ists"
    # Sync URL used by Celery Beat DatabaseScheduler (psycopg2 driver)
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://ists:ists_dev_password@localhost:5432/ists"

    # ── Redis ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Security ──────────────────────────────────────────
    SECRET_KEY: str = _INSECURE_DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 1

    # ── Storage ───────────────────────────────────────────
    STORAGE_BACKEND: str = "local"  # "local" | "s3"
    # Must stay below the reverse proxy's client_max_body_size (210M in
    # DEPLOYMENT.md) — nginx rejects an oversized body with its own 413 before
    # FastAPI ever sees the request, so raising this alone is not enough.
    MAX_UPLOAD_SIZE_MB: int = 200
    LOCAL_STORAGE_PATH: str = "/app/storage"
    S3_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # ── SMTP ──────────────────────────────────────────────
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    SMTP_FROM_ADDRESS: str = "ists@local"

    # ── CORS ──────────────────────────────────────────────
    # Comma-separated list of allowed frontend origins
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ── App ───────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    # ── Rate Limiting ─────────────────────────────────────
    RATE_LIMIT_AUTH: str = "60/minute"      # stricter limit for auth endpoints
    RATE_LIMIT_DEFAULT: str = "300/minute"  # general API endpoints

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS_ORIGINS as a parsed list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    @model_validator(mode="after")
    def _reject_insecure_secret_in_production(self) -> "Settings":
        """
        Fail fast at startup rather than silently issuing forgeable JWTs.

        SECRET_KEY's default value is public (it's committed in this file and
        in .env.example), so if an operator forgets to set a real value in a
        non-development deployment, every JWT this app issues is forgeable by
        anyone who has read this source file.
        """
        if not self.is_development and self.SECRET_KEY == _INSECURE_DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY is still the insecure default value. "
                "Set a real random SECRET_KEY env var before running with "
                f"ENVIRONMENT={self.ENVIRONMENT!r}."
            )
        if not self.is_development and self.API_KEY_ENCRYPTION_KEY == _INSECURE_DEFAULT_API_KEY_ENCRYPTION_KEY:
            raise ValueError(
                "API_KEY_ENCRYPTION_KEY is still the insecure default value. "
                "Set a real random Fernet key env var before running with "
                f"ENVIRONMENT={self.ENVIRONMENT!r}."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()


# Module-level singleton — import this directly in most modules
settings: Settings = get_settings()
