"""restore/views.py — Restore API endpoint."""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class RestoreView(APIView):
    """POST /api/v1/restore/ — trigger a full or partial restore."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from pos.models import Business
        from restore.services import RestoreService

        tenant_id       = request.data.get('tenant_id')
        snapshot_version = request.data.get('snapshot_version')
        scope           = request.data.get('scope')

        if not tenant_id:
            return Response({'error': 'tenant_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant = Business.objects.get(pk=tenant_id)
        except Business.DoesNotExist:
            return Response({'error': 'Tenant not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            if scope:
                result = RestoreService.restore_scoped(tenant, scope, request.user)
            elif snapshot_version:
                result = RestoreService.restore_version(tenant, int(snapshot_version), request.user)
            else:
                result = RestoreService.restore_latest(tenant, request.user)

            return Response(result, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.exception("Restore failed for tenant %s", tenant_id)
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
