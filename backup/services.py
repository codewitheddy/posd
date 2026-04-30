"""backup/services.py — BackupService: create snapshots, retention, storage usage."""
import gzip
import hashlib
import json
import logging
import os
import tempfile
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


class BackupService:

    @staticmethod
    def create_snapshot(tenant, triggered_by=None):
        """
        Collect all pending EventLog records, serialize → gzip → AES-256 encrypt,
        upload to cloud, create BackupSnapshot, verify checksum.
        Returns the BackupSnapshot instance.
        """
        from backup.cloud import CloudStorageClient
        from backup.encryption import EncryptionService
        from backup.models import BackupSnapshot, TenantBackupSettings
        from events.models import EventLog
        from events.serializers import EventLogSerializer
        from pos.models import BackupAuditLog

        settings = getattr(tenant, 'backup_settings', None)
        storage_mode = settings.storage_mode if settings else TenantBackupSettings.STORAGE_HYBRID

        # Collect pending events (incremental: only those not yet in a snapshot)
        pending_qs = EventLog.objects.filter(
            tenant=tenant,
            sync_status=EventLog.SYNC_STATUS_PENDING,
        ).order_by('timestamp')

        event_count = pending_qs.count()
        if event_count == 0:
            logger.info("No pending events for tenant %s — skipping snapshot.", tenant.pk)
            # Return a dummy snapshot record with 0 events
            version = BackupSnapshot.next_version(tenant)
            snap = BackupSnapshot.objects.create(
                tenant=tenant,
                version=version,
                storage_key='',
                file_size_bytes=0,
                checksum_sha256='',
                event_count=0,
                status=BackupSnapshot.STATUS_UPLOADED,
            )
            return snap

        # Serialize
        serializer = EventLogSerializer(pending_qs, many=True)
        payload_bytes = json.dumps(serializer.data, default=str).encode('utf-8')

        # Gzip compress
        compressed = gzip.compress(payload_bytes, compresslevel=6)

        # AES-256 encrypt
        enc_service = EncryptionService()
        ciphertext, key_id = enc_service.encrypt(compressed, tenant)

        # Compute checksum of ciphertext
        checksum = hashlib.sha256(ciphertext).hexdigest()

        # Build storage key
        now = timezone.now()
        storage_key = (
            f"backups/{tenant.pk}/{now.strftime('%Y-%m-%d')}"
            f"/{now.strftime('%Y%m%dT%H%M%S')}.json.gz"
        )

        version = BackupSnapshot.next_version(tenant)

        # Upload (skip if local_only)
        if storage_mode != TenantBackupSettings.STORAGE_LOCAL:
            client = CloudStorageClient()
            client.upload(storage_key, ciphertext)
            # Verify checksum
            remote_checksum = client.object_checksum(storage_key)
            snap_status = (
                BackupSnapshot.STATUS_UPLOADED
                if remote_checksum == checksum
                else BackupSnapshot.STATUS_CORRUPTED
            )
        else:
            snap_status = BackupSnapshot.STATUS_UPLOADED

        # Write local copy if hybrid or local_only
        if storage_mode in (TenantBackupSettings.STORAGE_HYBRID, TenantBackupSettings.STORAGE_LOCAL):
            local_dir = os.path.join(tempfile.gettempdir(), 'pos_backups', str(tenant.pk))
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, os.path.basename(storage_key))
            with open(local_path, 'wb') as fh:
                fh.write(ciphertext)

        # Create snapshot record
        snap = BackupSnapshot.objects.create(
            tenant=tenant,
            version=version,
            storage_key=storage_key,
            file_size_bytes=len(ciphertext),
            checksum_sha256=checksum,
            encryption_key_id=key_id,
            event_count=event_count,
            status=snap_status,
        )

        # Mark events as synced atomically
        if snap_status == BackupSnapshot.STATUS_UPLOADED:
            uuids = list(pending_qs.values_list('uuid', flat=True))
            EventLog._force_update_sync_status(uuids, EventLog.SYNC_STATUS_SYNCED)

        # Audit log
        BackupAuditLog.log_backup_operation(
            operation='backup_business',
            user=triggered_by,
            business=tenant,
            backup_file=storage_key,
            status='success' if snap_status == BackupSnapshot.STATUS_UPLOADED else 'failed',
            details={'version': version, 'event_count': event_count},
        )

        if snap_status == BackupSnapshot.STATUS_CORRUPTED:
            logger.error("Snapshot checksum mismatch for tenant %s v%s — marked corrupted.", tenant.pk, version)

        return snap

    @staticmethod
    def delete_expired_snapshots(tenant):
        """Delete BackupSnapshot records and cloud objects older than retention_days."""
        from backup.cloud import CloudStorageClient
        from backup.models import BackupSnapshot, TenantBackupSettings

        settings = getattr(tenant, 'backup_settings', None)
        retention_days = settings.retention_days if settings else 30
        cutoff = timezone.now() - timedelta(days=retention_days)

        expired = BackupSnapshot.objects.filter(tenant=tenant, created_at__lt=cutoff).exclude(
            status=BackupSnapshot.STATUS_DELETED
        )

        client = CloudStorageClient()
        for snap in expired:
            if snap.storage_key:
                try:
                    client.delete(snap.storage_key)
                except Exception as exc:
                    logger.warning("Could not delete cloud object %s: %s", snap.storage_key, exc)
            snap.status = BackupSnapshot.STATUS_DELETED
            snap.save(update_fields=['status'])

        logger.info("Deleted %d expired snapshots for tenant %s.", expired.count(), tenant.pk)

    @staticmethod
    def get_local_storage_usage(tenant):
        """Return dict with used_mb and percent_of_limit for local backup storage."""
        from backup.models import TenantBackupSettings

        local_dir = os.path.join(tempfile.gettempdir(), 'pos_backups', str(tenant.pk))
        used_bytes = 0
        if os.path.isdir(local_dir):
            for dirpath, _, filenames in os.walk(local_dir):
                for fname in filenames:
                    try:
                        used_bytes += os.path.getsize(os.path.join(dirpath, fname))
                    except OSError:
                        pass

        used_mb = round(used_bytes / (1024 * 1024), 2)

        settings = getattr(tenant, 'backup_settings', None)
        limit_mb = settings.local_storage_limit_mb if settings else None
        percent  = round((used_mb / limit_mb) * 100, 1) if limit_mb else None

        return {'used_mb': used_mb, 'limit_mb': limit_mb, 'percent': percent}
