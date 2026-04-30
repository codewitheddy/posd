"""
Field-level encryption for sensitive data at rest.
Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).

Usage:
    from .encryption import encrypt, decrypt

    # In model:
    encrypted_phone = models.TextField(blank=True)

    def set_phone(self, value):
        self.encrypted_phone = encrypt(value)

    def get_phone(self):
        return decrypt(self.encrypted_phone)
"""

import base64
import os
from django.conf import settings


def _get_fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None

    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        return None

    # Accept raw 32-byte key or base64-encoded Fernet key
    if isinstance(key, str):
        key = key.encode()
    if len(key) == 32:
        key = base64.urlsafe_b64encode(key)

    return Fernet(key)


def encrypt(value: str) -> str:
    """Encrypt a string value. Returns original value if encryption not configured."""
    if not value:
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt an encrypted string. Returns original value if encryption not configured."""
    if not value:
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception:
        # Return as-is if decryption fails (e.g., unencrypted legacy data)
        return value


def generate_key() -> str:
    """Generate a new Fernet key. Run once and store in FIELD_ENCRYPTION_KEY env var."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
