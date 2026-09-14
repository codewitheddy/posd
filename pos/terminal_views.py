"""
Back Office Views — POS Terminal Device Management & PIN Login Audit Trails.
"""
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from datetime import datetime

from .models import Business, Branch, POSTerminal, PINLoginAuditLog, POSSession
from .decorators import business_required, back_office_required, back_office_module_required


@login_required
@business_required
@back_office_required
def terminal_list(request, slug=None):
    """
    Back Office list of all registered POS terminals in the store.
    """
    business = request.business
    branch = getattr(request, 'branch', None)
    
    qs = POSTerminal.objects.filter(business=business).select_related('branch').prefetch_related('allowed_cashiers')
    if branch and not request.user.is_superuser and not (hasattr(request, 'business_membership') and request.business_membership.role in ['owner', 'admin']):
        qs = qs.filter(branch=branch)

    terminals = qs.order_by('branch__name', 'terminal_code')

    return render(request, 'pos/terminals/terminal_list.html', {
        'business': business,
        'terminals': terminals,
        'branches': Branch.objects.filter(business=business, is_active=True),
    })


@login_required
@business_required
@back_office_module_required('system_admin')
def terminal_create(request, slug=None):
    """Create a new POS terminal definition in the store."""
    business = request.business
    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        terminal_code = request.POST.get('terminal_code', '').strip().upper()
        branch_id = request.POST.get('branch_id')
        import uuid
        device_token = request.POST.get('device_token', '').strip() or str(uuid.uuid4())

        if not name or not terminal_code or not branch_id:
            messages.error(request, 'Terminal name, code, and branch are required.')
            return redirect('terminal_create')

        branch = get_object_or_404(Branch, pk=branch_id, business=business)
        
        if POSTerminal.objects.filter(business=business, terminal_code=terminal_code).exists():
            messages.error(request, f'Terminal with code "{terminal_code}" already exists.')
            return redirect('terminal_create')

        terminal = POSTerminal.objects.create(
            business=business,
            branch=branch,
            name=name,
            terminal_code=terminal_code,
            device_token=device_token,
            is_active=True,
        )
        messages.success(request, f'Terminal "{terminal.name}" created successfully.')
        return redirect('terminal_list')

    return render(request, 'pos/terminals/terminal_form.html', {
        'business': business,
        'branches': branches,
    })


@login_required
@business_required
@back_office_module_required('system_admin')
def terminal_edit(request, pk=None, slug=None):
    """Edit terminal details, assigned branch, and status."""
    business = request.business
    terminal = get_object_or_404(POSTerminal, pk=pk, business=business)
    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')

    if request.method == 'POST':
        terminal.name = request.POST.get('name', '').strip()
        terminal.terminal_code = request.POST.get('terminal_code', '').strip().upper()
        branch_id = request.POST.get('branch_id')
        terminal.is_active = request.POST.get('is_active') == '1'

        if branch_id:
            terminal.branch = get_object_or_404(Branch, pk=branch_id, business=business)

        terminal.save()
        messages.success(request, f'Terminal "{terminal.name}" updated successfully.')
        return redirect('terminal_list')

    return render(request, 'pos/terminals/terminal_form.html', {
        'business': business,
        'terminal': terminal,
        'branches': branches,
    })


@login_required
@business_required
@back_office_required
def pin_audit_log_list(request, slug=None):
    """
    Back Office Audit Trail — View and filter all Cashier PIN login attempts,
    shift drawer opens, lockouts, and closures.
    """
    business = request.business
    branch = getattr(request, 'branch', None)
    
    qs = PINLoginAuditLog.objects.filter(business=business).select_related('branch', 'user', 'terminal')
    
    # Filter by branch
    branch_id = request.GET.get('branch')
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    elif branch and not request.user.is_superuser and not (hasattr(request, 'business_membership') and request.business_membership.role in ['owner', 'admin']):
        qs = qs.filter(branch=branch)

    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    # Filter by employee / cashier
    employee_query = request.GET.get('employee', '').strip()
    if employee_query:
        from django.db.models import Q
        qs = qs.filter(
            Q(employee_id__icontains=employee_query) |
            Q(user__username__icontains=employee_query) |
            Q(user__first_name__icontains=employee_query) |
            Q(user__last_name__icontains=employee_query)
        )

    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        try:
            start_dt = datetime.strptime(date_from, '%Y-%m-%d')
            qs = qs.filter(created_at__gte=start_dt)
        except ValueError:
            pass
    if date_to:
        try:
            end_dt = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            qs = qs.filter(created_at__lte=end_dt)
        except ValueError:
            pass

    # Export to CSV if requested
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="pin_audit_log_{timezone.now():%Y%m%d_%H%M}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Timestamp', 'Status', 'Employee ID / User', 'Terminal', 'Branch', 'IP Address', 'Notes / Reason'])
        for log in qs[:1000]:
            user_label = log.user.get_full_name() or log.user.username if log.user else log.employee_id
            writer.writerow([
                log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                log.get_status_display(),
                user_label,
                log.terminal.name if log.terminal else log.terminal_code,
                log.branch.name if log.branch else '',
                log.ip_address,
                log.failure_reason,
            ])
        return response

    logs = qs.order_by('-created_at')[:200]

    return render(request, 'pos/audit/pin_audit_list.html', {
        'business': business,
        'logs': logs,
        'branches': Branch.objects.filter(business=business, is_active=True),
        'status_choices': PINLoginAuditLog.STATUS_CHOICES,
        'selected_branch': branch_id,
        'selected_status': status_filter,
        'employee_query': employee_query,
        'date_from': date_from,
        'date_to': date_to,
    })
