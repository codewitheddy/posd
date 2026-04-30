"""restore/services.py — RestoreService: full, versioned, and scoped restore."""
import gzip
import json
import logging
import time

from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_RETRIES = 3


class RestoreService:

    @staticmethod
    def restore_latest(tenant, user):
        """Restore from the latest non-corrupted snapshot."""
        from backup.models import BackupSnapshot
        snap = (
            BackupSnapshot.objects
            .filter(tenant=tenant)
            .exclude(status__in=['corrupted', 'deleted'])
            .order_by('-version')
            .first()
        )
        if not snap:
            raise ValueError("No valid snapshot found for this tenant.")
        return RestoreService._do_restore(tenant, snap, user, scope=None)

    @staticmethod
    def restore_version(tenant, version: int, user):
        """Point-in-time restore to a specific snapshot version."""
        from backup.models import BackupSnapshot
        snap = BackupSnapshot.objects.get(tenant=tenant, version=version)
        return RestoreService._do_restore(tenant, snap, user, scope=None)

    @staticmethod
    def restore_scoped(tenant, scope: str, user):
        """Restore only EventLog records matching the given event_type prefix."""
        from backup.models import BackupSnapshot
        snap = (
            BackupSnapshot.objects
            .filter(tenant=tenant)
            .exclude(status__in=['corrupted', 'deleted'])
            .order_by('-version')
            .first()
        )
        if not snap:
            raise ValueError("No valid snapshot found for this tenant.")
        return RestoreService._do_restore(tenant, snap, user, scope=scope)

    @staticmethod
    def _do_restore(tenant, snap, user, scope):
        from backup.cloud import CloudStorageClient
        from backup.encryption import EncryptionService
        from events.models import EventLog
        from pos.models import BackupAuditLog

        start = time.time()
        client = CloudStorageClient()
        enc    = EncryptionService()

        # Download with retries
        ciphertext = None
        for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
            try:
                ciphertext = client.download(snap.storage_key)
                break
            except Exception as exc:
                logger.warning("Download attempt %d failed: %s", attempt, exc)
                if attempt < MAX_DOWNLOAD_RETRIES:
                    time.sleep(10 * attempt)
                else:
                    raise

        # Decrypt → decompress → parse
        plaintext   = enc.decrypt(ciphertext, snap.encryption_key_id or 'local')
        decompressed = gzip.decompress(plaintext)
        records      = json.loads(decompressed.decode('utf-8'))

        # Replay events (skip malformed, skip already-existing UUIDs)
        existing_uuids = set(
            str(u) for u in EventLog.objects.filter(tenant=tenant).values_list('uuid', flat=True)
        )

        to_create = []
        skipped   = 0
        for record in records:
            try:
                uid = str(record['uuid'])
                if uid in existing_uuids:
                    continue
                event_type = record['event_type']
                if scope and not event_type.startswith(scope):
                    continue
                to_create.append(EventLog(
                    uuid=uid,
                    tenant=tenant,
                    event_type=event_type,
                    payload=record['payload'],
                    device_id=record.get('device_id', 'restore'),
                    timestamp=record['timestamp'],
                    sync_status=EventLog.SYNC_STATUS_SYNCED,
                ))
            except (KeyError, TypeError) as exc:
                skipped += 1
                BackupAuditLog.log_backup_operation(
                    operation='restore_business',
                    business=tenant,
                    backup_file=snap.storage_key,
                    status='warning',
                    error_message=f"Malformed record skipped: {exc}",
                )

        if to_create:
            EventLog.objects.bulk_create(to_create, ignore_conflicts=True)

        duration = round(time.time() - start, 2)

        BackupAuditLog.log_backup_operation(
            operation='restore_business',
            user=user,
            business=tenant,
            backup_file=snap.storage_key,
            status='success',
            details={
                'snapshot_version': snap.version,
                'records_restored': len(to_create),
                'records_skipped':  skipped,
                'duration_seconds': duration,
                'scope': scope,
            },
        )

        return {
            'snapshot_version': snap.version,
            'records_restored': len(to_create),
            'records_skipped':  skipped,
            'duration_seconds': duration,
        }
