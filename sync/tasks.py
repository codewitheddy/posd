"""sync/tasks.py — Celery tasks for uploading pending events."""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

BATCH_SIZE   = 500
MAX_RETRIES  = 10
RETRY_DELAY  = 30  # seconds, doubles on each retry


@shared_task(bind=True, max_retries=MAX_RETRIES)
def upload_pending_events(self, tenant_id: int, device_id: str = 'server'):
    """
    Poll for pending EventLog records for a tenant, batch-upload to cloud,
    and mark them synced atomically.
    """
    from backup.cloud import CloudStorageClient
    from backup.services import BackupService
    from events.models import EventLog
    from pos.models import Business
    from sync.models import SyncStatus

    try:
        tenant = Business.objects.get(pk=tenant_id)
    except Business.DoesNotExist:
        logger.error("upload_pending_events: tenant %s not found.", tenant_id)
        return

    pending_qs = EventLog.objects.filter(
        tenant=tenant,
        sync_status=EventLog.SYNC_STATUS_PENDING,
    ).order_by('timestamp')

    total = pending_qs.count()
    if total == 0:
        _update_sync_status(tenant, device_id, SyncStatus.STATUS_SYNCED, 0)
        return

    # Paginate into batches of BATCH_SIZE
    offset = 0
    synced_total = 0

    while offset < total:
        batch_qs   = pending_qs[offset:offset + BATCH_SIZE]
        batch_uuids = list(batch_qs.values_list('uuid', flat=True))

        try:
            # Delegate to BackupService which handles compress + encrypt + upload
            BackupService.create_snapshot(tenant)
            EventLog._force_update_sync_status(batch_uuids, EventLog.SYNC_STATUS_SYNCED)
            synced_total += len(batch_uuids)
        except Exception as exc:
            logger.warning("Batch upload failed (offset=%d): %s", offset, exc)
            _update_sync_status(tenant, device_id, SyncStatus.STATUS_ERROR, total - synced_total,
                                 error_message=str(exc))
            # Exponential backoff retry
            delay = RETRY_DELAY * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=delay)

        offset += BATCH_SIZE

    _update_sync_status(tenant, device_id, SyncStatus.STATUS_SYNCED, 0)
    logger.info("Synced %d events for tenant %s.", synced_total, tenant_id)


def _update_sync_status(tenant, device_id, status, pending_count, error_message=''):
    from sync.models import SyncStatus
    obj, _ = SyncStatus.objects.get_or_create(
        tenant=tenant,
        device_id=device_id,
        defaults={'status': status},
    )
    obj.status               = status
    obj.pending_events_count = pending_count
    obj.error_message        = error_message
    if status == SyncStatus.STATUS_SYNCED:
        obj.last_synced_at = timezone.now()
    obj.save(update_fields=['status', 'pending_events_count', 'error_message', 'last_synced_at', 'updated_at'])
