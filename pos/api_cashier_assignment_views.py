"""
REST API ViewSets for Cashier-to-Till Assignment and Cross-Branch Transfer System.
"""
from decimal import Decimal
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (
    Branch, POSTerminal, CashierTillAssignment,
    CashierTransferRequest, CashierAssignmentAuditLog, User
)
from .serializers import (
    CashierTillAssignmentSerializer, CashierTransferRequestSerializer,
    CashierAssignmentAuditLogSerializer, POSTerminalSerializer
)
from .cashier_assignment_service import CashierAssignmentService
from .permissions import BranchScopeMixin, get_request_business


class CashierTransferRequestViewSet(BranchScopeMixin, viewsets.ModelViewSet):
    """
    REST API ViewSet for Managing Cross-Branch Cashier Transfers.
    """
    serializer_class = CashierTransferRequestSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'transfer_type', 'from_branch', 'to_branch', 'cashier']
    search_fields = ['cashier__username', 'cashier__first_name', 'cashier__last_name', 'reason']
    ordering_fields = ['created_at', 'start_date', 'status']

    def get_queryset(self):
        business = get_request_business(self.request) or getattr(self.request, 'business', None)
        if not business:
            if self.request.user.is_superuser:
                return CashierTransferRequest.objects.all().select_related('cashier', 'from_branch', 'to_branch', 'requested_by', 'approved_by')
            return CashierTransferRequest.objects.none()
        return CashierTransferRequest.objects.filter(business=business).select_related('cashier', 'from_branch', 'to_branch', 'requested_by', 'approved_by')

    def create(self, request, *args, **kwargs):
        """Request a new cashier transfer."""
        cashier_id = request.data.get('cashier')
        from_branch_id = request.data.get('from_branch')
        to_branch_id = request.data.get('to_branch')
        transfer_type = request.data.get('transfer_type', 'temporary')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        reason = request.data.get('reason', '')

        if not all([cashier_id, from_branch_id, to_branch_id, start_date]):
            return Response(
                {'error': 'cashier, from_branch, to_branch, and start_date are required fields.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cashier = get_object_or_404(User, pk=cashier_id)
        from_branch = get_object_or_404(Branch, pk=from_branch_id)
        to_branch = get_object_or_404(Branch, pk=to_branch_id)
        business = get_request_business(request) or getattr(request, 'business', None) or from_branch.business

        try:
            transfer = CashierAssignmentService.request_transfer(
                business=business,
                cashier=cashier,
                from_branch=from_branch,
                to_branch=to_branch,
                transfer_type=transfer_type,
                start_date=start_date,
                end_date=end_date,
                requested_by=request.user,
                reason=reason
            )
            serializer = self.get_serializer(transfer)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a pending transfer request."""
        transfer = self.get_object()
        notes = request.data.get('notes', '')
        try:
            approved = CashierAssignmentService.approve_transfer(
                transfer_request=transfer,
                approved_by=request.user,
                notes=notes
            )
            return Response(self.get_serializer(approved).data)
        except PermissionError as pe:
            return Response({'error': str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a pending transfer request."""
        transfer = self.get_object()
        rejection_reason = request.data.get('rejection_reason', '')
        try:
            rejected = CashierAssignmentService.reject_transfer(
                transfer_request=transfer,
                rejected_by=request.user,
                rejection_reason=rejection_reason
            )
            return Response(self.get_serializer(rejected).data)
        except PermissionError as pe:
            return Response({'error': str(pe)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a pending transfer request."""
        transfer = self.get_object()
        reason = request.data.get('reason', '')
        try:
            cancelled = CashierAssignmentService.cancel_transfer(
                transfer_request=transfer,
                user=request.user,
                reason=reason
            )
            return Response(self.get_serializer(cancelled).data)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)


class CashierTillAssignmentViewSet(BranchScopeMixin, viewsets.ModelViewSet):
    """
    REST API ViewSet for Managing Cashier Till Assignments.
    """
    serializer_class = CashierTillAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status', 'branch', 'terminal', 'cashier']
    ordering_fields = ['shift_start', 'shift_end', 'status']

    def get_queryset(self):
        business = get_request_business(self.request) or getattr(self.request, 'business', None)
        if not business:
            if self.request.user.is_superuser:
                return CashierTillAssignment.objects.all().select_related('cashier', 'terminal', 'branch', 'assigned_by')
            return CashierTillAssignment.objects.none()
        return CashierTillAssignment.objects.filter(business=business).select_related('cashier', 'terminal', 'branch', 'assigned_by')

    def create(self, request, *args, **kwargs):
        """Assign a cashier to a till with schedule conflict prevention."""
        cashier_id = request.data.get('cashier')
        terminal_id = request.data.get('terminal')
        branch_id = request.data.get('branch')
        shift_start = request.data.get('shift_start')
        shift_end = request.data.get('shift_end')
        hourly_rate_val = request.data.get('hourly_rate', '0.00')
        notes = request.data.get('notes', '')

        if not all([cashier_id, terminal_id, branch_id, shift_start, shift_end]):
            return Response(
                {'error': 'cashier, terminal, branch, shift_start, and shift_end are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cashier = get_object_or_404(User, pk=cashier_id)
        terminal = get_object_or_404(POSTerminal, pk=terminal_id)
        branch = get_object_or_404(Branch, pk=branch_id)
        business = get_request_business(request) or getattr(request, 'business', None) or branch.business

        try:
            hourly_rate = Decimal(str(hourly_rate_val))
        except Exception:
            hourly_rate = Decimal('0.00')

        try:
            assignment = CashierAssignmentService.assign_cashier_to_till(
                business=business,
                cashier=cashier,
                terminal=terminal,
                branch=branch,
                shift_start=shift_start,
                shift_end=shift_end,
                assigned_by=request.user,
                hourly_rate=hourly_rate,
                notes=notes
            )
            return Response(self.get_serializer(assignment).data, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate an assignment when the cashier starts their till session."""
        assignment = self.get_object()
        try:
            activated = CashierAssignmentService.activate_assignment(
                assignment=assignment,
                activated_by=request.user
            )
            return Response(self.get_serializer(activated).data)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        """Release a till and mark the shift completed."""
        assignment = self.get_object()
        notes = request.data.get('notes', '')
        try:
            released = CashierAssignmentService.release_till(
                assignment=assignment,
                released_by=request.user,
                notes=notes
            )
            return Response(self.get_serializer(released).data)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)


class CashierAssignmentAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only REST API ViewSet for Cashier Assignment and Transfer Audit Logs.
    """
    serializer_class = CashierAssignmentAuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['action', 'cashier', 'from_branch', 'to_branch', 'terminal']
    ordering_fields = ['timestamp']

    def get_queryset(self):
        business = get_request_business(self.request) or getattr(self.request, 'business', None)
        if not business:
            if self.request.user.is_superuser:
                return CashierAssignmentAuditLog.objects.all().select_related('cashier', 'performed_by', 'from_branch', 'to_branch', 'terminal')
            return CashierAssignmentAuditLog.objects.none()
        return CashierAssignmentAuditLog.objects.filter(business=business).select_related('cashier', 'performed_by', 'from_branch', 'to_branch', 'terminal')


class BranchTillStatusView(APIView):
    """
    REST API endpoint for live branch till map and active cashiers:
    GET /api/v1/branches/{branch_id}/till-status/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, branch_id):
        branch = get_object_or_404(Branch, pk=branch_id)
        status_data = CashierAssignmentService.get_branch_status(branch)
        
        # Serialize response
        tills_serialized = []
        for t in status_data['tills']:
            tills_serialized.append({
                'terminal_id': t['terminal'].id,
                'name': t['terminal'].name,
                'terminal_code': t['terminal'].terminal_code,
                'status': t['status'],
                'status_label': t['status_label'],
                'badge_class': t['badge_class'],
                'active_cashier': {
                    'id': t['active_assignment'].cashier.id,
                    'name': t['active_assignment'].cashier.get_full_name() or t['active_assignment'].cashier.username,
                    'shift_start': t['active_assignment'].shift_start,
                    'shift_end': t['active_assignment'].shift_end,
                } if t['active_assignment'] else None
            })

        return Response({
            'branch_id': branch.id,
            'branch_name': branch.name,
            'branch_code': branch.code,
            'total_tills': status_data['total_tills'],
            'available_tills': status_data['available_tills'],
            'in_use_tills': status_data['in_use_tills'],
            'offline_tills': status_data['offline_tills'],
            'tills': tills_serialized,
            'pending_incoming_count': len(status_data['pending_incoming']),
            'pending_outgoing_count': len(status_data['pending_outgoing']),
        })


class BranchLaborReportView(APIView):
    """
    REST API endpoint for branch labor cost & hours worked reporting:
    GET /api/v1/branches/{branch_id}/labor-report/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, branch_id):
        branch = get_object_or_404(Branch, pk=branch_id)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        report = CashierAssignmentService.get_branch_labor_report(
            branch=branch,
            start_date=start_date,
            end_date=end_date
        )

        return Response({
            'branch_id': branch.id,
            'branch_name': branch.name,
            'start_date': report['start_date'],
            'end_date': report['end_date'],
            'total_shifts': report['total_shifts'],
            'total_hours_worked': str(report['total_hours_worked']),
            'total_labor_cost': str(report['total_labor_cost']),
            'currency': 'KES',
            'cashiers': report['cashiers'],
        })

