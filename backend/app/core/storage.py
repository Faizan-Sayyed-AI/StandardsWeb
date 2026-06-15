"""
Storage backend abstraction (PRD §11.1).

All document I/O goes through a StorageBackend Protocol.
Switching from local to S3 requires only a change to STORAGE_BACKEND env var.

Protocol:
  upload(file, key)         -> stored key (str)
  download_url(key, ttl)    -> URL or signed path (str)
  delete(key)               -> None

Implementations:
  LocalStorageBackend   ->  STORAGE_BACKEND=local  (dev / Docker Compose)
  S3StorageBackend      ->  STORAGE_BACKEND=s3     (AWS prod)

Factory:
  get_storage_backend() -> StorageBackend singleton
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

import structlog

from app.config import settings

log = structlog.get_logger(__name__)


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class StorageBackend(Protocol):
    """Minimal interface every storage backend must implement."""

    def upload(self, file: BinaryIO, key: str) -> str:
        """Save `file` at `key` and return the stored key."""
        ...

    def download_url(self, key: str, ttl: int = 900) -> str:
        """Return a URL or opaque token used to download the file.

        For local storage: returns the filesystem path (API streams it).
        For S3: returns a pre-signed GET URL valid for `ttl` seconds.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove the file at `key` from storage (used by purge endpoint)."""
        ...


# ── Local filesystem backend ──────────────────────────────────────────────────


class LocalStorageBackend:
    """Stores files under LOCAL_STORAGE_PATH (mounted Docker volume in dev)."""

    def __init__(self, base_path: str = settings.LOCAL_STORAGE_PATH) -> None:
        self._base = Path(base_path)

    def _full_path(self, key: str) -> Path:
        # Prevent path-traversal by resolving against base
        target = (self._base / key).resolve()
        if not str(target).startswith(str(self._base.resolve())):
            raise ValueError(f"Attempted path traversal: {key!r}")
        return target

    def upload(self, file: BinaryIO, key: str) -> str:
        target = self._full_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            f.write(file.read())
        log.info("storage.local.upload", key=key, path=str(target))
        return key

    def download_url(self, key: str, ttl: int = 900) -> str:  # noqa: ARG002
        """Return the absolute filesystem path. The API endpoint streams it."""
        full = self._full_path(key)
        if not full.exists():
            raise FileNotFoundError(f"Storage key not found: {key!r}")
        return str(full)

    def delete(self, key: str) -> None:
        target = self._full_path(key)
        if target.exists():
            os.remove(target)
            log.info("storage.local.delete", key=key)


# ── S3 backend ────────────────────────────────────────────────────────────────


class S3StorageBackend:
    """Stores files in an S3 bucket. Download returns a pre-signed URL (15 min TTL)."""

    def __init__(self) -> None:
        import boto3  # type: ignore[import-untyped]

        self._s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
        self._bucket = settings.S3_BUCKET_NAME

    def upload(self, file: BinaryIO, key: str) -> str:
        self._s3.upload_fileobj(file, self._bucket, key)
        log.info("storage.s3.upload", bucket=self._bucket, key=key)
        return key

    def download_url(self, key: str, ttl: int = 900) -> str:
        url: str = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl,
        )
        log.info("storage.s3.presigned_url", key=key, ttl=ttl)
        return url

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)
        log.info("storage.s3.delete", bucket=self._bucket, key=key)


# ── Factory ───────────────────────────────────────────────────────────────────

_backend_instance: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """Return the configured StorageBackend singleton (local or S3)."""
    global _backend_instance
    if _backend_instance is None:
        backend_type = settings.STORAGE_BACKEND.lower()
        if backend_type == "s3":
            _backend_instance = S3StorageBackend()
            log.info("storage.backend.initialised", type="s3", bucket=settings.S3_BUCKET_NAME)
        else:
            _backend_instance = LocalStorageBackend()
            log.info(
                "storage.backend.initialised",
                type="local",
                base_path=settings.LOCAL_STORAGE_PATH,
            )
    return _backend_instance


# ── Utility: SHA-256 checksum ─────────────────────────────────────────────────


def compute_sha256(file: BinaryIO) -> str:
    """Compute hex SHA-256 digest of a file-like object (rewinds to start afterwards)."""
    file.seek(0)
    h = hashlib.sha256()
    for chunk in iter(lambda: file.read(65536), b""):
        h.update(chunk)
    file.seek(0)
    return h.hexdigest()
