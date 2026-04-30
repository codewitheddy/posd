"""backup/web_views.py — Tenant-facing backup settings UI."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from backup.models import BackupSnapshot, TenantBackupSettings


def _get_tenant(request):
    from pos.models import BusinessMembership
    m = BusinessMembership.objects.filter(user=request.user, is_active=True).select_related('business').first()
    return m.business if m else None


@login_required
def backup_settings_view(request):
    tenant = _get_tenant(request)
    if not tenant:
        messages.error(request, 'No active business found.')
        return redirect('business_list')

    settings, _ = TenantBackupSettings.objects.get_or_create(
        tenant=tenant,
        defaults={'backup_mode': TenantBackupSettings.MODE_AUTOMATIC,
                  'retention_days': 30,
                  'storage_mode': TenantBackupSettings.STORAGE_HYBRID},
    )

    from sync.models import SyncStatus
    sync_statuses = SyncStatus.objects.filter(tenant=tenant)

    # Map status to simple UI labels
    STATUS_LABELS = {
        SyncStatus.STATUS_SYNCED:  'Synced',
        SyncStatus.STATUS_PENDING: 'Syncing',
        SyncStatus.STATUS_ERROR:   'Error',
    }

    recent_snapshots = BackupSnapshot.objects.filter(tenant=tenant).order_by('-version')[:10]

    if request.method == 'POST':
        backup_mode             = request.POST.get('backup_mode', TenantBackupSettings.MODE_AUTOMATIC)
        schedule_interval_hours = request.POST.get('schedule_interval_hours') or None
        retention_days          = int(request.POST.get('retention_days', 30))
        storage_mode            = request.POST.get('storage_mode', TenantBackupSettings.STORAGE_HYBRID)
        local_storage_limit_mb  = request.POST.get('local_storage_limit_mb') or None

        settings.backup_mode             = backup_mode
        settings.schedule_interval_hours = int(schedule_interval_hours) if schedule_interval_hours else None
        settings.retention_days          = retention_days
        settings.storage_mode            = storage_mode
        settings.local_storage_limit_mb  = int(local_storage_limit_mb) if local_storage_limit_mb else None

        try:
            settings.full_clean()
            settings.save()

            # Register/revoke Celery Beat task
            from backup.tasks import register_scheduled_backup, revoke_scheduled_backup
            if backup_mode == TenantBackupSettings.MODE_SCHEDULED:
                register_scheduled_backup(tenant)
            else:
                revoke_scheduled_backup(tenant)

            messages.success(request, 'Backup settings saved.')
        except Exception as exc:
            messages.error(request, f'Error: {exc}')

        return redirect('backup_settings')

    context = {
        'settings':         settings,
        'sync_statuses':    sync_statuses,
        'status_labels':    STATUS_LABELS,
        'recent_snapshots': recent_snapshots,
        'backup_modes':     TenantBackupSettings.BACKUP_MODE_CHOICES,
        'storage_modes':    TenantBackupSettings.STORAGE_MODE_CHOICES,
        'valid_intervals':  TenantBackupSettings.VALID_INTERVALS,
    }
    return render(request, 'backup/settings.html', context)
