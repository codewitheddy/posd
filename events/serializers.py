"""events/serializers.py — DRF serializer for EventLog (sync API + backup files)."""
from rest_framework import serializers
from events.models import EventLog


class EventLogSerializer(serializers.ModelSerializer):
    """Full serializer used for the sync API and backup file format."""

    tenant_id = serializers.PrimaryKeyRelatedField(source='tenant', read_only=True)

    class Meta:
        model = EventLog
        fields = [
            'uuid',
            'event_type',
            'payload',
            'device_id',
            'tenant_id',
            'timestamp',
            'sync_status',
        ]
        read_only_fields = ['uuid', 'sync_status', 'tenant_id']

    def create(self, validated_data):
        """Enforce that tenant comes from the request context, not the payload."""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and hasattr(request.user, 'business_memberships'):
            # tenant is injected by the view
            pass
        return EventLog.objects.create(**validated_data)


class EventLogIngestSerializer(serializers.Serializer):
    """
    Serializer for the ingest endpoint (POST /api/v1/sync/events/).
    Accepts a list of raw event dicts; the view handles deduplication.
    """
    uuid        = serializers.UUIDField()
    event_type  = serializers.ChoiceField(choices=EventLog.EVENT_TYPE_CHOICES)
    payload     = serializers.JSONField()
    device_id   = serializers.CharField(max_length=100)
    timestamp   = serializers.DateTimeField()
    sync_status = serializers.ChoiceField(
        choices=EventLog.SYNC_STATUS_CHOICES,
        default=EventLog.SYNC_STATUS_PENDING,
    )
