"""backup/views.py — Manual backup and version listing API endpoints."""
import logging

from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

BACKUP_LOCK_TIMEOUT = 600  # 10 minutes


def _get_tenant(request):
    """Return the Business for the authenticated user."""
    from pos.models import Business, BusinessMembership
    membership = BusinessMembership.objects.filter(
        user=request.user, is_active=True
    ).select_related('business').first()
    return membership.business if membership else None


class ManualBackupView(APIView):
    """POST /api/v1/backup/manual/ — trigger an on-demand backup."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response({'error': 'No active business found.'}, status=status.HTTP_403_FORBIDDEN)

        lock_key = f'backup_lock_{tenant.pk}'
        acquired = cache.add(lock_key, '1', BACKUP_LOCK_TIMEOUT)
        if not acquired:
            return Response(
                {'error': 'A backup is already in progress for this tenant.'},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            from backup.services import BackupService
            snapshot = BackupService.create_snapshot(tenant, triggered_by=request.user)

            if request.query_params.get('download') == 'true':
                from backup.cloud import CloudStorageClient
                client = CloudStorageClient()
                data = client.download(snapshot.storage_key)
                resp = HttpResponse(data, content_type='application/gzip')
                resp['Content-Disposition'] = (
                    f'attachment; filename="backup_{tenant.pk}_{snapshot.version}.json.gz"'
                )
                return resp

            return Response({
                'snapshot_id':  snapshot.pk,
                'version':      snapshot.version,
                'file_size':    snapshot.file_size_bytes,
                'checksum':     snapshot.checksum_sha256,
                'timestamp':    snapshot.created_at.isoformat(),
                'event_count':  snapshot.event_count,
            }, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.exception("Manual backup failed for tenant %s", tenant.pk)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            cache.delete(lock_key)


class BackupVersionsView(APIView):
    """GET /api/v1/backup/versions/ — list available snapshot versions."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = _get_tenant(request)
        if not tenant:
            return Response({'error': 'No active business found.'}, status=status.HTTP_403_FORBIDDEN)

        from backup.models import BackupSnapshot
        snapshots = BackupSnapshot.objects.filter(
            tenant=tenant
        ).exclude(status='deleted').order_by('-version').values(
            'version', 'created_at', 'event_count', 'file_size_bytes', 'status'
        )
        return Response({'versions': list(snapshots)})
