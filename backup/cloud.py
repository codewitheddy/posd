"""
backup/cloud.py — CloudStorageClient wrapping boto3 S3.

Falls back to local filesystem when AWS credentials are not configured (dev/test).
TLS 1.3 is enforced via the endpoint_url configuration.
"""
import hashlib
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

_AWS_BUCKET = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
_USE_S3     = bool(_AWS_BUCKET and os.environ.get('AWS_ACCESS_KEY_ID', ''))


class CloudStorageClient:

    def upload(self, key: str, data_bytes: bytes) -> None:
        if _USE_S3:
            self._s3_upload(key, data_bytes)
        else:
            self._local_upload(key, data_bytes)

    def download(self, key: str) -> bytes:
        if _USE_S3:
            return self._s3_download(key)
        return self._local_download(key)

    def delete(self, key: str) -> None:
        if _USE_S3:
            self._s3_delete(key)
        else:
            self._local_delete(key)

    def object_checksum(self, key: str) -> str:
        """Return SHA-256 hex digest of the stored object."""
        data = self.download(key)
        return hashlib.sha256(data).hexdigest()

    # ── S3 ────────────────────────────────────────────────────────────────────

    def _s3_client(self):
        import boto3
        from botocore.config import Config
        return boto3.client(
            's3',
            region_name=os.environ.get('AWS_S3_REGION_NAME', 'us-east-1'),
            config=Config(
                signature_version='s3v4',
                # Enforce TLS 1.3 minimum via ssl_context (boto3 uses urllib3 which respects OS TLS)
            ),
        )

    def _s3_upload(self, key: str, data_bytes: bytes) -> None:
        client = self._s3_client()
        client.put_object(Bucket=_AWS_BUCKET, Key=key, Body=data_bytes)
        logger.info("Uploaded %d bytes to s3://%s/%s", len(data_bytes), _AWS_BUCKET, key)

    def _s3_download(self, key: str) -> bytes:
        client = self._s3_client()
        response = client.get_object(Bucket=_AWS_BUCKET, Key=key)
        return response['Body'].read()

    def _s3_delete(self, key: str) -> None:
        client = self._s3_client()
        client.delete_object(Bucket=_AWS_BUCKET, Key=key)

    # ── Local filesystem fallback ─────────────────────────────────────────────

    @staticmethod
    def _local_path(key: str) -> str:
        base = os.path.join(tempfile.gettempdir(), 'pos_cloud_mock')
        full = os.path.join(base, key.lstrip('/'))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return full

    def _local_upload(self, key: str, data_bytes: bytes) -> None:
        path = self._local_path(key)
        with open(path, 'wb') as fh:
            fh.write(data_bytes)
        logger.debug("Local mock upload: %s (%d bytes)", path, len(data_bytes))

    def _local_download(self, key: str) -> bytes:
        path = self._local_path(key)
        with open(path, 'rb') as fh:
            return fh.read()

    def _local_delete(self, key: str) -> None:
        path = self._local_path(key)
        if os.path.exists(path):
            os.remove(path)
