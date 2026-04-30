from django.contrib import admin
from django.utils.html import format_html
from sync.models import SyncStatus


@admin.register(SyncStatus)
class SyncStatusAdmin(admin.ModelAdmin):
    list_display  = ['tenant', 'device_id', 'status_badge', 'pending_events_count',
                     'last_synced_at', 'updated_at']
    list_filter   = ['status', 'updated_at']
    search_fields = ['tenant__name', 'device_id']
    readonly_fields = ['tenant', 'device_id', 'last_synced_at', 'pending_events_count',
                       'status', 'error_message', 'updated_at']

    def status_badge(self, obj):
        colours = {'synced': 'green', 'pending': 'orange', 'error': 'red'}
        colour  = colours.get(obj.status, 'black')
        return format_html('<span style="color:{};font-weight:bold">{}</span>',
                           colour, obj.get_status_display())
    status_badge.short_description = 'Status'

    def has_add_permission(self, request):
        return False
