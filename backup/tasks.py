"""backup/tasks.py — Scheduled backup and retention Celery tasks."""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def run_scheduled_backup(tenant_id: int):
    """Triggered by Celery Beat for tenants in scheduled mode."""
    from backup.services import BackupService
    from pos.models import Business
    from sync.models import SyncStatus

    try:
        tenant = Business.objects.get(pk=tenant_id)
    except Business.DoesNotExist:
        logger.error("run_scheduled_backup: tenant %s not found.", tenant_id)
        return

    try:
        snap = BackupService.create_snapshot(tenant)
        # Update SyncStatus
        SyncStatus.objects.update_or_create(
            tenant=tenant,
            device_id='scheduled',
            defaults={
                'status':               SyncStatus.STATUS_SYNCED,
                'last_synced_at':       timezone.now(),
                'pending_events_count': 0,
                'error_message':        '',
            },
        )
        logger.info("Scheduled backup completed for tenant %s — snapshot v%s.", tenant_id, snap.version)
    except Exception as exc:
        logger.exception("Scheduled backup failed for tenant %s: %s", tenant_id, exc)
        SyncStatus.objects.update_or_create(
            tenant=tenant,
            device_id='scheduled',
            defaults={
                'status':        SyncStatus.STATUS_ERROR,
                'error_message': str(exc),
            },
        )


@shared_task
def enforce_retention_policy():
    """Daily task: delete expired snapshots for all tenants."""
    from backup.services import BackupService
    from pos.models import Business

    for tenant in Business.objects.filter(is_active=True):
        try:
            BackupService.delete_expired_snapshots(tenant)
        except Exception as exc:
            logger.warning("Retention cleanup failed for tenant %s: %s", tenant.pk, exc)


def register_scheduled_backup(tenant):
    """
    Register (or update) a Celery Beat PeriodicTask for a tenant in scheduled mode.
    Requires django-celery-beat to be installed.
    """
    try:
        from django_celery_beat.models import IntervalSchedule, PeriodicTask
        import json

        settings = tenant.backup_settings
        hours    = settings.schedule_interval_hours or 24

        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=hours,
            period=IntervalSchedule.HOURS,
        )
        PeriodicTask.objects.update_or_create(
            name=f'backup_tenant_{tenant.pk}',
            defaults={
                'interval':  schedule,
                'task':      'backup.tasks.run_scheduled_backup',
                'args':      json.dumps([tenant.pk]),
                'enabled':   True,
            },
        )
        logger.info("Registered scheduled backup for tenant %s every %dh.", tenant.pk, hours)
    except ImportError:
        logger.warning("django-celery-beat not installed — scheduled backup not registered.")
    except Exception as exc:
        logger.error("Failed to register scheduled backup for tenant %s: %s", tenant.pk, exc)


def revoke_scheduled_backup(tenant):
    """Remove the Celery Beat PeriodicTask for a tenant."""
    try:
        from django_celery_beat.models import PeriodicTask
        PeriodicTask.objects.filter(name=f'backup_tenant_{tenant.pk}').delete()
        logger.info("Revoked scheduled backup for tenant %s.", tenant.pk)
    except ImportError:
        pass
    except Exception as exc:
        logger.error("Failed to revoke scheduled backup for tenant %s: %s", tenant.pk, exc)
