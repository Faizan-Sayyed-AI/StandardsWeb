"""
Application configuration.

All settings are read from environment variables (or a .env file in dev).
Access the singleton via: from app.config import settings
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Database ──────────────────────────────────────────
    # Async URL used by FastAPI / SQLAlchemy (asyncpg driver)
    DATABASE_URL: str = "postgresql+asyncpg://ists:ists_dev_password@localhost:5432/ists"
    # Sync URL used by Celery Beat DatabaseScheduler (psycopg2 driver)
    DATABASE_SYNC_URL: str = "postgresql+psycopg2://ists:ists_dev_password@localhost:5432/ists"

    # ── Redis ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Security ──────────────────────────────────────────
    SECRET_KEY: str = "dev-secret-change-me-in-production-use-32-random-bytes"
    ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 1

    # ── Storage ───────────────────────────────────────────
    STORAGE_BACKEND: str = "local"  # "local" | "s3"
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


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()


# Module-level singleton — import this directly in most modules
settings: Settings = get_settings()
