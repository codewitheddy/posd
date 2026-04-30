"""
HR Module — Django web views (non-API, template-based).
All views are scoped to request.business via the existing pos middleware.
"""
import io

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count, Q
from decimal import Decimal
from datetime import date, timedelta

from pos.models import Business, BusinessMembership, Branch, ActivityLog, BusinessSettings
from pos.decorators import business_required
from .models import (
    Department, Employee, Attendance, Payroll,
    StaffAdvance, Leave, PerformanceRecord, DisciplinaryRecord
)
from .services import AttendanceService, PayrollService, PerformanceService


def _require_manager(request):
    """Return True if user is owner/admin/superuser."""
    if request.user.is_superuser:
        return True
    m = getattr(request, 'business_membership', None)
    return m and m.role in ('owner', 'admin')


def _log(request, action, description, model_name, obj_id):
    try:
        ActivityLog.log_activity(
            user=request.user,
            action_type=action,
            description=description,
            model_name=model_name,
            object_id=obj_id,
            request=request,
            business=request.business,
            operation_type=action,
            entity_type=model_name,
            entity_id=str(obj_id) if obj_id else '',
        )
    except Exception:
        pass


def _get_or_create_employee_for_attendance(request):
    """Return (employee, created_flag), auto-creating a minimal profile when safe."""
    business = request.business
    employee = Employee.objects.filter(user_account=request.user, business=business).first()
    if employee:
        return employee, False

    membership = getattr(request, 'business_membership', None)
    if not membership:
        raise Employee.DoesNotExist('No active business membership found for this user.')

    branch = Branch.objects.filter(business=business, is_active=True).order_by('-is_default', 'name', 'pk').first()
    if not branch:
        raise ValueError('No active branch found. Create an active branch before clocking attendance.')

    role_title_map = {
        'owner': 'Owner',
        'admin': 'Administrator',
        'manager': 'Manager',
        'stock_manager': 'Stock Manager',
        'cashier': 'Cashier',
        'sales': 'Sales Associate',
        'viewer': 'Viewer',
    }
    employee = Employee.objects.create(
        user_account=request.user,
        first_name=request.user.first_name,
        last_name=request.user.last_name,
        business=business,
        branch=branch,
        job_title=role_title_map.get(membership.role, membership.role.replace('_', ' ').title()),
        status='active',
        hire_date=timezone.localdate(),
    )
    return employee, True


def _format_exception_message(exc):
    """Return a clean user-facing message for common exception types."""
    if isinstance(exc, ValidationError):
        if getattr(exc, 'messages', None):
            return ' '.join(str(msg) for msg in exc.messages)
        if getattr(exc, 'message_dict', None):
            parts = []
            for field_messages in exc.message_dict.values():
                parts.extend(str(msg) for msg in field_messages)
            if parts:
                return ' '.join(parts)
    return str(exc)


def _attendance_redirect_response(request, slug):
    """Redirect to a safe next URL when provided, otherwise attendance list."""
    next_url = request.POST.get('next', '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('hr_attendance_list', slug=slug)


def _resolve_attendance_employee_for_action(request):
    """Resolve attendance target employee for clock actions.

    Managers can submit `employee_id` to clock in/out any active employee in the
    current business. Non-managers always act on their own profile (auto-created
    when missing).
    """
    business = request.business
    employee_id = request.POST.get('employee_id', '').strip()

    if _require_manager(request) and employee_id:
        employee = get_object_or_404(Employee, pk=employee_id, business=business, status='active')
        return employee, False

    return _get_or_create_employee_for_attendance(request)


# ─── Dashboard ────────────────────────────────────────────────────────────────

@login_required
@business_required
def hr_dashboard(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    business = request.business
    policy = AttendanceService.get_working_hours_policy(business)
    scheduled_hours = policy['scheduled_hours']

    selected_overtime_range = request.GET.get('overtime_range', 'month').strip().lower()
    overtime_range_error = ''
    overtime_start_date = month_start
    overtime_end_date = today
    if selected_overtime_range == '7d':
        overtime_start_date = today - timedelta(days=6)
    elif selected_overtime_range == '30d':
        overtime_start_date = today - timedelta(days=29)
    elif selected_overtime_range == 'custom':
        start_raw = request.GET.get('overtime_start', '').strip()
        end_raw = request.GET.get('overtime_end', '').strip()
        try:
            overtime_start_date = date.fromisoformat(start_raw)
            overtime_end_date = date.fromisoformat(end_raw)
            if overtime_start_date > overtime_end_date:
                raise ValueError('Overtime start date cannot be after end date.')
        except ValueError:
            selected_overtime_range = 'month'
            overtime_start_date = month_start
            overtime_end_date = today
            overtime_range_error = 'Invalid overtime date range. Showing this month instead.'
    else:
        selected_overtime_range = 'month'

    total_employees = Employee.objects.filter(business=business, status='active').count()
    present_today = Attendance.objects.filter(
        employee__business=business, date=today, status__in=('present', 'late')
    ).count()
    on_leave_today = Leave.objects.filter(
        employee__business=business, status='approved',
        start_date__lte=today, end_date__gte=today
    ).count()
    payroll_this_month = Payroll.objects.filter(
        employee__business=business, pay_date__gte=month_start, status='paid'
    ).aggregate(total=Sum('net_salary'))['total'] or Decimal('0.00')
    top_record = PerformanceRecord.objects.filter(
        employee__business=business, period_start__gte=month_start
    ).order_by('-performance_score').select_related('employee__user_account').first()
    pending_leave = Leave.objects.filter(employee__business=business, status='pending').count()
    recent_attendance = Attendance.objects.filter(
        employee__business=business, date=today
    ).select_related('employee__user_account').order_by('employee__user_account__first_name')[:10]

    overtime_by_employee = {}
    total_overtime_hours = Decimal('0.00')
    if scheduled_hours > 0:
        month_attendance = Attendance.objects.filter(
            employee__business=business,
            date__gte=overtime_start_date,
            date__lte=overtime_end_date,
            status__in=('present', 'late'),
        ).select_related('employee__user_account')

        for record in month_attendance:
            worked = record.total_hours or Decimal('0.00')
            overtime = max(Decimal('0.00'), worked - scheduled_hours)
            if overtime <= 0:
                continue

            total_overtime_hours += overtime
            emp = record.employee
            if emp.pk not in overtime_by_employee:
                overtime_by_employee[emp.pk] = {
                    'employee': emp,
                    'overtime_hours': Decimal('0.00'),
                    'overtime_days': 0,
                }
            overtime_by_employee[emp.pk]['overtime_hours'] += overtime
            overtime_by_employee[emp.pk]['overtime_days'] += 1

    top_overtime_staff = sorted(
        overtime_by_employee.values(),
        key=lambda row: (-row['overtime_hours'], row['employee'].get_full_name().lower()),
    )[:5]
    overtime_staff_count = len(overtime_by_employee)

    return render(request, 'hr/dashboard.html', {
        'total_employees': total_employees,
        'present_today': present_today,
        'on_leave_today': on_leave_today,
        'payroll_this_month': payroll_this_month,
        'top_record': top_record,
        'pending_leave': pending_leave,
        'recent_attendance': recent_attendance,
        'scheduled_hours': scheduled_hours,
        'total_overtime_hours': total_overtime_hours,
        'overtime_staff_count': overtime_staff_count,
        'top_overtime_staff': top_overtime_staff,
        'selected_overtime_range': selected_overtime_range,
        'overtime_start_date': overtime_start_date,
        'overtime_end_date': overtime_end_date,
        'overtime_range_error': overtime_range_error,
        'today': today,
    })


# ─── Employees ────────────────────────────────────────────────────────────────

@login_required
@business_required
def employee_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)
    business = request.business
    qs = Employee.objects.filter(business=business).select_related(
        'user_account', 'branch', 'department'
    ).order_by('user_account__first_name')
    status_filter = request.GET.get('status', '')
    dept_filter = request.GET.get('department', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if dept_filter:
        qs = qs.filter(department_id=dept_filter)
    departments = Department.objects.filter(business=business)
    return render(request, 'hr/employee_list.html', {
        'employees': qs,
        'departments': departments,
        'status_filter': status_filter,
        'dept_filter': dept_filter,
    })


@login_required
@business_required
def employee_create(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_employee_list', slug=request.business.slug)
    from django.contrib.auth.models import User
    business = request.business
    branches = Branch.objects.filter(business=business)
    departments = Department.objects.filter(business=business)
    users_without_employee = User.objects.filter(
        business_memberships__business=business
    ).exclude(employee_profile__business=business).distinct()

    if request.method == 'POST':
        try:
            user_id = request.POST.get('user_account')
            emp_type = request.POST.get('emp_type', 'pos')
            branch_id = request.POST.get('branch')
            dept_id = request.POST.get('department') or None

            user = None
            first_name = ''
            last_name = ''

            if emp_type == 'non_pos':
                first_name = request.POST.get('first_name', '').strip()
                last_name = request.POST.get('last_name', '').strip()
                if not first_name:
                    messages.error(request, 'First name is required for non-POS staff.')
                    return render(request, 'hr/employee_form.html', {
                        'branches': branches, 'departments': departments,
                        'users': users_without_employee, 'is_edit': False,
                    })
            else:
                if not user_id:
                    messages.error(request, 'Please select or create a user account.')
                    return render(request, 'hr/employee_form.html', {
                        'branches': branches, 'departments': departments,
                        'users': users_without_employee, 'is_edit': False,
                    })
                user = User.objects.get(pk=user_id)
                first_name = user.first_name
                last_name = user.last_name

            emp = Employee(
                user_account=user,
                first_name=first_name,
                last_name=last_name,
                business=business,
                branch=Branch.objects.get(pk=branch_id),
                department=Department.objects.get(pk=dept_id) if dept_id else None,
                job_title=request.POST.get('job_title', ''),
                id_number=request.POST.get('id_number', ''),
                kra_pin=request.POST.get('kra_pin', ''),
                nssf_number=request.POST.get('nssf_number', ''),
                nhif_number=request.POST.get('nhif_number', ''),
                address=request.POST.get('address', ''),
                basic_salary=Decimal(request.POST.get('basic_salary') or '0'),
                hourly_rate=Decimal('0') if Decimal(request.POST.get('basic_salary') or '0') > 0 else Decimal(request.POST.get('hourly_rate') or '0'),
                house_allowance=Decimal(request.POST.get('house_allowance') or '0'),
                transport_allowance=Decimal(request.POST.get('transport_allowance') or '0'),
                medical_allowance=Decimal(request.POST.get('medical_allowance') or '0'),
                other_allowance=Decimal(request.POST.get('other_allowance') or '0'),
                other_allowances={},  # Initialize as empty dict
                status=request.POST.get('status', 'active'),
                emergency_contact_name=request.POST.get('emergency_contact_name', ''),
                emergency_contact_phone=request.POST.get('emergency_contact_phone', ''),
                notes=request.POST.get('notes', ''),
                hire_date=request.POST.get('hire_date') or date.today(),
            )
            emp.full_clean()
            emp.save()
            
            # Parse other_allowances JSON
            import json
            other_allowances_str = request.POST.get('other_allowances', '{}').strip()
            if other_allowances_str:
                try:
                    emp.other_allowances = json.loads(other_allowances_str)
                    emp.save(update_fields=['other_allowances'])
                except json.JSONDecodeError:
                    messages.warning(request, 'Invalid JSON format for additional allowances. Using empty allowances.')
            
            _log(request, 'create', f'Created employee {emp}', 'Employee', emp.pk)
            messages.success(request, f'Employee {emp} created successfully.')
            return redirect('hr_employee_list', slug=slug)
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return render(request, 'hr/employee_form.html', {
        'branches': branches,
        'departments': departments,
        'users': users_without_employee,
        'is_edit': False,
    })


@login_required
@business_required
def employee_edit(request, slug=None, pk=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_employee_list', slug=request.business.slug)
    business = request.business
    emp = get_object_or_404(Employee, pk=pk, business=business)
    branches = Branch.objects.filter(business=business)
    departments = Department.objects.filter(business=business)

    if request.method == 'POST':
        try:
            branch_id = request.POST.get('branch')
            dept_id = request.POST.get('department') or None
            emp.branch = Branch.objects.get(pk=branch_id)
            emp.department = Department.objects.get(pk=dept_id) if dept_id else None
            emp.job_title = request.POST.get('job_title', emp.job_title)
            emp.id_number = request.POST.get('id_number', emp.id_number)
            emp.kra_pin = request.POST.get('kra_pin', emp.kra_pin)
            emp.nssf_number = request.POST.get('nssf_number', emp.nssf_number)
            emp.nhif_number = request.POST.get('nhif_number', emp.nhif_number)
            emp.address = request.POST.get('address', emp.address)
            emp.basic_salary = Decimal(request.POST.get('basic_salary') or emp.basic_salary)
            emp.hourly_rate = Decimal('0') if Decimal(request.POST.get('basic_salary') or str(emp.basic_salary)) > 0 else Decimal(request.POST.get('hourly_rate') or emp.hourly_rate)
            emp.house_allowance = Decimal(request.POST.get('house_allowance') or emp.house_allowance)
            emp.transport_allowance = Decimal(request.POST.get('transport_allowance') or emp.transport_allowance)
            emp.medical_allowance = Decimal(request.POST.get('medical_allowance') or emp.medical_allowance)
            emp.other_allowance = Decimal(request.POST.get('other_allowance') or emp.other_allowance)
            
            # Parse other_allowances JSON
            import json
            other_allowances_str = request.POST.get('other_allowances', '{}').strip()
            if other_allowances_str:
                try:
                    emp.other_allowances = json.loads(other_allowances_str)
                except json.JSONDecodeError:
                    messages.warning(request, 'Invalid JSON format for additional allowances. Keeping existing allowances.')
            
            emp.status = request.POST.get('status', emp.status)
            emp.emergency_contact_name = request.POST.get('emergency_contact_name', emp.emergency_contact_name)
            emp.emergency_contact_phone = request.POST.get('emergency_contact_phone', emp.emergency_contact_phone)
            emp.notes = request.POST.get('notes', emp.notes)
            hire = request.POST.get('hire_date')
            if hire:
                emp.hire_date = hire
            emp.full_clean()
            emp.save()
            _log(request, 'update', f'Updated employee {emp}', 'Employee', emp.pk)
            messages.success(request, 'Employee updated.')
            return redirect('hr_employee_list', slug=slug)
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return render(request, 'hr/employee_form.html', {
        'employee': emp,
        'branches': branches,
        'departments': departments,
        'is_edit': True,
    })


# ─── Attendance ───────────────────────────────────────────────────────────────

@login_required
@business_required
def attendance_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)
    business = request.business
    today = timezone.localdate()
    date_filter = request.GET.get('date', str(today))
    emp_filter = request.GET.get('employee', '')
    try:
        filter_date = date.fromisoformat(date_filter)
    except ValueError:
        filter_date = today

    qs = Attendance.objects.filter(
        employee__business=business, date=filter_date
    ).select_related('employee__user_account').order_by('employee__user_account__first_name')
    if emp_filter:
        qs = qs.filter(employee_id=emp_filter)

    policy = AttendanceService.get_working_hours_policy(business)
    scheduled_hours = policy['scheduled_hours']
    for row in qs:
        worked = row.total_hours or Decimal('0.00')
        row.overtime_hours = max(Decimal('0.00'), worked - scheduled_hours)

    employees = Employee.objects.filter(business=business, status='active').select_related('user_account')
    my_employee = Employee.objects.filter(user_account=request.user, business=business).first()
    return render(request, 'hr/attendance_list.html', {
        'attendance_records': qs,
        'employees': employees,
        'my_employee': my_employee,
        'can_manage_attendance': _require_manager(request),
        'workday_start_time': policy['shift_start'],
        'workday_end_time': policy['shift_end'],
        'late_grace_minutes': policy['late_grace_minutes'],
        'scheduled_hours': scheduled_hours,
        'filter_date': filter_date,
        'emp_filter': emp_filter,
    })


@login_required
@business_required
def attendance_clock_in(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)
    if request.method != 'POST':
        return redirect('hr_attendance_list', slug=slug)
    business = request.business
    try:
        employee, was_created = _resolve_attendance_employee_for_action(request)
        record = AttendanceService.clock_in(employee)
        _log(request, 'create', f'Clock in: {employee}', 'Attendance', record.pk)
        if was_created:
            messages.info(request, f'HR employee profile auto-created for {employee.get_full_name()} during clock in.')
        messages.success(request, f'Clocked in at {record.clock_in}')
    except Employee.DoesNotExist:
        messages.error(request, 'No employee profile found for your account.')
    except Exception as e:
        messages.error(request, _format_exception_message(e))
    return _attendance_redirect_response(request, slug)


@login_required
@business_required
def attendance_clock_out(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)
    if request.method != 'POST':
        return redirect('hr_attendance_list', slug=slug)
    business = request.business
    try:
        employee, was_created = _resolve_attendance_employee_for_action(request)
        record = AttendanceService.clock_out(employee)
        _log(request, 'update', f'Clock out: {employee}', 'Attendance', record.pk)
        if was_created:
            messages.info(request, f'HR employee profile auto-created for {employee.get_full_name()} during clock out.')
        messages.success(request, f'Clocked out at {record.clock_out} — {record.total_hours}h')
    except Employee.DoesNotExist:
        messages.error(request, 'No employee profile found for your account.')
    except Exception as e:
        messages.error(request, _format_exception_message(e))
    return _attendance_redirect_response(request, slug)


# ─── Leave ────────────────────────────────────────────────────────────────────

@login_required
@business_required
def leave_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)
    business = request.business
    qs = Leave.objects.filter(employee__business=business).select_related(
        'employee__user_account', 'approved_by__user_account'
    ).order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'hr/leave_list.html', {'leave_requests': qs, 'status_filter': status_filter})


@login_required
@business_required
def leave_create(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)
    business = request.business
    if request.method == 'POST':
        try:
            employee = Employee.objects.get(user_account=request.user, business=business)
            start = date.fromisoformat(request.POST['start_date'])
            end = date.fromisoformat(request.POST['end_date'])
            if end < start:
                messages.error(request, 'End date must be on or after start date.')
            else:
                leave = Leave.objects.create(
                    employee=employee,
                    leave_type=request.POST.get('leave_type', 'annual'),
                    start_date=start,
                    end_date=end,
                    days_count=(end - start).days + 1,
                    reason=request.POST.get('reason', ''),
                    status='pending',
                )
                _log(request, 'create', f'Leave request by {employee}', 'Leave', leave.pk)
                messages.success(request, 'Leave request submitted.')
                return redirect('hr_leave_list', slug=slug)
        except Employee.DoesNotExist:
            messages.error(request, 'No employee profile found.')
        except Exception as e:
            messages.error(request, str(e))
    return render(request, 'hr/leave_form.html', {})


@login_required
@business_required
def leave_approve(request, slug=None, pk=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_leave_list', slug=slug)
    leave = get_object_or_404(Leave, pk=pk, employee__business=request.business)
    if leave.status != 'pending':
        messages.error(request, 'Leave request is already finalised.')
        return redirect('hr_leave_list', slug=slug)
    try:
        approver = Employee.objects.get(user_account=request.user, business=request.business)
    except Employee.DoesNotExist:
        approver = None
    leave.status = 'approved'
    leave.approved_by = approver
    leave.save(update_fields=['status', 'approved_by'])
    Attendance.objects.filter(
        employee=leave.employee, date__gte=leave.start_date, date__lte=leave.end_date
    ).update(status='off')
    _log(request, 'update', f'Approved leave for {leave.employee}', 'Leave', leave.pk)
    messages.success(request, 'Leave approved.')
    return redirect('hr_leave_list', slug=slug)


@login_required
@business_required
def leave_reject(request, slug=None, pk=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_leave_list', slug=slug)
    leave = get_object_or_404(Leave, pk=pk, employee__business=request.business)
    if leave.status != 'pending':
        messages.error(request, 'Leave request is already finalised.')
        return redirect('hr_leave_list', slug=slug)
    leave.status = 'rejected'
    leave.save(update_fields=['status'])
    _log(request, 'update', f'Rejected leave for {leave.employee}', 'Leave', leave.pk)
    messages.success(request, 'Leave rejected.')
    return redirect('hr_leave_list', slug=slug)


# ─── Payroll ──────────────────────────────────────────────────────────────────

@login_required
@business_required
def payroll_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)
    business = request.business
    qs = Payroll.objects.filter(employee__business=business).select_related(
        'employee__user_account'
    ).order_by('-period_end')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
    return render(request, 'hr/payroll_list.html', {'payrolls': qs, 'status_filter': status_filter})


@login_required
@business_required
def payroll_calculate(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_payroll_list', slug=slug)
    if request.method == 'POST':
        try:
            ps = date.fromisoformat(request.POST['period_start'])
            pe = date.fromisoformat(request.POST['period_end'])
            payrolls = PayrollService.calculate_period(request.business, ps, pe)
            _log(request, 'create', f'Calculated payroll {ps} to {pe}', 'Payroll', None)
            messages.success(request, f'Payroll calculated for {len(payrolls)} employee(s).')
        except Exception as e:
            messages.error(request, str(e))
    return redirect('hr_payroll_list', slug=slug)


@login_required
@business_required
def payroll_mark_paid(request, slug=None, pk=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_payroll_list', slug=slug)
    payroll = get_object_or_404(Payroll, pk=pk, employee__business=request.business)
    try:
        PayrollService.mark_paid(payroll)
        _log(request, 'update', f'Marked payroll paid for {payroll.employee}', 'Payroll', payroll.pk)
        messages.success(request, 'Payroll marked as paid.')
    except Exception as e:
        messages.error(request, str(e))
    return redirect('hr_payroll_list', slug=slug)


# ─── Advances ─────────────────────────────────────────────────────────────────

@login_required
@business_required
def advance_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)
    qs = StaffAdvance.objects.filter(
        employee__business=request.business
    ).select_related('employee__user_account').order_by('-date_taken')
    return render(request, 'hr/advance_list.html', {'advances': qs})


@login_required
@business_required
def advance_create(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_advance_list', slug=slug)
    business = request.business
    employees = Employee.objects.filter(business=business, status='active').select_related('user_account')
    if request.method == 'POST':
        try:
            emp = Employee.objects.get(pk=request.POST['employee'], business=business)
            if StaffAdvance.objects.filter(employee=emp, status='active').exists():
                messages.error(request, 'Employee already has an active advance.')
            else:
                amount = Decimal(request.POST['amount'])
                adv = StaffAdvance.objects.create(
                    employee=emp,
                    amount=amount,
                    reason=request.POST.get('reason', ''),
                    date_taken=date.fromisoformat(request.POST['date_taken']),
                    deduction_per_month=Decimal(request.POST['deduction_per_month']),
                    balance_remaining=amount,
                    status='active',
                )
                _log(request, 'create', f'Advance for {emp}', 'StaffAdvance', adv.pk)
                messages.success(request, 'Advance recorded.')
                return redirect('hr_advance_list', slug=slug)
        except Exception as e:
            messages.error(request, str(e))
    return render(request, 'hr/advance_form.html', {'employees': employees})


# ─── Performance ──────────────────────────────────────────────────────────────

@login_required
@business_required
def performance_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)
    business = request.business
    qs = PerformanceRecord.objects.filter(
        employee__business=business
    ).select_related('employee__user_account').order_by('-performance_score', '-period_end')
    if request.method == 'POST':
        try:
            ps = date.fromisoformat(request.POST['period_start'])
            pe = date.fromisoformat(request.POST['period_end'])
            records = PerformanceService.generate_period(business, ps, pe)
            _log(request, 'create', f'Generated performance {ps} to {pe}', 'PerformanceRecord', None)
            messages.success(request, f'Performance generated for {len(records)} employee(s).')
        except Exception as e:
            messages.error(request, str(e))
        return redirect('hr_performance_list', slug=slug)
    return render(request, 'hr/performance_list.html', {'records': qs})


# ─── Disciplinary ─────────────────────────────────────────────────────────────

@login_required
@business_required
def disciplinary_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)
    qs = DisciplinaryRecord.objects.filter(
        employee__business=request.business
    ).select_related('employee__user_account', 'issued_by__user_account').order_by('-incident_date')
    return render(request, 'hr/disciplinary_list.html', {'records': qs})


@login_required
@business_required
def disciplinary_create(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_disciplinary_list', slug=slug)
    business = request.business
    employees = Employee.objects.filter(business=business, status='active').select_related('user_account')
    if request.method == 'POST':
        try:
            emp = Employee.objects.get(pk=request.POST['employee'], business=business)
            issuer = Employee.objects.get(user_account=request.user, business=business)
            rec = DisciplinaryRecord.objects.create(
                employee=emp,
                incident_date=date.fromisoformat(request.POST['incident_date']),
                incident_type=request.POST.get('incident_type', 'warning'),
                description=request.POST.get('description', ''),
                action_taken=request.POST.get('action_taken', ''),
                issued_by=issuer,
            )
            _log(request, 'create', f'Disciplinary for {emp}', 'DisciplinaryRecord', rec.pk)
            messages.success(request, 'Disciplinary record created.')
            return redirect('hr_disciplinary_list', slug=slug)
        except Exception as e:
            messages.error(request, str(e))
    return render(request, 'hr/disciplinary_form.html', {'employees': employees})


# ─── P9 Form (Kenya Tax) ──────────────────────────────────────────────────────

def _calculate_paye(annual_taxable, annual_shif=Decimal('0.00')):
    """
    Calculate annual PAYE — Kenya 2026.
    Taxable = Gross - NSSF (employee portion).
    Bands: 0-288,000 @ 10%, 288,001-388,000 @ 25%, 388,001-6,000,000 @ 30%,
           6,000,001-9,600,000 @ 32.5%, above 9,600,000 @ 35%.
    Reliefs: Personal KES 28,800/year; Insurance relief 15% of annual SHIF.
    """
    g = Decimal(str(annual_taxable))
    tax = Decimal('0')
    bands = [
        (Decimal('288000'), Decimal('0.10')),
        (Decimal('100000'), Decimal('0.25')),   # 288,001 – 388,000
        (Decimal('5612000'), Decimal('0.30')),  # 388,001 – 6,000,000
        (Decimal('3600000'), Decimal('0.325')), # 6,000,001 – 9,600,000
    ]
    remaining = g
    for band_size, rate in bands:
        if remaining <= 0:
            break
        taxable = min(remaining, band_size)
        tax += taxable * rate
        remaining -= taxable
    if remaining > 0:
        tax += remaining * Decimal('0.35')
    personal_relief = Decimal('28800')
    insurance_relief = Decimal(str(annual_shif)) * Decimal('0.15')
    tax = max(Decimal('0'), tax - personal_relief - insurance_relief)
    return tax


def _calculate_shif(gross_monthly):
    """SHIF — 2026: flat 2.75% of gross salary, no cap."""
    return round(Decimal(str(gross_monthly)) * Decimal('0.0275'), 2)


def _calculate_housing_levy(gross_monthly):
    """Affordable Housing Levy (employee) — 2026: 1.5% of gross salary."""
    return round(Decimal(str(gross_monthly)) * Decimal('0.015'), 2)


def _calculate_nssf(gross_monthly):
    """
    NSSF Tier I + Tier II — February 2026 limits.
    Tier I : 6% of first KES 9,000   (max KES 540).
    Tier II: 6% of KES 9,001–108,000 (max KES 5,940).
    Total max: KES 6,480.
    """
    g = Decimal(str(gross_monthly))
    tier1 = min(g, Decimal('9000')) * Decimal('0.06')
    tier2 = max(Decimal('0'), min(g, Decimal('108000')) - Decimal('9000')) * Decimal('0.06')
    return tier1 + tier2


@login_required
@business_required
def p9_list(request, slug=None):
    """List employees for P9 generation."""
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)
    business = request.business
    tax_year = int(request.GET.get('year', date.today().year))
    employees = Employee.objects.filter(business=business, status__in=('active', 'terminated')).select_related('user_account')
    return render(request, 'hr/p9_list.html', {
        'employees': employees,
        'tax_year': tax_year,
        'years': range(date.today().year, date.today().year - 5, -1),
    })


@login_required
@business_required
def p9_download(request, slug=None, employee_pk=None):
    """Generate and download P9 PDF for an employee."""
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    business = request.business
    employee = get_object_or_404(Employee, pk=employee_pk, business=business)
    tax_year = int(request.GET.get('year', date.today().year))

    # Fetch payroll records for the tax year
    payrolls = Payroll.objects.filter(
        employee=employee,
        period_start__year=tax_year,
        status='paid',
    ).order_by('period_start')

    # Build monthly data
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    monthly_data = {}
    for p in payrolls:
        m = p.period_start.month
        gross = p.basic_salary + p.overtime_amount + p.bonus + p.commission
        nssf = _calculate_nssf(gross)
        shif = _calculate_shif(gross)
        housing_levy = _calculate_housing_levy(gross)
        # PAYE taxable = gross - NSSF; insurance relief = 15% of annual SHIF
        annual_paye = _calculate_paye((gross - nssf) * 12, annual_shif=shif * 12)
        monthly_paye = round(annual_paye / 12, 2)
        monthly_data[m] = {
            'basic': p.basic_salary,
            'benefits': p.bonus + p.commission,
            'gross': gross,
            'shif': shif,
            'housing_levy': housing_levy,
            'nssf': nssf,
            'paye': monthly_paye,
            'net': gross - shif - housing_levy - nssf - monthly_paye,
        }

    # Totals
    total_gross = sum(v['gross'] for v in monthly_data.values())
    total_paye = sum(v['paye'] for v in monthly_data.values())
    total_shif = sum(v['shif'] for v in monthly_data.values())
    total_housing_levy = sum(v['housing_levy'] for v in monthly_data.values())
    total_nssf = sum(v['nssf'] for v in monthly_data.values())

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=14)
    sub_style = ParagraphStyle('sub', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10)
    normal = styles['Normal']

    story = []
    story.append(Paragraph('P9 FORM', title_style))
    story.append(Paragraph(f'Tax Deduction Card — Year of Income {tax_year}', sub_style))
    story.append(Spacer(1, 0.4*cm))

    # Employer / Employee info table
    settings_obj = getattr(business, 'settings', None)
    employer_pin = business.kra_pin or '—'
    employer_name = (settings_obj.get_business_name() if settings_obj else business.name)
    if employee.user_account:
        employee_name = employee.user_account.get_full_name() or employee.user_account.username
    else:
        employee_name = f"{employee.first_name} {employee.last_name}".strip()
    employee_pin = employee.kra_pin or '—'

    info_data = [
        ['Employer Name:', employer_name, 'Employer KRA PIN:', employer_pin],
        ['Employee Name:', employee_name, 'Employee KRA PIN:', employee_pin],
        ['Job Title:', employee.job_title, 'Tax Year:', str(tax_year)],
    ]
    info_table = Table(info_data, colWidths=[3.5*cm, 7*cm, 3.5*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5*cm))

    # Monthly breakdown table
    header = ['Month', 'Basic Pay', 'Benefits', 'Gross Pay', 'NSSF', 'SHIF', 'Hsg Levy', 'PAYE', 'Net Pay']
    table_data = [header]
    for i, month in enumerate(months, 1):
        d = monthly_data.get(i, {})
        if d:
            table_data.append([
                month,
                f"{d['basic']:,.2f}",
                f"{d['benefits']:,.2f}",
                f"{d['gross']:,.2f}",
                f"{d['nssf']:,.2f}",
                f"{d['shif']:,.2f}",
                f"{d['housing_levy']:,.2f}",
                f"{d['paye']:,.2f}",
                f"{d['net']:,.2f}",
            ])
        else:
            table_data.append([month, '—', '—', '—', '—', '—', '—', '—', '—'])

    # Totals row
    table_data.append([
        'TOTAL',
        '', '',
        f"{total_gross:,.2f}",
        f"{total_nssf:,.2f}",
        f"{total_shif:,.2f}",
        f"{total_housing_levy:,.2f}",
        f"{total_paye:,.2f}",
        '',
    ])

    col_widths = [1.5*cm, 2.4*cm, 2.2*cm, 2.4*cm, 1.9*cm, 1.9*cm, 1.9*cm, 2.2*cm, 2.4*cm]
    breakdown_table = Table(table_data, colWidths=col_widths)
    breakdown_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#224195')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fa')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e9ecef')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(breakdown_table)
    story.append(Spacer(1, 0.5*cm))

    # Summary
    summary_data = [
        ['Annual Gross Pay:', f"KES {total_gross:,.2f}"],
        ['Total NSSF Deducted:', f"KES {total_nssf:,.2f}"],
        ['Total SHIF Deducted:', f"KES {total_shif:,.2f}"],
        ['Total Housing Levy:', f"KES {total_housing_levy:,.2f}"],
        ['Total PAYE Deducted:', f"KES {total_paye:,.2f}"],
    ]
    summary_table = Table(summary_data, colWidths=[6*cm, 5*cm])
    summary_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        'This P9 form is generated from payroll records. PAYE is calculated using 2026 Kenya tax regulations. '
        'Includes SHIF (2.75% of gross), NSSF (Feb 2026 limits), and Affordable Housing Levy (1.5%). '
        'Please verify with a certified tax consultant before filing.',
        ParagraphStyle('disclaimer', parent=normal, fontSize=7, textColor=colors.grey)
    ))

    doc.build(story)
    buffer.seek(0)
    filename = f"P9_{employee_name.replace(' ', '_')}_{tax_year}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@business_required
def payslip_download(request, slug=None, payroll_pk=None):
    """Generate and download payslip PDF for a payroll record."""
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)

    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    business = request.business
    payroll = get_object_or_404(Payroll, pk=payroll_pk, employee__business=business)
    employee = payroll.employee

    # Keep pending payroll slips in sync with current calculation rules.
    if payroll.status == 'pending':
        PayrollService.calculate_period(business, payroll.period_start, payroll.period_end)
        payroll.refresh_from_db()
        employee = payroll.employee

    # Build PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('title', parent=styles['Heading1'], alignment=TA_CENTER, fontSize=16)
    sub_style = ParagraphStyle('sub', parent=styles['Normal'], alignment=TA_CENTER, fontSize=10)
    normal = styles['Normal']
    right_align = ParagraphStyle('right', parent=normal, alignment=TA_RIGHT)

    story = []
    story.append(Paragraph('PAYSLIP', title_style))
    story.append(Paragraph(f'Pay Period: {payroll.period_start} to {payroll.period_end}', sub_style))
    story.append(Spacer(1, 0.4*cm))

    # Employee info
    settings_obj = getattr(business, 'settings', None)
    employer_name = (settings_obj.get_business_name() if settings_obj else business.name)
    employee_name = employee.get_full_name()

    info_data = [
        ['Employer:', employer_name, 'Employee:', employee_name],
        ['Job Title:', employee.job_title, 'ID Number:', employee.id_number or '—'],
        ['Department:', employee.department.name if employee.department else '—', 'Branch:', employee.branch.name],
    ]
    info_table = Table(info_data, colWidths=[3*cm, 6*cm, 3*cm, 4*cm])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5*cm))

    # Earnings
    earnings_data = [
        ['Earnings', 'Amount'],
        ['Basic Salary', f"KES {payroll.basic_salary:,.2f}"],
        ['House Allowance', f"KES {payroll.house_allowance:,.2f}"],
        ['Transport Allowance', f"KES {payroll.transport_allowance:,.2f}"],
        ['Medical Allowance', f"KES {payroll.medical_allowance:,.2f}"],
        ['Other Allowance', f"KES {payroll.other_allowance:,.2f}"],
        ['Overtime', f"KES {payroll.overtime_amount:,.2f}"],
        ['Bonus', f"KES {payroll.bonus:,.2f}"],
        ['Commission', f"KES {payroll.commission:,.2f}"],
        ['Gross Salary', f"KES {payroll.gross_salary:,.2f}"],
    ]
    earnings_table = Table(earnings_data, colWidths=[8*cm, 4*cm])
    earnings_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
    ]))
    story.append(Paragraph('Earnings', styles['Heading3']))
    story.append(earnings_table)
    story.append(Spacer(1, 0.3*cm))

    # Deductions
    deductions_data = [
        ['Deductions', 'Amount'],
        ['PAYE', f"KES {payroll.paye:,.2f}"],
        ['SHIF (2.75%)', f"KES {payroll.shif:,.2f}"],
        ['NSSF', f"KES {payroll.nssf:,.2f}"],
        ['Housing Levy (1.5%)', f"KES {payroll.housing_levy:,.2f}"],
        ['Absence Deduction', f"KES {payroll.absence_deduction:,.2f}"],
        ['Other Deductions', f"KES {payroll.other_deductions:,.2f}"],
        ['Salary Advance', f"KES {payroll.advances_deducted:,.2f}"],
        ['Total Deductions', f"KES {payroll.total_deductions:,.2f}"],
    ]
    deductions_table = Table(deductions_data, colWidths=[8*cm, 4*cm])
    deductions_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
    ]))
    story.append(Paragraph('Deductions', styles['Heading3']))
    story.append(deductions_table)
    story.append(Spacer(1, 0.3*cm))

    # Net Salary
    net_data = [
        ['Net Salary', f"KES {payroll.net_salary:,.2f}"],
    ]
    net_table = Table(net_data, colWidths=[8*cm, 4*cm])
    net_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.lightgrey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph(
        'Note: For partial periods, monthly basic salary and fixed allowances are prorated based on working days in the selected pay period (26-working-day monthly base).',
        ParagraphStyle('proration_note', parent=normal, fontSize=8, textColor=colors.grey)
    ))
    story.append(Spacer(1, 0.2*cm))

    story.append(Paragraph(
        f'Payment Date: {payroll.pay_date or "Pending"} | Status: {payroll.get_status_display()}',
        ParagraphStyle('footer', parent=normal, fontSize=8, alignment=TA_CENTER)
    ))

    doc.build(story)
    buffer.seek(0)
    filename = f"Payslip_{employee_name.replace(' ', '_')}_{payroll.period_start}_{payroll.period_end}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─── Departments ──────────────────────────────────────────────────────────────

@login_required
@business_required
def department_list(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_dashboard', slug=slug)
    depts = Department.objects.filter(business=request.business).select_related('manager__user_account')
    return render(request, 'hr/department_list.html', {'departments': depts})


@login_required
@business_required
def department_create(request, slug=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_department_list', slug=slug)
    business = request.business
    employees = Employee.objects.filter(business=business, status='active').select_related('user_account')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        manager_id = request.POST.get('manager') or None
        if not name:
            messages.error(request, 'Department name is required.')
        elif Department.objects.filter(business=business, name=name).exists():
            messages.error(request, f'Department "{name}" already exists.')
        else:
            dept = Department.objects.create(
                business=business,
                name=name,
                description=description,
                manager=Employee.objects.get(pk=manager_id) if manager_id else None,
            )
            _log(request, 'create', f'Created department {dept.name}', 'Department', dept.pk)
            messages.success(request, f'Department "{dept.name}" created.')
            return redirect('hr_department_list', slug=slug)
    return render(request, 'hr/department_form.html', {'employees': employees, 'is_edit': False})


@login_required
@business_required
def department_edit(request, slug=None, pk=None):
    if not _require_manager(request):
        messages.error(request, 'Permission denied.')
        return redirect('hr_department_list', slug=slug)
    business = request.business
    dept = get_object_or_404(Department, pk=pk, business=business)
    employees = Employee.objects.filter(business=business, status='active').select_related('user_account')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        manager_id = request.POST.get('manager') or None
        if not name:
            messages.error(request, 'Department name is required.')
        elif Department.objects.filter(business=business, name=name).exclude(pk=pk).exists():
            messages.error(request, f'Department "{name}" already exists.')
        else:
            dept.name = name
            dept.description = description
            dept.manager = Employee.objects.get(pk=manager_id) if manager_id else None
            dept.save()
            _log(request, 'update', f'Updated department {dept.name}', 'Department', dept.pk)
            messages.success(request, 'Department updated.')
            return redirect('hr_department_list', slug=slug)
    return render(request, 'hr/department_form.html', {
        'department': dept, 'employees': employees, 'is_edit': True
    })


from django.http import JsonResponse as _JsonResponse
from django.views.decorators.http import require_POST as _require_POST


@login_required
@business_required
@_require_POST
def department_quick_create(request, slug=None):
    """AJAX endpoint to create a department inline from the employee form."""
    if not _require_manager(request):
        return _JsonResponse({'error': 'Permission denied.'}, status=403)
    name = request.POST.get('name', '').strip()
    if not name:
        return _JsonResponse({'error': 'Name is required.'}, status=400)
    if Department.objects.filter(business=request.business, name=name).exists():
        return _JsonResponse({'error': f'Department "{name}" already exists.'}, status=400)
    dept = Department.objects.create(business=request.business, name=name)
    return _JsonResponse({'id': dept.pk, 'name': dept.name})


@login_required
@business_required
@_require_POST
def user_quick_create(request, slug=None):
    """AJAX endpoint to create a User + BusinessMembership inline from the employee form."""
    if not _require_manager(request):
        return _JsonResponse({'error': 'Permission denied.'}, status=403)
    from django.contrib.auth.models import User
    from pos.models import BusinessMembership
    username = request.POST.get('username', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    password = request.POST.get('password', '').strip()
    role = request.POST.get('role', 'cashier')
    if not username or not password:
        return _JsonResponse({'error': 'Username and password are required.'}, status=400)
    if len(password) < 8:
        return _JsonResponse({'error': 'Password must be at least 8 characters.'}, status=400)
    if User.objects.filter(username=username).exists():
        return _JsonResponse({'error': f'Username "{username}" is already taken.'}, status=400)
    user = User.objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password=password,
    )
    BusinessMembership.objects.create(
        user=user,
        business=request.business,
        role=role,
        is_active=True,
    )
    full_name = user.get_full_name() or username
    return _JsonResponse({'id': user.pk, 'name': f'{full_name} ({username})'})
