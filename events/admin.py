from django.contrib import admin
from events.models import EventLog


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display  = ['uuid', 'tenant', 'event_type', 'device_id', 'sync_status', 'timestamp']
    list_filter   = ['event_type', 'sync_status', 'timestamp']
    search_fields = ['uuid', 'device_id', 'tenant__name']
    readonly_fields = ['uuid', 'tenant', 'event_type', 'payload', 'device_id', 'timestamp', 'sync_status', 'created_at']
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
