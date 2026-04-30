from django.contrib import admin
from django.utils.html import format_html
from backup.models import BackupSnapshot, TenantBackupSettings


class TenantBackupSettingsInline(admin.StackedInline):
    model   = TenantBackupSettings
    extra   = 0
    can_delete = False
    fields  = ['backup_mode', 'schedule_interval_hours', 'retention_days',
                'storage_mode', 'local_storage_limit_mb', 'encryption_key_id']


@admin.register(TenantBackupSettings)
class TenantBackupSettingsAdmin(admin.ModelAdmin):
    list_display  = ['tenant', 'backup_mode', 'schedule_interval_hours', 'retention_days', 'storage_mode']
    list_filter   = ['backup_mode', 'storage_mode']
    search_fields = ['tenant__name']


@admin.register(BackupSnapshot)
class BackupSnapshotAdmin(admin.ModelAdmin):
    list_display  = ['tenant', 'version', 'status_badge', 'event_count', 'file_size_bytes', 'created_at']
    list_filter   = ['status', 'created_at']
    search_fields = ['tenant__name', 'storage_key']
    readonly_fields = ['tenant', 'version', 'storage_key', 'file_size_bytes',
                       'checksum_sha256', 'encryption_key_id', 'event_count', 'status', 'created_at']
    date_hierarchy = 'created_at'

    def status_badge(self, obj):
        colours = {
            'uploaded':  'green',
            'pending':   'orange',
            'corrupted': 'red',
            'deleted':   'grey',
        }
        colour = colours.get(obj.status, 'black')
        return format_html('<span style="color:{}">{}</span>', colour, obj.get_status_display())
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False


# ── Platform-wide backup health dashboard ────────────────────────────────────

class BackupHealthAdminSite:
    """Custom admin view registered on the default admin site."""
    pass


# Register the inline on the existing Business admin
def _register_inline():
    try:
        from pos.models import Business
        from django.contrib.admin import site
        if Business in site._registry:
            site._registry[Business].inlines = list(
                site._registry[Business].inlines
            ) + [TenantBackupSettingsInline]
    except Exception:
        pass


_register_inline()
