"""
Cashier Assignment & Cross-Branch Transfer Service Layer.
Enforces business rules for multi-branch supermarket cashier assignments,
cross-branch transfers, till availability, schedule conflict prevention, and labor reporting.
"""
from decimal import Decimal
from datetime import date, datetime
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum

from .models import (
    Business, Branch, BranchMembership, POSTerminal,
    CashierTillAssignment, CashierTransferRequest, CashierAssignmentAuditLog
)


class CashierAssignmentService:
    """
    Core service handling cashier scheduling, till assignments, cross-branch transfers,
    conflict prevention, and labor analytics.
    """

    # ── 1. CROSS-BRANCH TRANSFERS ─────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def request_transfer(cls, business, cashier, from_branch, to_branch, transfer_type,
                         start_date, end_date=None, requested_by=None, reason=''):
        """
        Request a permanent or temporary transfer of a cashier to another branch.
        """
        if from_branch.pk == to_branch.pk:
            raise ValueError("Origin and destination branches must be different.")

        if not start_date:
            raise ValueError("Start date is required for all transfer requests.")

        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

        if end_date and isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        if transfer_type == 'temporary':
            if not end_date:
                raise ValueError("End date is required for temporary transfers.")
            if end_date < start_date:
                raise ValueError("End date cannot be earlier than start date.")

        # Check for duplicate pending request for this cashier
        pending_exists = CashierTransferRequest.objects.filter(
            business=business,
            cashier=cashier,
            status='pending'
        ).exists()
        if pending_exists:
            raise ValueError(f"Cashier {cashier.get_full_name() or cashier.username} already has a pending transfer request.")

        transfer_request = CashierTransferRequest.objects.create(
            business=business,
            cashier=cashier,
            from_branch=from_branch,
            to_branch=to_branch,
            transfer_type=transfer_type,
            start_date=start_date,
            end_date=end_date if transfer_type == 'temporary' else None,
            status='pending',
            requested_by=requested_by,
            reason=reason or 'Operational requirement',
        )

        # Audit Log
        CashierAssignmentAuditLog.objects.create(
            business=business,
            cashier=cashier,
            action='transfer_requested',
            performed_by=requested_by,
            from_branch=from_branch,
            to_branch=to_branch,
            transfer_request=transfer_request,
            reason=reason,
            details={
                'transfer_type': transfer_type,
                'start_date': str(start_date),
                'end_date': str(end_date) if end_date else None,
            }
        )

        return transfer_request

    @classmethod
    def can_user_approve_transfer(cls, transfer_request, user):
        """
        Validation Rule 2: Transfer requests require approval from the receiving branch's manager
        or business owner / HQ admin.
        """
        if user.is_superuser:
            return True

        # Check business-wide owner or admin
        from .models import BusinessMembership
        bm = BusinessMembership.objects.filter(business=transfer_request.business, user=user, is_active=True).first()
        if bm and bm.role in ['owner', 'admin', 'hq_admin', 'manager']:
            return True

        # Check destination branch manager role
        dest_membership = BranchMembership.objects.filter(
            branch=transfer_request.to_branch,
            user=user,
            is_active=True,
            role__in=['branch_manager', 'manager', 'hq_admin']
        ).exists()

        return dest_membership

    @classmethod
    @transaction.atomic
    def approve_transfer(cls, transfer_request, approved_by, notes=''):
        """
        Approve a pending transfer request and update branch memberships.
        """
        if transfer_request.status != 'pending':
            raise ValueError(f"Cannot approve transfer with status '{transfer_request.status}'.")

        if not cls.can_user_approve_transfer(transfer_request, approved_by):
            raise PermissionError("Only managers of the receiving branch or business administrators can approve this transfer.")

        transfer_request.status = 'approved'
        transfer_request.approved_by = approved_by
        transfer_request.action_date = timezone.now()
        transfer_request.save(update_fields=['status', 'approved_by', 'action_date', 'updated_at'])

        cashier = transfer_request.cashier
        to_branch = transfer_request.to_branch
        from_branch = transfer_request.from_branch

        if transfer_request.transfer_type == 'permanent':
            # Update home branch membership to destination branch
            BranchMembership.objects.filter(
                user=cashier, branch=from_branch
            ).update(is_home_branch=False)

            membership, created = BranchMembership.objects.get_or_create(
                user=cashier,
                branch=to_branch,
                defaults={'role': 'cashier', 'is_home_branch': True, 'is_active': True}
            )
            if not created:
                membership.is_home_branch = True
                membership.is_active = True
                membership.save(update_fields=['is_home_branch', 'is_active'])
        else:
            # Temporary transfer: Ensure cashier has active membership at receiving branch without changing home branch
            BranchMembership.objects.get_or_create(
                user=cashier,
                branch=to_branch,
                defaults={'role': 'cashier', 'is_home_branch': False, 'is_active': True}
            )

        # Audit Log
        CashierAssignmentAuditLog.objects.create(
            business=transfer_request.business,
            cashier=cashier,
            action='transfer_approved',
            performed_by=approved_by,
            from_branch=from_branch,
            to_branch=to_branch,
            transfer_request=transfer_request,
            reason=notes or 'Approved by receiving manager',
            details={
                'transfer_type': transfer_request.transfer_type,
                'start_date': str(transfer_request.start_date),
                'end_date': str(transfer_request.end_date) if transfer_request.end_date else None,
            }
        )

        return transfer_request

    @classmethod
    @transaction.atomic
    def reject_transfer(cls, transfer_request, rejected_by, rejection_reason=''):
        """
        Reject a pending transfer request.
        """
        if transfer_request.status != 'pending':
            raise ValueError(f"Cannot reject transfer with status '{transfer_request.status}'.")

        if not cls.can_user_approve_transfer(transfer_request, rejected_by):
            raise PermissionError("Only managers of the receiving branch or business administrators can reject this transfer.")

        transfer_request.status = 'rejected'
        transfer_request.approved_by = rejected_by
        transfer_request.action_date = timezone.now()
        transfer_request.rejection_reason = rejection_reason or 'Rejected by receiving manager'
        transfer_request.save(update_fields=['status', 'approved_by', 'action_date', 'rejection_reason', 'updated_at'])

        # Audit Log
        CashierAssignmentAuditLog.objects.create(
            business=transfer_request.business,
            cashier=transfer_request.cashier,
            action='transfer_rejected',
            performed_by=rejected_by,
            from_branch=transfer_request.from_branch,
            to_branch=transfer_request.to_branch,
            transfer_request=transfer_request,
            reason=rejection_reason,
        )

        return transfer_request

    @classmethod
    @transaction.atomic
    def cancel_transfer(cls, transfer_request, user, reason=''):
        """
        Cancel a pending transfer request by the requester or administrator.
        """
        if transfer_request.status != 'pending':
            raise ValueError(f"Cannot cancel transfer with status '{transfer_request.status}'.")

        transfer_request.status = 'cancelled'
        transfer_request.action_date = timezone.now()
        transfer_request.rejection_reason = reason or 'Cancelled by requester'
        transfer_request.save(update_fields=['status', 'action_date', 'rejection_reason', 'updated_at'])

        CashierAssignmentAuditLog.objects.create(
            business=transfer_request.business,
            cashier=transfer_request.cashier,
            action='transfer_cancelled',
            performed_by=user,
            from_branch=transfer_request.from_branch,
            to_branch=transfer_request.to_branch,
            transfer_request=transfer_request,
            reason=reason,
        )

        return transfer_request

    # ── 2. DYNAMIC CASHIER BRANCH RESOLUTION & AUTO-REVERSION ────────────────

    @classmethod
    def get_active_cashier_branch(cls, cashier, target_date=None):
        """
        Resolves the cashier's active branch for a given date.
        Validation Rule 5: Temporary transfers automatically revert to home branch after end date.
        
        Returns:
            (branch: Branch, is_temporary: bool, transfer_request: CashierTransferRequest | None)
        """
        if target_date is None:
            target_date = timezone.localdate()
        elif isinstance(target_date, str):
            from django.utils.dateparse import parse_datetime, parse_date
            parsed_dt = parse_datetime(target_date)
            if parsed_dt:
                target_date = parsed_dt.date()
            else:
                parsed_d = parse_date(target_date)
                target_date = parsed_d if parsed_d else datetime.strptime(target_date[:10], '%Y-%m-%d').date()
        elif isinstance(target_date, datetime):
            target_date = target_date.date()

        # 1. Check for approved active transfers covering target_date
        active_transfer = CashierTransferRequest.objects.filter(
            cashier=cashier,
            status='approved',
            start_date__lte=target_date
        ).filter(
            Q(transfer_type='permanent') |
            Q(transfer_type='temporary', end_date__gte=target_date)
        ).order_by('-start_date').first()

        if active_transfer:
            return active_transfer.to_branch, (active_transfer.transfer_type == 'temporary'), active_transfer

        # 2. Fallback to Home Branch Membership
        home_membership = BranchMembership.objects.filter(
            user=cashier,
            is_home_branch=True,
            is_active=True
        ).select_related('branch').first()

        if home_membership:
            return home_membership.branch, False, None

        # 3. Fallback to any active branch membership
        any_membership = BranchMembership.objects.filter(
            user=cashier,
            is_active=True
        ).select_related('branch').first()

        if any_membership:
            return any_membership.branch, False, None

        # 4. Fallback to default branch
        default_branch = Branch.objects.filter(is_default=True, is_active=True).first() or Branch.objects.filter(is_active=True).first()
        return default_branch, False, None

    # ── 3. TILL & CASHIER AVAILABILITY & CONFLICT PREVENTION ──────────────────

    @classmethod
    def check_till_availability(cls, branch, terminal, shift_start, shift_end, exclude_assignment_id=None):
        """
        Validation Rule 3 & 4: Checks if till is active and available for the requested time window.
        A till can have only one active/scheduled cashier at a time.
        """
        if not terminal.is_active:
            return False, None, f"Terminal '{terminal.name}' ({terminal.terminal_code}) is marked inactive."

        if terminal.operational_status == 'offline':
            return False, None, f"Terminal '{terminal.name}' ({terminal.terminal_code}) is currently offline."

        if terminal.operational_status == 'maintenance':
            return False, None, f"Terminal '{terminal.name}' ({terminal.terminal_code}) is under maintenance."

        if terminal.branch_id != branch.id:
            return False, None, f"Terminal '{terminal.name}' belongs to {terminal.branch.name}, not {branch.name}."

        # Overlapping query: shift_start < existing.shift_end AND shift_end > existing.shift_start
        conflicts = CashierTillAssignment.objects.filter(
            terminal=terminal,
            status__in=['scheduled', 'active'],
            shift_start__lt=shift_end,
            shift_end__gt=shift_start
        )
        if exclude_assignment_id:
            conflicts = conflicts.exclude(pk=exclude_assignment_id)

        conflict = conflicts.select_related('cashier').first()
        if conflict:
            cashier_name = conflict.cashier.get_full_name() or conflict.cashier.username
            return False, conflict, f"Till '{terminal.terminal_code}' is already assigned to {cashier_name} from {conflict.shift_start:%H:%M} to {conflict.shift_end:%H:%M}."

        return True, None, "Till is available."

    @classmethod
    def check_cashier_availability(cls, cashier, shift_start, shift_end, exclude_assignment_id=None):
        """
        Validation Rule 7: Prevent scheduling conflicts across ANY branch for the cashier.
        """
        conflicts = CashierTillAssignment.objects.filter(
            cashier=cashier,
            status__in=['scheduled', 'active'],
            shift_start__lt=shift_end,
            shift_end__gt=shift_start
        )
        if exclude_assignment_id:
            conflicts = conflicts.exclude(pk=exclude_assignment_id)

        conflict = conflicts.select_related('branch', 'terminal').first()
        if conflict:
            return False, conflict, f"Cashier is already scheduled at {conflict.branch.name} (Till: {conflict.terminal.terminal_code}) from {conflict.shift_start:%H:%M} to {conflict.shift_end:%H:%M}."

        return True, None, "Cashier is available."

    # ── 4. TILL ASSIGNMENT & RELEASE ──────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def assign_cashier_to_till(cls, business, cashier, terminal, branch, shift_start, shift_end,
                               assigned_by=None, hourly_rate=Decimal('0.00'), notes=''):
        """
        Assigns a cashier to a till for a given shift window.
        Validates branch eligibility, till availability, and cashier availability.
        """
        from django.utils.dateparse import parse_datetime
        if isinstance(shift_start, str):
            parsed_start = parse_datetime(shift_start)
            if parsed_start:
                shift_start = parsed_start
            else:
                shift_start = datetime.fromisoformat(shift_start)

        if isinstance(shift_end, str):
            parsed_end = parse_datetime(shift_end)
            if parsed_end:
                shift_end = parsed_end
            else:
                shift_end = datetime.fromisoformat(shift_end)

        if shift_end <= shift_start:
            raise ValueError("Shift end time must be after shift start time.")

        # 1. Verify Cashier Branch Eligibility for the shift date
        shift_date = shift_start.date() if isinstance(shift_start, datetime) else shift_start
        active_branch, is_temp, transfer_obj = cls.get_active_cashier_branch(cashier, shift_date)

        if not active_branch or active_branch.id != branch.id:
            # Check if user has explicit active branch membership
            has_membership = BranchMembership.objects.filter(user=cashier, branch=branch, is_active=True).exists()
            if not has_membership:
                raise ValueError(
                    f"Cashier '{cashier.get_full_name() or cashier.username}' is not active at branch '{branch.name}' on {shift_date}. "
                    f"(Current active branch: {active_branch.name if active_branch else 'None'}). Request a cross-branch transfer first."
                )

        # 2. Check Till Availability
        till_ok, till_conflict, till_reason = cls.check_till_availability(branch, terminal, shift_start, shift_end)
        if not till_ok:
            CashierAssignmentAuditLog.objects.create(
                business=business,
                cashier=cashier,
                action='conflict_prevented',
                performed_by=assigned_by,
                from_branch=branch,
                to_branch=branch,
                terminal=terminal,
                reason=f"Till Conflict: {till_reason}"
            )
            raise ValueError(till_reason)

        # 3. Check Cashier Availability
        cashier_ok, cashier_conflict, cashier_reason = cls.check_cashier_availability(cashier, shift_start, shift_end)
        if not cashier_ok:
            CashierAssignmentAuditLog.objects.create(
                business=business,
                cashier=cashier,
                action='conflict_prevented',
                performed_by=assigned_by,
                from_branch=branch,
                to_branch=branch,
                terminal=terminal,
                reason=f"Cashier Overlap: {cashier_reason}"
            )
            raise ValueError(cashier_reason)

        # 4. Create Assignment
        assignment = CashierTillAssignment.objects.create(
            business=business,
            cashier=cashier,
            terminal=terminal,
            branch=branch,
            shift_start=shift_start,
            shift_end=shift_end,
            status='scheduled',
            hourly_rate=hourly_rate or Decimal('0.00'),
            assigned_by=assigned_by,
            notes=notes
        )

        # Audit Log
        CashierAssignmentAuditLog.objects.create(
            business=business,
            cashier=cashier,
            action='till_assigned',
            performed_by=assigned_by,
            from_branch=branch,
            to_branch=branch,
            terminal=terminal,
            assignment=assignment,
            reason=notes or 'Scheduled shift assignment',
            details={
                'shift_start': shift_start.isoformat() if hasattr(shift_start, 'isoformat') else str(shift_start),
                'shift_end': shift_end.isoformat() if hasattr(shift_end, 'isoformat') else str(shift_end),
                'hourly_rate': str(hourly_rate),
            }
        )

        return assignment

    @classmethod
    @transaction.atomic
    def activate_assignment(cls, assignment, actual_start=None, activated_by=None):
        """
        Activates a scheduled assignment when the cashier starts their till session.
        """
        if assignment.status not in ['scheduled', 'active']:
            raise ValueError(f"Cannot activate assignment with status '{assignment.status}'.")

        assignment.status = 'active'
        assignment.actual_start = actual_start or timezone.now()
        assignment.save(update_fields=['status', 'actual_start', 'updated_at'])

        # Mark terminal in-use
        terminal = assignment.terminal
        terminal.operational_status = 'in_use'
        terminal.save(update_fields=['operational_status'])

        CashierAssignmentAuditLog.objects.create(
            business=assignment.business,
            cashier=assignment.cashier,
            action='till_activated',
            performed_by=activated_by or assignment.cashier,
            from_branch=assignment.branch,
            to_branch=assignment.branch,
            terminal=terminal,
            assignment=assignment,
            reason='Cashier shift session started',
        )

        return assignment

    @classmethod
    @transaction.atomic
    def release_till(cls, assignment, actual_end=None, released_by=None, notes=''):
        """
        Releases an active/scheduled till assignment (marks completed and frees the till).
        """
        if assignment.status == 'completed':
            return assignment

        assignment.status = 'completed'
        assignment.actual_end = actual_end or timezone.now()
        if not assignment.actual_start:
            assignment.actual_start = assignment.shift_start
        if notes:
            assignment.notes = f"{assignment.notes}\nRelease note: {notes}".strip()
        assignment.save(update_fields=['status', 'actual_start', 'actual_end', 'notes', 'updated_at'])

        # Free the till if no other active assignment
        terminal = assignment.terminal
        other_active = CashierTillAssignment.objects.filter(
            terminal=terminal, status='active'
        ).exclude(pk=assignment.pk).exists()

        if not other_active:
            terminal.operational_status = 'available'
            terminal.save(update_fields=['operational_status'])

        CashierAssignmentAuditLog.objects.create(
            business=assignment.business,
            cashier=assignment.cashier,
            action='till_released',
            performed_by=released_by or assignment.cashier,
            from_branch=assignment.branch,
            to_branch=assignment.branch,
            terminal=terminal,
            assignment=assignment,
            reason=notes or 'Shift completed and till released',
            details={
                'hours_worked': str(assignment.calculate_hours_worked()),
                'labor_cost': str(assignment.calculate_labor_cost()),
            }
        )

        return assignment

    # ── 5. DASHBOARD ANALYTICS & LABOR REPORTING ──────────────────────────────

    @classmethod
    def get_branch_status(cls, branch, target_datetime=None):
        """
        Retrieves live operational metrics for a branch:
        tills status (available, in-use, offline), active cashiers, pending transfers.
        """
        if target_datetime is None:
            target_datetime = timezone.now()

        terminals = list(POSTerminal.objects.filter(branch=branch).order_by('terminal_code'))
        total_tills = len(terminals)
        
        tills_data = []
        available_count = 0
        in_use_count = 0
        offline_count = 0

        for t in terminals:
            active_assign = t.till_assignments.filter(status='active').select_related('cashier').first()
            if not t.is_active or t.operational_status == 'offline':
                status_key = 'offline'
                badge_class = 'bg-secondary'
                status_label = 'Offline'
                offline_count += 1
            elif t.operational_status == 'maintenance':
                status_key = 'maintenance'
                badge_class = 'bg-warning text-dark'
                status_label = 'Maintenance'
                offline_count += 1
            elif active_assign:
                status_key = 'in_use'
                badge_class = 'bg-success'
                cashier_name = active_assign.cashier.get_full_name() or active_assign.cashier.username
                status_label = f'In Use ({cashier_name})'
                in_use_count += 1
            else:
                status_key = 'available'
                badge_class = 'bg-primary'
                status_label = 'Available'
                available_count += 1

            tills_data.append({
                'terminal': t,
                'status': status_key,
                'status_label': status_label,
                'badge_class': badge_class,
                'active_assignment': active_assign,
            })

        # Active Cashiers on Duty
        active_assignments = list(CashierTillAssignment.objects.filter(
            branch=branch, status='active'
        ).select_related('cashier', 'terminal'))

        # Pending Transfers
        pending_incoming = list(CashierTransferRequest.objects.filter(
            to_branch=branch, status='pending'
        ).select_related('cashier', 'from_branch', 'requested_by'))

        pending_outgoing = list(CashierTransferRequest.objects.filter(
            from_branch=branch, status='pending'
        ).select_related('cashier', 'to_branch', 'requested_by'))

        return {
            'branch': branch,
            'total_tills': total_tills,
            'available_tills': available_count,
            'in_use_tills': in_use_count,
            'offline_tills': offline_count,
            'tills': tills_data,
            'active_assignments': active_assignments,
            'pending_incoming': pending_incoming,
            'pending_outgoing': pending_outgoing,
        }

    @classmethod
    def get_branch_labor_report(cls, branch, start_date=None, end_date=None):
        """
        Non-Functional Requirement: Labor cost and hours worked reporting by branch.
        """
        assignments = CashierTillAssignment.objects.filter(
            branch=branch,
            status__in=['active', 'completed']
        ).select_related('cashier', 'terminal')

        if start_date:
            assignments = assignments.filter(shift_start__date__gte=start_date)
        if end_date:
            assignments = assignments.filter(shift_end__date__lte=end_date)

        total_hours = Decimal('0.00')
        total_cost = Decimal('0.00')
        cashier_breakdown = {}

        for a in assignments:
            hours = a.calculate_hours_worked()
            cost = a.calculate_labor_cost()
            total_hours += hours
            total_cost += cost

            cid = a.cashier_id
            cname = a.cashier.get_full_name() or a.cashier.username
            if cid not in cashier_breakdown:
                cashier_breakdown[cid] = {
                    'cashier_id': cid,
                    'cashier_name': cname,
                    'shifts_count': 0,
                    'total_hours': Decimal('0.00'),
                    'total_cost': Decimal('0.00'),
                    'hourly_rate': a.hourly_rate,
                }
            cashier_breakdown[cid]['shifts_count'] += 1
            cashier_breakdown[cid]['total_hours'] += hours
            cashier_breakdown[cid]['total_cost'] += cost

        return {
            'branch': branch,
            'start_date': start_date,
            'end_date': end_date,
            'total_shifts': assignments.count(),
            'total_hours_worked': total_hours,
            'total_labor_cost': total_cost,
            'cashiers': list(cashier_breakdown.values()),
        }
