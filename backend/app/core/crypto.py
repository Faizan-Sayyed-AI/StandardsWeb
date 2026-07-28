"""
Symmetric encryption for secrets stored at rest (e.g. api_keys.key_value).

Uses Fernet (AES-128-CBC + HMAC) keyed by API_KEY_ENCRYPTION_KEY, kept
separate from SECRET_KEY so rotating the JWT signing secret doesn't strand
already-encrypted values.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def encrypt_secret(plain: str) -> str:
    """Encrypt a plaintext secret for storage. Returns an opaque token string."""
    return Fernet(settings.API_KEY_ENCRYPTION_KEY).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Decrypt a token produced by encrypt_secret(). Raises ValueError if invalid."""
    try:
        return Fernet(settings.API_KEY_ENCRYPTION_KEY).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Could not decrypt secret — wrong key or corrupted value") from exc
