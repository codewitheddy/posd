"""sync/views.py — Event ingest and sync status API endpoints."""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _get_tenant(request):
    from pos.models import BusinessMembership
    membership = BusinessMembership.objects.filter(
        user=request.user, is_active=True
    ).select_related('business').first()
    return membership.business if membership else None


class SyncEventsView(APIView):
    """POST /api/v1/sync/events/ — ingest a batch of EventLog records."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response({'error': 'No active business found.'}, status=status.HTTP_403_FORBIDDEN)

        records = request.data if isinstance(request.data, list) else request.data.get('events', [])
        if not records:
            return Response({'accepted': 0, 'duplicates': 0})

        from events.models import EventLog
        from events.serializers import EventLogIngestSerializer

        accepted = 0
        duplicates = 0
        to_create = []

        incoming_uuids = [str(r.get('uuid', '')) for r in records]
        existing_uuids = set(
            str(u) for u in EventLog.objects.filter(
                uuid__in=incoming_uuids, tenant=tenant
            ).values_list('uuid', flat=True)
        )

        for record in records:
            uid = str(record.get('uuid', ''))
            if uid in existing_uuids:
                duplicates += 1
                continue
            ser = EventLogIngestSerializer(data=record)
            if ser.is_valid():
                to_create.append(EventLog(
                    uuid=ser.validated_data['uuid'],
                    tenant=tenant,
                    event_type=ser.validated_data['event_type'],
                    payload=ser.validated_data['payload'],
                    device_id=ser.validated_data['device_id'],
                    timestamp=ser.validated_data['timestamp'],
                    sync_status=EventLog.SYNC_STATUS_PENDING,
                ))
                accepted += 1
            else:
                logger.warning("Invalid event record skipped: %s", ser.errors)

        if to_create:
            EventLog.objects.bulk_create(to_create, ignore_conflicts=True)

        return Response({'accepted': accepted, 'duplicates': duplicates})


class SyncStatusView(APIView):
    """GET /api/v1/sync/status/ — return SyncStatus for all devices of the tenant."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response({'error': 'No active business found.'}, status=status.HTTP_403_FORBIDDEN)

        from sync.models import SyncStatus
        from backup.services import BackupService

        statuses = list(
            SyncStatus.objects.filter(tenant=tenant).values(
                'device_id', 'last_synced_at', 'pending_events_count', 'status', 'error_message'
            )
        )

        storage = BackupService.get_local_storage_usage(tenant)

        return Response({
            'devices': statuses,
            'storage': storage,
        })
