"""
backup/encryption.py — AES-256 encryption via AWS KMS.

Falls back to a local Fernet key when KMS is not configured (dev/test only).
Plaintext key material is NEVER stored in the database or filesystem.
"""
import logging
import os

from django.conf import settings as django_settings

logger = logging.getLogger(__name__)

_KMS_KEY_ARN = os.environ.get('AWS_KMS_KEY_ARN', '')
_USE_KMS     = bool(_KMS_KEY_ARN)


class EncryptionService:
    """Encrypt/decrypt bytes using AES-256 (KMS data keys in prod, Fernet in dev)."""

    def encrypt(self, plaintext_bytes: bytes, tenant) -> tuple[bytes, str]:
        """
        Returns (ciphertext, key_id).
        key_id is the KMS key ARN or 'local' for the dev fallback.
        """
        if _USE_KMS:
            return self._kms_encrypt(plaintext_bytes, tenant)
        return self._local_encrypt(plaintext_bytes)

    def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        if key_id == 'local':
            return self._local_decrypt(ciphertext)
        return self._kms_decrypt(ciphertext, key_id)

    # ── KMS path ─────────────────────────────────────────────────────────────

    def _kms_encrypt(self, plaintext_bytes: bytes, tenant) -> tuple[bytes, str]:
        import boto3
        import struct

        client = boto3.client('kms', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
        response = client.generate_data_key(KeyId=_KMS_KEY_ARN, KeySpec='AES_256')
        data_key_plaintext  = response['Plaintext']       # 32 bytes
        data_key_ciphertext = response['CiphertextBlob']  # encrypted data key

        ciphertext = self._aes_encrypt(plaintext_bytes, data_key_plaintext)

        # Prepend encrypted data key length + encrypted data key to ciphertext
        key_len = len(data_key_ciphertext)
        blob = struct.pack('>I', key_len) + data_key_ciphertext + ciphertext

        self._audit('encrypt', tenant, _KMS_KEY_ARN)
        return blob, _KMS_KEY_ARN

    def _kms_decrypt(self, blob: bytes, key_id: str) -> bytes:
        import boto3
        import struct

        key_len = struct.unpack('>I', blob[:4])[0]
        data_key_ciphertext = blob[4:4 + key_len]
        ciphertext          = blob[4 + key_len:]

        client = boto3.client('kms', region_name=os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
        response = client.decrypt(CiphertextBlob=data_key_ciphertext)
        data_key_plaintext = response['Plaintext']

        return self._aes_decrypt(ciphertext, data_key_plaintext)

    # ── Local fallback (dev/test) ─────────────────────────────────────────────

    def _local_encrypt(self, plaintext_bytes: bytes) -> tuple[bytes, str]:
        key = self._local_key()
        from cryptography.fernet import Fernet
        return Fernet(key).encrypt(plaintext_bytes), 'local'

    def _local_decrypt(self, ciphertext: bytes) -> bytes:
        key = self._local_key()
        from cryptography.fernet import Fernet
        return Fernet(key).decrypt(ciphertext)

    @staticmethod
    def _local_key() -> bytes:
        """Derive a stable Fernet key from SECRET_KEY (dev only)."""
        import base64
        import hashlib
        raw = hashlib.sha256(django_settings.SECRET_KEY.encode()).digest()
        return base64.urlsafe_b64encode(raw)

    # ── AES-256-CBC helpers ───────────────────────────────────────────────────

    @staticmethod
    def _aes_encrypt(plaintext: bytes, key: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        import os as _os
        iv = _os.urandom(16)
        padder = padding.PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        enc = cipher.encryptor()
        return iv + enc.update(padded) + enc.finalize()

    @staticmethod
    def _aes_decrypt(ciphertext: bytes, key: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
        iv, data = ciphertext[:16], ciphertext[16:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        dec = cipher.decryptor()
        padded = dec.update(data) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()

    # ── Audit ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _audit(operation: str, tenant, key_id: str):
        try:
            from pos.models import BackupAuditLog
            BackupAuditLog.log_backup_operation(
                operation='backup_business',
                business=tenant,
                backup_file='',
                status='success',
                details={'crypto_op': operation, 'key_id': key_id},
            )
        except Exception as exc:
            logger.warning("Audit log failed for crypto op: %s", exc)
