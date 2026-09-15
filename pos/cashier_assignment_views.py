"""
Web Views for Cashier-to-Till Assignment and Cross-Branch Transfer Management Dashboard.
"""
from decimal import Decimal
from datetime import datetime, date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.models import User

from .models import (
    Business, Branch, BranchMembership, POSTerminal,
    CashierTillAssignment, CashierTransferRequest, CashierAssignmentAuditLog
)
from .decorators import business_required
from .cashier_assignment_service import CashierAssignmentService


@login_required
@business_required
def cashier_assignment_dashboard(request, slug=None):
    """
    Main Enterprise Dashboard for Cashier Till Assignments, Cross-Branch Transfers,
    Labor Reporting, and Audit Logs.
    """
    business = request.business
    user = request.user

    # 1. Selected Branch (defaults to active branch or first active branch)
    branch_id = request.GET.get('branch_id')
    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')
    
    current_branch = None
    if branch_id:
        current_branch = Branch.objects.filter(pk=branch_id, business=business).first()
    if not current_branch:
        current_branch = getattr(request, 'branch', None) or branches.first()

    # 2. Branch Till Status & Metrics
    branch_status = None
    if current_branch:
        branch_status = CashierAssignmentService.get_branch_status(current_branch)

    # 3. Available Cashiers for Assignment
    # Get cashiers eligible at this branch (home branch or active approved transfer)
    eligible_cashiers = []
    all_cashiers = list(User.objects.filter(
        business_memberships__business=business,
        business_memberships__is_active=True
    ).distinct().order_by('first_name', 'last_name', 'username'))

    today = timezone.localdate()
    for c in all_cashiers:
        active_b, is_temp, transfer_obj = CashierAssignmentService.get_active_cashier_branch(c, today)
        is_at_current_branch = (active_b and active_b.id == current_branch.id) if current_branch else False
        eligible_cashiers.append({
            'user': c,
            'name': c.get_full_name() or c.username,
            'active_branch': active_b,
            'is_at_current_branch': is_at_current_branch,
            'is_temporary': is_temp,
            'transfer': transfer_obj,
        })

    # 4. Transfer Requests (Incoming to current branch, Outgoing from current branch, and All)
    pending_incoming = CashierTransferRequest.objects.filter(
        business=business, to_branch=current_branch, status='pending'
    ).select_related('cashier', 'from_branch', 'requested_by') if current_branch else []

    all_transfers = CashierTransferRequest.objects.filter(
        business=business
    ).select_related('cashier', 'from_branch', 'to_branch', 'requested_by', 'approved_by').order_by('-created_at')[:50]

    # 5. Shift Assignments
    status_filter = request.GET.get('status_filter', '')
    assignments_qs = CashierTillAssignment.objects.filter(business=business)
    if current_branch:
        assignments_qs = assignments_qs.filter(branch=current_branch)
    if status_filter:
        assignments_qs = assignments_qs.filter(status=status_filter)
    assignments = assignments_qs.select_related('cashier', 'terminal', 'branch', 'assigned_by').order_by('-shift_start')[:100]

    # 6. Labor Cost & Hours Report
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    labor_report = None
    if current_branch:
        start_d = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else today.replace(day=1)
        end_d = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else today
        labor_report = CashierAssignmentService.get_branch_labor_report(
            branch=current_branch,
            start_date=start_d,
            end_date=end_d
        )

    # 7. Audit Trail
    audit_logs = CashierAssignmentAuditLog.objects.filter(
        business=business
    ).select_related('cashier', 'performed_by', 'from_branch', 'to_branch', 'terminal', 'assignment').order_by('-timestamp')[:100]

    return render(request, 'pos/branches/cashier_assignments.html', {
        'business': business,
        'branches': branches,
        'current_branch': current_branch,
        'branch_status': branch_status,
        'eligible_cashiers': eligible_cashiers,
        'all_cashiers': all_cashiers,
        'pending_incoming': pending_incoming,
        'all_transfers': all_transfers,
        'assignments': assignments,
        'labor_report': labor_report,
        'audit_logs': audit_logs,
        'status_filter': status_filter,
        'start_date_str': start_date_str or (today.replace(day=1).strftime('%Y-%m-%d')),
        'end_date_str': end_date_str or (today.strftime('%Y-%m-%d')),
        'today': today,
    })


@login_required
@business_required
@require_POST
def request_transfer_view(request, slug=None):
    """Handle Transfer Request Submission"""
    business = request.business
    cashier_id = request.POST.get('cashier_id')
    from_branch_id = request.POST.get('from_branch_id')
    to_branch_id = request.POST.get('to_branch_id')
    transfer_type = request.POST.get('transfer_type', 'temporary')
    start_date = request.POST.get('start_date')
    end_date = request.POST.get('end_date') or None
    reason = request.POST.get('reason', '').strip()

    if not all([cashier_id, from_branch_id, to_branch_id, start_date]):
        messages.error(request, 'All fields are required to request a cashier transfer.')
        return redirect('cashier_assignment_dashboard')

    cashier = get_object_or_404(User, pk=cashier_id)
    from_branch = get_object_or_404(Branch, pk=from_branch_id, business=business)
    to_branch = get_object_or_404(Branch, pk=to_branch_id, business=business)

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
        messages.success(request, f'Transfer request for {cashier.get_full_name() or cashier.username} to {to_branch.name} submitted successfully (Pending approval from {to_branch.name} manager).')
    except Exception as e:
        messages.error(request, f'Error requesting transfer: {str(e)}')

    return redirect('cashier_assignment_dashboard')


@login_required
@business_required
@require_POST
def approve_transfer_view(request, pk, slug=None):
    """Approve a pending transfer request"""
    business = request.business
    transfer = get_object_or_404(CashierTransferRequest, pk=pk, business=business)
    notes = request.POST.get('notes', '').strip()

    try:
        CashierAssignmentService.approve_transfer(
            transfer_request=transfer,
            approved_by=request.user,
            notes=notes
        )
        messages.success(request, f'Transfer request for {transfer.cashier.get_full_name() or transfer.cashier.username} to {transfer.to_branch.name} approved successfully.')
    except Exception as e:
        messages.error(request, f'Error approving transfer: {str(e)}')

    return redirect('cashier_assignment_dashboard')


@login_required
@business_required
@require_POST
def reject_transfer_view(request, pk, slug=None):
    """Reject a pending transfer request"""
    business = request.business
    transfer = get_object_or_404(CashierTransferRequest, pk=pk, business=business)
    rejection_reason = request.POST.get('rejection_reason', '').strip()

    try:
        CashierAssignmentService.reject_transfer(
            transfer_request=transfer,
            rejected_by=request.user,
            rejection_reason=rejection_reason
        )
        messages.warning(request, f'Transfer request for {transfer.cashier.get_full_name() or transfer.cashier.username} rejected.')
    except Exception as e:
        messages.error(request, f'Error rejecting transfer: {str(e)}')

    return redirect('cashier_assignment_dashboard')


@login_required
@business_required
@require_POST
def cancel_transfer_view(request, pk, slug=None):
    """Cancel a pending transfer request"""
    business = request.business
    transfer = get_object_or_404(CashierTransferRequest, pk=pk, business=business)
    reason = request.POST.get('reason', '').strip()

    try:
        CashierAssignmentService.cancel_transfer(
            transfer_request=transfer,
            user=request.user,
            reason=reason
        )
        messages.info(request, f'Transfer request for {transfer.cashier.get_full_name() or transfer.cashier.username} cancelled.')
    except Exception as e:
        messages.error(request, f'Error cancelling transfer: {str(e)}')

    return redirect('cashier_assignment_dashboard')


@login_required
@business_required
@require_POST
def assign_till_view(request, slug=None):
    """Schedule / Assign a cashier to a till"""
    business = request.business
    cashier_id = request.POST.get('cashier_id')
    terminal_id = request.POST.get('terminal_id')
    branch_id = request.POST.get('branch_id')
    shift_start_str = request.POST.get('shift_start')
    shift_end_str = request.POST.get('shift_end')
    hourly_rate_str = request.POST.get('hourly_rate', '0.00').strip()
    notes = request.POST.get('notes', '').strip()

    if not all([cashier_id, terminal_id, branch_id, shift_start_str, shift_end_str]):
        messages.error(request, 'Please provide cashier, till, branch, and shift start/end times.')
        return redirect('cashier_assignment_dashboard')

    cashier = get_object_or_404(User, pk=cashier_id)
    branch = get_object_or_404(Branch, pk=branch_id, business=business)
    terminal = get_object_or_404(POSTerminal, pk=terminal_id, business=business)

    try:
        shift_start = datetime.fromisoformat(shift_start_str)
        if timezone.is_naive(shift_start):
            shift_start = timezone.make_aware(shift_start)
            
        shift_end = datetime.fromisoformat(shift_end_str)
        if timezone.is_naive(shift_end):
            shift_end = timezone.make_aware(shift_end)

        hourly_rate = Decimal(hourly_rate_str) if hourly_rate_str else Decimal('0.00')

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
        messages.success(request, f'Shift scheduled: {cashier.get_full_name() or cashier.username} assigned to {terminal.name} ({terminal.terminal_code}) from {shift_start:%H:%M} to {shift_end:%H:%M}.')
    except Exception as e:
        messages.error(request, f'Assignment failed: {str(e)}')

    return redirect('cashier_assignment_dashboard')


@login_required
@business_required
@require_POST
def activate_till_view(request, pk, slug=None):
    """Activate a scheduled assignment"""
    business = request.business
    assignment = get_object_or_404(CashierTillAssignment, pk=pk, business=business)

    try:
        CashierAssignmentService.activate_assignment(assignment=assignment, activated_by=request.user)
        messages.success(request, f'Till {assignment.terminal.terminal_code} is now ACTIVE with cashier {assignment.cashier.get_full_name() or assignment.cashier.username}.')
    except Exception as e:
        messages.error(request, f'Activation failed: {str(e)}')

    return redirect('cashier_assignment_dashboard')


@login_required
@business_required
@require_POST
def release_till_view(request, pk, slug=None):
    """Release a till and complete shift"""
    business = request.business
    assignment = get_object_or_404(CashierTillAssignment, pk=pk, business=business)
    notes = request.POST.get('notes', '').strip()

    try:
        CashierAssignmentService.release_till(assignment=assignment, released_by=request.user, notes=notes)
        messages.success(request, f'Till {assignment.terminal.terminal_code} released successfully. Shift marked completed.')
    except Exception as e:
        messages.error(request, f'Release failed: {str(e)}')

    return redirect('cashier_assignment_dashboard')
