"""
Home Portal & Unified Gateway Views for Marid POS
Provides a modern landing hub featuring dual Backoffice and FrontOffice entry cards
with interactive Admin Password and Cashier PIN authentication workflows.
"""
import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages, auth
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.urls import reverse
from django.core.cache import cache
from django.views.decorators.http import require_POST, require_http_methods
from django_ratelimit.decorators import ratelimit

from .models import (
    Business, Branch, BranchMembership, BusinessMembership,
    UserProfile, POSTerminal, POSSession, PINLoginAuditLog, ActivityLog
)
from hr.models import Employee, Attendance
from hr.services import AttendanceService


def _get_client_ip(request):
    """Retrieve client IP address from request headers"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _get_user_agent(request):
    """Retrieve client user agent"""
    return request.META.get('HTTP_USER_AGENT', '')[:500]


def home_portal(request):
    """
    Unified Modern Home Screen with Multi-Module Workspace Gateway:
    1. Backoffice Portal (Central Controller & Master Administration)
    2. FrontOffice POS Terminal (Cashier Selling & Till Sessions)
    3. HR & Workforce Portal (Attendance, Time Clock, Leaves, Payroll)
    """
    # Resolve active business
    business = getattr(request, 'business', None)
    if not business:
        business = Business.objects.filter(is_active=True).first() or Business.objects.first()

    # Resolve active branch
    branch = getattr(request, 'branch', None)
    if not branch and business:
        branch = Branch.objects.filter(business=business, is_default=True, is_active=True).first() or \
                 Branch.objects.filter(business=business, is_active=True).first()

    # Resolve terminal from session, cookie or device token
    terminal = getattr(request, 'terminal', None)
    device_token = request.COOKIES.get('pos_terminal_token', '')
    if not terminal and device_token and business:
        terminal = POSTerminal.objects.filter(business=business, device_token=device_token, is_active=True).first()
    if not terminal and business and branch:
        terminal = POSTerminal.objects.filter(business=business, branch=branch, is_active=True).first()

    # Check active shift session
    active_session = None
    if business and request.user.is_authenticated:
        active_session = POSSession.objects.filter(
            business=business,
            status='open',
            cashier=request.user
        ).order_by('-opened_at').first()

    # Determine user role status if authenticated
    user_membership = None
    is_admin_or_manager = False
    is_cashier = False

    if request.user.is_authenticated:
        if request.user.is_superuser:
            is_admin_or_manager = True
        elif business:
            user_membership = BusinessMembership.objects.filter(
                user=request.user,
                business=business,
                is_active=True
            ).first()
            if user_membership:
                is_admin_or_manager = user_membership.role in ['owner', 'admin', 'manager']
                is_cashier = user_membership.role in ['cashier', 'sales']

    # Get active registered cashiers / staff for quick selection / tags
    cashiers = []
    if business:
        cashier_profiles = UserProfile.objects.filter(
            user__business_memberships__business=business,
            user__business_memberships__is_active=True,
            user__is_active=True
        ).exclude(pin_hash__isnull=True).exclude(pin_hash='').select_related('user').distinct()[:8]
        cashiers = [p.user for p in cashier_profiles]

    # HR & Workforce Context
    total_staff = 0
    present_today = 0
    my_employee = None
    my_attendance = None
    is_clocked_in = False
    today = timezone.localdate()

    if business:
        total_staff = Employee.objects.filter(business=business, status='active').count()
        present_today = Attendance.objects.filter(
            employee__business=business,
            date=today,
            status__in=('present', 'late')
        ).count()

    if request.user.is_authenticated and business:
        my_employee = Employee.objects.filter(user_account=request.user, business=business).first()
        if my_employee:
            my_attendance = Attendance.objects.filter(employee=my_employee, date=today).first()
            if my_attendance and not my_attendance.clock_out:
                is_clocked_in = True

    context = {
        'business': business,
        'branch': branch,
        'terminal': terminal,
        'active_session': active_session,
        'user_membership': user_membership,
        'is_admin_or_manager': is_admin_or_manager,
        'is_cashier': is_cashier,
        'cashiers': cashiers,
        'total_staff': total_staff,
        'present_today': present_today,
        'my_employee': my_employee,
        'my_attendance': my_attendance,
        'is_clocked_in': is_clocked_in,
        'current_year': timezone.now().year,
    }

    return render(request, 'pos/home_portal.html', context)


@ratelimit(key='ip', rate='10/m', method='POST', block=False)
def api_backoffice_login(request):
    """
    AJAX endpoint for Admin / Manager password authentication from the Home Screen.
    Authenticates user, logs activity, and returns JSON response with target redirect URL.
    """
    if getattr(request, 'limited', False):
        return JsonResponse({
            'success': False,
            'error': 'Too many login attempts. Please wait a minute and try again.'
        }, status=429)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required.'}, status=405)

    username_or_email = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')

    if not username_or_email or not password:
        return JsonResponse({
            'success': False,
            'error': 'Please provide both username/email and password.'
        }, status=400)

    # Try authentication directly with username
    user = authenticate(request, username=username_or_email, password=password)

    # If failed, attempt lookup by email (support multiple user records)
    if user is None:
        try:
            for candidate in User.objects.filter(email__iexact=username_or_email):
                user = authenticate(request, username=candidate.username, password=password)
                if user:
                    break
        except Exception:
            user = None

    if user is None:
        return JsonResponse({
            'success': False,
            'error': 'Invalid administrator username/email or password.'
        }, status=401)

    if not user.is_active:
        return JsonResponse({
            'success': False,
            'error': 'This account has been disabled. Please contact your system administrator.'
        }, status=403)

    # Log in user
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    # Resolve Business & Ensure Membership
    business = getattr(request, 'business', None)
    if not business:
        business = Business.objects.filter(is_active=True).first() or Business.objects.first()

    if business:
        membership = BusinessMembership.objects.filter(user=user, business=business).first()
        if not membership and user.is_superuser:
            BusinessMembership.objects.create(
                user=user,
                business=business,
                role='owner',
                is_active=True
            )

    # Log activity
    ActivityLog.log_activity(
        user=user,
        action_type='login',
        description=f'Admin logged in via Home Portal: {user.username}',
        request=request
    )

    next_url = request.POST.get('next') or request.GET.get('next') or reverse('dashboard')
    user_display = user.get_full_name() or user.username

    target_label = 'HR & Payroll' if '/hr/' in next_url else ('Accounting' if '/accounting/' in next_url else 'Backoffice')
    messages.success(request, f'Welcome to {target_label}, {user_display}!')

    return JsonResponse({
        'success': True,
        'redirect_url': next_url,
        'user_name': user_display,
        'message': f'Authenticated successfully. Redirecting to {target_label}...'
    })


@ratelimit(key='ip', rate='15/m', method='POST', block=False)
def api_cashier_pin_login(request):
    """
    AJAX endpoint for Cashier PIN authentication from the Home Screen.
    Validates PIN, checks lockout, binds terminal session, and returns JSON redirect response.
    """
    if getattr(request, 'limited', False):
        return JsonResponse({
            'success': False,
            'error': 'Too many PIN verification attempts. Please wait a minute before trying again.'
        }, status=429)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required.'}, status=405)

    pin = request.POST.get('pin', '').strip()
    employee_id = request.POST.get('employee_id', '').strip()
    device_token = request.POST.get('device_token', '').strip() or request.COOKIES.get('pos_terminal_token', '')

    if not pin:
        return JsonResponse({
            'success': False,
            'error': 'Please enter your unique 4–6 digit security PIN.'
        }, status=400)

    # Resolve business & branch
    business = getattr(request, 'business', None)
    if not business:
        business = Business.objects.filter(is_active=True).first() or Business.objects.first()

    branch = getattr(request, 'branch', None)
    if not branch and business:
        branch = Branch.objects.filter(business=business, is_default=True, is_active=True).first() or \
                 Branch.objects.filter(business=business, is_active=True).first()

    # Resolve or link terminal
    terminal = getattr(request, 'terminal', None)
    if not terminal and device_token and business:
        terminal = POSTerminal.objects.filter(business=business, device_token=device_token, is_active=True).first()
    if not terminal and business and branch:
        terminal = POSTerminal.objects.filter(business=business, branch=branch, is_active=True).first()

    ip_address = _get_client_ip(request)
    user_agent = _get_user_agent(request)

    profile = None
    # Mode 1: Cashier ID was explicitly provided
    if employee_id:
        profile = UserProfile.objects.select_related('user').filter(employee_id=employee_id).first()
        if not profile:
            user_by_name = User.objects.filter(username=employee_id).first()
            if user_by_name:
                profile = getattr(user_by_name, 'profile', None)
    else:
        # Mode 2: Direct Unique PIN lookup across store staff
        profile = UserProfile.find_by_pin(pin, business=business)

    if not profile:
        if business:
            PINLoginAuditLog.objects.create(
                business=business,
                branch=branch,
                employee_id=employee_id,
                terminal=terminal,
                terminal_code=terminal.terminal_code if terminal else '',
                status='failed_pin',
                failure_reason='Incorrect PIN or unknown cashier',
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return JsonResponse({
            'success': False,
            'error': 'Invalid security PIN. Please check your unique cashier PIN and try again.'
        }, status=401)

    user = profile.user
    if not user.is_active:
        return JsonResponse({
            'success': False,
            'error': 'This cashier account is inactive. Please contact your store manager.'
        }, status=403)

    lockout_key = f'pin_lockout_{user.id}'
    attempts_key = f'pin_attempts_{user.id}'

    # Check lockout
    lockout_until = cache.get(lockout_key)
    if lockout_until:
        remaining = max(1, int((lockout_until - timezone.now()).total_seconds() / 60))
        if business:
            PINLoginAuditLog.objects.create(
                business=business,
                branch=branch,
                user=user,
                employee_id=employee_id or profile.employee_id or user.username,
                terminal=terminal,
                terminal_code=terminal.terminal_code if terminal else '',
                status='locked_out',
                failure_reason=f'Account locked out for {remaining} more minute(s)',
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return JsonResponse({
            'success': False,
            'error': f'Account locked due to consecutive failed attempts. Try again in {remaining} minute(s).'
        }, status=423)

    # Check if PIN is configured
    if not profile.has_pin_set:
        if business:
            PINLoginAuditLog.objects.create(
                business=business,
                branch=branch,
                user=user,
                employee_id=employee_id or profile.employee_id or user.username,
                terminal=terminal,
                terminal_code=terminal.terminal_code if terminal else '',
                status='no_pin_set',
                failure_reason='PIN login not configured for user',
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return JsonResponse({
            'success': False,
            'error': 'PIN login is not configured for this user. Please contact your manager to set a POS PIN.'
        }, status=400)

    # Verify PIN hash if employee_id was used
    if not profile.check_pin(pin):
        attempts = cache.get(attempts_key, 0) + 1
        cache.set(attempts_key, attempts, timeout=900)

        if attempts >= 5:
            lockout_time = timezone.now() + timezone.timedelta(minutes=15)
            cache.set(lockout_key, lockout_time, timeout=900)
            cache.delete(attempts_key)
            failure_status = 'locked_out'
            failure_msg = 'PIN incorrect. Account locked for 15 minutes.'
        else:
            failure_status = 'failed_pin'
            remaining_attempts = 5 - attempts
            failure_msg = f'Invalid PIN. {remaining_attempts} attempt(s) remaining before temporary lockout.'

        if business:
            PINLoginAuditLog.objects.create(
                business=business,
                branch=branch,
                user=user,
                employee_id=employee_id or profile.employee_id or user.username,
                terminal=terminal,
                terminal_code=terminal.terminal_code if terminal else '',
                status=failure_status,
                failure_reason=f'Incorrect PIN entered (attempt #{attempts})',
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return JsonResponse({'success': False, 'error': failure_msg}, status=401)

    # Check terminal validation if assigned
    if terminal:
        can_login, reason = terminal.can_cashier_login(user)
        if not can_login:
            if business:
                PINLoginAuditLog.objects.create(
                    business=business,
                    branch=branch,
                    user=user,
                    employee_id=employee_id or profile.employee_id or user.username,
                    terminal=terminal,
                    terminal_code=terminal.terminal_code,
                    status='invalid_terminal',
                    failure_reason=f'Terminal validation failed: {reason}',
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            return JsonResponse({
                'success': False,
                'error': f'Terminal login rejected: {reason}'
            }, status=403)

    # Success: clear attempts and log in
    cache.delete(attempts_key)
    auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    # Ensure Business Membership exists
    if business:
        membership = BusinessMembership.objects.filter(user=user, business=business).first()
        if not membership:
            role = 'admin' if user.is_superuser else ('manager' if user.is_staff else 'cashier')
            membership = BusinessMembership.objects.create(
                user=user,
                business=business,
                role=role,
                is_active=True
            )
        elif not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=['is_active'])

    # Auto-create or bind terminal if needed
    if not terminal and business and branch:
        terminal = POSTerminal.objects.filter(business=business, branch=branch, is_active=True).first()
        if not terminal:
            terminal = POSTerminal.objects.create(
                business=business,
                branch=branch,
                name=f'{branch.name} - Register 1',
                terminal_code=f'TERM-{branch.code}-01',
                device_token=str(uuid.uuid4()),
                is_active=True,
            )

    if terminal:
        terminal.last_active_at = timezone.now()
        terminal.save(update_fields=['last_active_at'])
        request.session['active_terminal_id'] = terminal.pk

    request.session['is_front_office_session'] = True

    # Log successful login audit
    if business:
        PINLoginAuditLog.objects.create(
            business=business,
            branch=branch,
            user=user,
            employee_id=profile.employee_id or user.username,
            terminal=terminal,
            terminal_code=terminal.terminal_code if terminal else '',
            status='success',
            failure_reason='',
            ip_address=ip_address,
            user_agent=user_agent,
        )

    ActivityLog.log_activity(
        user=user,
        action_type='login',
        description=f'Cashier logged in via Home Portal PIN: {user.username}',
        request=request
    )

    # Check for existing open shift session
    from django.db.models import Q
    pos_session = None
    if business:
        pos_session = POSSession.objects.filter(
            business=business,
            status='open'
        ).filter(
            Q(cashier=user) | Q(opened_by=user)
        ).order_by('-opened_at').first()

    cashier_name = user.get_full_name() or user.username

    if pos_session:
        request.session['pos_session_id'] = pos_session.pk
        redirect_url = reverse('pos_screen')
        message = f'Welcome back, {cashier_name}! Active shift #{pos_session.session_number} resumed.'
        messages.success(request, message)
    else:
        redirect_url = reverse('terminal_session_open')
        message = f'Welcome, {cashier_name}! Please enter opening cash float to begin your shift.'
        messages.info(request, message)

    resp = JsonResponse({
        'success': True,
        'redirect_url': redirect_url,
        'cashier_name': cashier_name,
        'message': message,
    })

    if terminal and terminal.device_token:
        resp.set_cookie('pos_terminal_token', terminal.device_token, max_age=315360000)

    return resp


@ratelimit(key='ip', rate='20/m', method='POST', block=False)
def api_hr_pin_login(request):
    """
    AJAX endpoint for HR & Workforce Portal authentication and quick 1-tap Time Clock actions.
    Supports:
    - 'enter_hr': Authenticate and redirect to HR portal dashboard or attendance list.
    - 'clock_in': Instant attendance clock-in for the employee.
    - 'clock_out': Instant attendance clock-out for the employee.
    - 'status': Check employee's current day attendance status.
    """
    if getattr(request, 'limited', False):
        return JsonResponse({
            'success': False,
            'error': 'Too many HR authentication attempts. Please wait a moment.'
        }, status=429)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required.'}, status=405)

    pin = request.POST.get('pin', '').strip()
    employee_id = request.POST.get('employee_id', '').strip()
    action = request.POST.get('action', 'enter_hr').strip()

    # Resolve business & branch
    business = getattr(request, 'business', None)
    if not business:
        business = Business.objects.filter(is_active=True).first() or Business.objects.first()

    branch = getattr(request, 'branch', None)
    if not branch and business:
        branch = Branch.objects.filter(business=business, is_default=True, is_active=True).first() or \
                 Branch.objects.filter(business=business, is_active=True).first()

    # If user is already authenticated and no PIN provided, use active user
    user = None
    profile = None

    if not pin and request.user.is_authenticated:
        user = request.user
        profile = getattr(user, 'profile', None)
    else:
        if not pin:
            return JsonResponse({
                'success': False,
                'error': 'Please enter your staff PIN.'
            }, status=400)

        # Lookup Profile by Employee ID or Unique PIN
        if employee_id:
            profile = UserProfile.objects.select_related('user').filter(employee_id=employee_id).first()
            if not profile:
                user_by_name = User.objects.filter(username=employee_id).first()
                if user_by_name:
                    profile = getattr(user_by_name, 'profile', None)
        else:
            profile = UserProfile.find_by_pin(pin, business=business)

        if not profile:
            return JsonResponse({
                'success': False,
                'error': 'Invalid security PIN. Staff member not recognized.'
            }, status=401)

        user = profile.user
        if not user.is_active:
            return JsonResponse({
                'success': False,
                'error': 'This employee account is inactive.'
            }, status=403)

        lockout_key = f'pin_lockout_{user.id}'
        attempts_key = f'pin_attempts_{user.id}'

        # Check lockout
        lockout_until = cache.get(lockout_key)
        if lockout_until:
            remaining = max(1, int((lockout_until - timezone.now()).total_seconds() / 60))
            return JsonResponse({
                'success': False,
                'error': f'Account locked due to failed attempts. Try again in {remaining} minute(s).'
            }, status=423)

        # Check PIN
        if not profile.check_pin(pin):
            attempts = cache.get(attempts_key, 0) + 1
            cache.set(attempts_key, attempts, timeout=900)
            if attempts >= 5:
                cache.set(lockout_key, timezone.now() + timezone.timedelta(minutes=15), timeout=900)
                cache.delete(attempts_key)
                return JsonResponse({
                    'success': False,
                    'error': 'PIN incorrect. Account locked for 15 minutes.'
                }, status=423)
            return JsonResponse({
                'success': False,
                'error': f'Invalid staff PIN. {5 - attempts} attempt(s) remaining.'
            }, status=401)

        # Success - clear attempts and log in
        cache.delete(attempts_key)
        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')

    # Ensure Business Membership exists
    if business and user:
        membership = BusinessMembership.objects.filter(user=user, business=business).first()
        if not membership:
            role = 'admin' if user.is_superuser else ('manager' if user.is_staff else 'staff')
            membership = BusinessMembership.objects.create(
                user=user,
                business=business,
                role=role,
                is_active=True
            )

    # Ensure Employee record exists for HR actions
    employee = None
    if business and user:
        employee = Employee.objects.filter(user_account=user, business=business).first()
        if not employee:
            emp_branch = branch or Branch.objects.filter(business=business, is_active=True).first()
            if not emp_branch:
                emp_branch = Branch.objects.create(
                    business=business,
                    name='Main Branch',
                    code='MAIN',
                    is_default=True,
                    is_active=True
                )
            role_title = 'Staff'
            if user.is_superuser or (membership and membership.role in ['owner', 'admin']):
                role_title = 'Administrator'
            elif membership and membership.role == 'manager':
                role_title = 'Store Manager'
            elif membership and membership.role == 'cashier':
                role_title = 'Cashier'

            employee = Employee.objects.create(
                user_account=user,
                first_name=user.first_name or user.username,
                last_name=user.last_name or '',
                business=business,
                branch=emp_branch,
                job_title=role_title,
                status='active',
                hire_date=timezone.localdate(),
            )

    today = timezone.localdate()
    employee_display = employee.get_full_name() if employee else (user.get_full_name() or user.username)

    # Handle Actions
    if action == 'clock_in':
        if not employee:
            return JsonResponse({'success': False, 'error': 'No employee profile linked to account.'}, status=400)
        try:
            record = AttendanceService.clock_in(employee)
            clock_in_str = record.clock_in.strftime('%I:%M %p')
            msg = f'{employee_display} clocked in at {clock_in_str}. Status: {record.get_status_display()}.'
            messages.success(request, msg)
            return JsonResponse({
                'success': True,
                'action': 'clock_in',
                'employee_name': employee_display,
                'clock_in_time': clock_in_str,
                'status': record.status,
                'message': msg,
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    elif action == 'clock_out':
        if not employee:
            return JsonResponse({'success': False, 'error': 'No employee profile linked to account.'}, status=400)
        try:
            record = AttendanceService.clock_out(employee)
            clock_out_str = record.clock_out.strftime('%I:%M %p')
            msg = f'{employee_display} clocked out at {clock_out_str} ({record.total_hours} hrs today).'
            messages.success(request, msg)
            return JsonResponse({
                'success': True,
                'action': 'clock_out',
                'employee_name': employee_display,
                'clock_out_time': clock_out_str,
                'total_hours': str(record.total_hours),
                'message': msg,
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    elif action == 'status':
        if not employee:
            return JsonResponse({'success': False, 'error': 'No employee profile linked.'}, status=400)
        att = Attendance.objects.filter(employee=employee, date=today).first()
        is_in = bool(att and not att.clock_out)
        return JsonResponse({
            'success': True,
            'is_clocked_in': is_in,
            'clock_in_time': att.clock_in.strftime('%I:%M %p') if att and att.clock_in else None,
            'clock_out_time': att.clock_out.strftime('%I:%M %p') if att and att.clock_out else None,
            'total_hours': str(att.total_hours) if att else '0.00',
            'employee_name': employee_display,
        })

    # Default action: 'enter_hr'
    is_mgr = user.is_superuser or (membership and membership.role in ['owner', 'admin', 'manager'])
    if is_mgr:
        redirect_url = reverse('hr_dashboard')
        welcome_msg = f'Welcome to HR & Workforce Hub, {employee_display}!'
    else:
        redirect_url = reverse('hr_attendance_list')
        welcome_msg = f'Welcome to Employee Attendance & Portal, {employee_display}!'

    messages.success(request, welcome_msg)
    return JsonResponse({
        'success': True,
        'action': 'enter_hr',
        'redirect_url': redirect_url,
        'employee_name': employee_display,
        'message': welcome_msg,
    })

