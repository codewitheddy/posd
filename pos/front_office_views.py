"""
Front Office Views — POS Terminal, Cashier PIN Sessions, and Shift Z-Reports.
Provides terminal-bound PIN authentication, shift lifecycle, and cashier-scoped operations.
"""
import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages, auth
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.cache import cache

from .models import (
    Business, Branch, BranchMembership, BusinessMembership,
    UserProfile, POSTerminal, POSSession, PINLoginAuditLog, ZReport
)
from .decorators import business_required, front_office_required
from .zreport_service import ZReportService


def _get_client_ip(request):
    """Retrieve client IP address from headers"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _get_user_agent(request):
    """Retrieve client user agent"""
    return request.META.get('HTTP_USER_AGENT', '')[:500]


def terminal_pin_login(request):
    """
    Front Office PIN Login Page.
    Touch-friendly numeric PIN pad for Cashiers and POS operators.
    Binds session to the physical terminal and logs all audit events.
    """
    business = getattr(request, 'business', None)
    if not business:
        from .models import Business
        business = Business.objects.filter(is_active=True).first() or Business.objects.first()

    terminal = getattr(request, 'terminal', None)
    branch = getattr(request, 'branch', None)
    if not branch and terminal:
        branch = terminal.branch
    if not branch and business:
        branch = Branch.objects.filter(business=business, is_default=True, is_active=True).first() or Branch.objects.filter(business=business, is_active=True).first()

    if request.method == 'POST':
        employee_id = request.POST.get('employee_id', '').strip()
        pin = request.POST.get('pin', '').strip()
        device_token = request.POST.get('device_token', '').strip() or request.COOKIES.get('pos_terminal_token', '')

        # Resolve terminal
        if not terminal and device_token and business:
            terminal = POSTerminal.objects.filter(business=business, device_token=device_token, is_active=True).first()

        ip_address = _get_client_ip(request)
        user_agent = _get_user_agent(request)

        if not pin:
            messages.error(request, 'Please enter your unique 4–6 digit security PIN.')
            return render(request, 'pos/front_office/pin_lock.html', {
                'business': business,
                'branch': branch,
                'terminal': terminal,
                'employee_id': employee_id,
            })

        profile = None
        # Mode 1: Employee ID / Username was explicitly provided
        if employee_id:
            profile = UserProfile.objects.select_related('user').filter(employee_id=employee_id).first()
            if not profile:
                user_by_name = User.objects.filter(username=employee_id).first()
                if user_by_name:
                    profile = getattr(user_by_name, 'profile', None)
        else:
            # Mode 2: Direct Unique PIN entry — look up cashier by their unique PIN
            profile = UserProfile.find_by_pin(pin, business=business)

        if not profile:
            # Audit log failed PIN entry
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
            messages.error(request, 'Invalid PIN. Please check your unique cashier PIN and try again.')
            return render(request, 'pos/front_office/pin_lock.html', {
                'business': business,
                'branch': branch,
                'terminal': terminal,
                'employee_id': employee_id,
            })

        user = profile.user
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
            messages.error(request, f'Account locked due to too many failed attempts. Try again in {remaining} minute(s).')
            return render(request, 'pos/front_office/pin_lock.html', {
                'business': business,
                'branch': branch,
                'terminal': terminal,
                'employee_id': employee_id,
            })

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
            messages.error(request, 'PIN login is not configured for this user. Please contact your manager to set a POS PIN.')
            return render(request, 'pos/front_office/pin_lock.html', {
                'business': business,
                'branch': branch,
                'terminal': terminal,
                'employee_id': employee_id,
            })

        # Verify PIN (in case employee_id was provided)
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
                failure_msg = f'Invalid PIN. {remaining_attempts} attempt(s) remaining before lockout.'

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

            messages.error(request, failure_msg)
            return render(request, 'pos/front_office/pin_lock.html', {
                'business': business,
                'branch': branch,
                'terminal': terminal,
                'employee_id': employee_id,
            })

        # Check terminal authorization if terminal is present
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
                messages.error(request, f'Terminal login rejected: {reason}')
                return render(request, 'pos/front_office/pin_lock.html', {
                    'business': business,
                    'branch': branch,
                    'terminal': terminal,
                    'employee_id': employee_id,
                })

        # Authentication Success
        cache.delete(attempts_key)
        auth.login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        # Auto-create or bind terminal if not registered on device
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

        # Log Successful Login Audit
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

        request.session['is_front_office_session'] = True
        request.session['active_branch_id'] = branch.pk if branch else None

        # Check existing active shift session for this cashier
        pos_session = None
        if business:
            from django.db.models import Q
            pos_session = POSSession.objects.filter(
                business=business,
                status='open'
            ).filter(
                Q(cashier=user) | Q(opened_by=user)
            ).order_by('-opened_at').first()

        cashier_display_name = user.get_full_name() or user.username

        if pos_session:
            request.session['pos_session_id'] = pos_session.pk
            messages.success(request, f'Welcome back, {cashier_display_name}! Active session #{pos_session.session_number} resumed.')
            response = redirect('pos_screen')
        else:
            # Prompt to open new cashier shift
            messages.info(request, f'Welcome, {cashier_display_name}! Please enter opening float to open your shift.')
            response = redirect('terminal_session_open')

        if terminal and terminal.device_token:
            response.set_cookie('pos_terminal_token', terminal.device_token, max_age=315360000)  # 10 years
        return response

    # GET: Load registered terminal cashiers for quick display if available
    available_cashiers = []
    if business:
        available_cashiers = list(User.objects.filter(
            business_memberships__business=business,
            business_memberships__is_active=True,
            profile__pin_hash__isnull=False,
        ).exclude(profile__pin_hash='').select_related('profile')[:10])

    return render(request, 'pos/front_office/pin_lock.html', {
        'business': business,
        'branch': branch,
        'terminal': terminal,
        'available_cashiers': available_cashiers,
    })


@require_POST
def terminal_lock(request):
    """
    Quick lock the terminal without terminating the active cashier shift session.
    """
    request.session['is_terminal_locked'] = True
    auth.logout(request)
    messages.info(request, 'Terminal locked. Enter PIN to resume.')
    return redirect('front_office_login')


@login_required
@business_required
def terminal_register(request):
    """
    Register and authorize the current browser/device as a POSTerminal.
    Restricted to Admins and Managers.
    """
    business = request.business
    membership = getattr(request, 'business_membership', None)
    if not request.user.is_superuser and (not membership or membership.role not in ['owner', 'admin', 'manager']):
        messages.error(request, 'Administrator or Manager access required to register terminals.')
        return redirect('pos_screen')

    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        terminal_code = request.POST.get('terminal_code', '').strip().upper()
        branch_id = request.POST.get('branch_id')

        if not name or not terminal_code or not branch_id:
            messages.error(request, 'Terminal name, code, and branch are required.')
            return redirect('terminal_register')

        branch = get_object_or_404(Branch, pk=branch_id, business=business)
        device_token = str(uuid.uuid4())

        terminal, created = POSTerminal.objects.update_or_create(
            business=business,
            terminal_code=terminal_code,
            defaults={
                'name': name,
                'branch': branch,
                'device_token': device_token,
                'ip_address': _get_client_ip(request),
                'is_active': True,
                'last_active_at': timezone.now(),
            }
        )

        messages.success(request, f'Terminal "{terminal.name}" ({terminal.terminal_code}) registered successfully on this device.')
        response = redirect('front_office_login')
        response.set_cookie('pos_terminal_token', terminal.device_token, max_age=315360000)
        return response

    return render(request, 'pos/terminals/terminal_register.html', {
        'business': business,
        'branches': branches,
    })


@login_required
@business_required
def terminal_session_open(request):
    """Open a new cashier drawer shift session"""
    business = request.business
    user = request.user
    terminal = getattr(request, 'terminal', None)
    branch = getattr(request, 'branch', None)

    if request.method == 'POST':
        opening_cash_str = request.POST.get('opening_cash', '0').strip()
        try:
            opening_cash = Decimal(opening_cash_str)
        except Exception:
            opening_cash = Decimal('0.00')

        notes = request.POST.get('notes', '').strip()

        from django.db.models import Q
        # Check existing open session
        existing = POSSession.objects.filter(
            business=business, status='open'
        ).filter(
            Q(opened_by=user) | Q(cashier=user)
        ).first()
        if not existing and terminal:
            existing = POSSession.objects.filter(
                business=business, terminal=terminal, status='open'
            ).first()

        if existing:
            messages.info(request, f'You already have an active shift session (#Session {existing.session_number}).')
            request.session['pos_session_id'] = existing.pk
            return redirect('pos_screen')

        session = POSSession.objects.create(
            business=business,
            branch=branch,
            terminal=terminal,
            terminal_identifier=terminal.terminal_code if terminal else '',
            opened_by=user,
            cashier=user,
            opening_cash=opening_cash,
            status='open',
            notes=notes,
        )
        request.session['pos_session_id'] = session.pk
        messages.success(request, f'Shift Session #{session.session_number} opened successfully with KES {opening_cash:,.2f} opening cash.')
        return redirect('pos_screen')

    return render(request, 'pos/front_office/session_open.html', {
        'business': business,
        'branch': branch,
        'terminal': terminal,
    })


@login_required
@business_required
def terminal_session_close(request):
    """
    Close the active cashier shift session, record counted cash, and generate Z-Report.
    """
    business = request.business
    user = request.user
    session_id = request.session.get('pos_session_id')
    terminal = getattr(request, 'terminal', None)
    
    from django.db.models import Q
    pos_session = None
    if session_id:
        pos_session = POSSession.objects.filter(pk=session_id, business=business, status='open').first()
    if not pos_session:
        pos_session = POSSession.objects.filter(
            business=business, status='open'
        ).filter(
            Q(opened_by=user) | Q(cashier=user)
        ).order_by('-opened_at').first()
    if not pos_session and terminal:
        pos_session = POSSession.objects.filter(
            business=business, terminal=terminal, status='open'
        ).order_by('-opened_at').first()

    if not pos_session:
        request.session.pop('pos_session_id', None)
        messages.warning(request, 'No active shift session found to close. Please open a shift first.')
        return redirect('terminal_session_open')

    request.session['pos_session_id'] = pos_session.pk

    if request.method == 'POST':
        closing_cash_str = request.POST.get('closing_cash', '0').strip()
        notes = request.POST.get('notes', '').strip()
        try:
            closing_cash = Decimal(closing_cash_str)
        except Exception:
            closing_cash = Decimal('0.00')

        # Use ZReportService to close session & generate Z-Report
        ip_address = _get_client_ip(request)
        user_agent = _get_user_agent(request)
        
        try:
            zreport = ZReportService.close_session(
                session_id=pos_session.id,
                user=user,
                closing_cash=closing_cash,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            
            # Log session closed audit
            PINLoginAuditLog.objects.create(
                business=business,
                branch=pos_session.branch,
                user=user,
                employee_id=getattr(user.profile, 'employee_id', '') if hasattr(user, 'profile') else '',
                terminal=pos_session.terminal,
                terminal_code=pos_session.terminal_identifier,
                status='session_closed',
                failure_reason=f'Closed shift session #{pos_session.session_number} (Z-Report #{zreport.z_number})',
                ip_address=ip_address,
                user_agent=user_agent,
            )

            request.session.pop('pos_session_id', None)
            messages.success(request, f'Shift Session #{pos_session.session_number} closed. Z-Report #{zreport.z_number} generated.')
            return redirect('front_office_zreport')
        except Exception as e:
            messages.error(request, f'Failed to close session: {str(e)}')

    # Preview current session totals
    from .models import Sale
    sales = Sale.objects.filter(session=pos_session)
    report_data = ZReportService._aggregate_session_data(
        session=pos_session,
        sales=sales,
        closing_cash=pos_session.opening_cash,
        user=user
    )
    cash_mgmt = report_data.get('cash_management', {})
    expected_cash = Decimal(str(cash_mgmt.get('expected_cash', pos_session.opening_cash)))

    return render(request, 'pos/front_office/session_close.html', {
        'business': business,
        'session': pos_session,
        'report_data': report_data,
        'expected_cash': expected_cash,
    })


@login_required
@business_required
@front_office_required
def front_office_pos(request):
    """
    Main Front Office POS Terminal screen.
    """
    from .views import pos_screen
    return pos_screen(request)


@login_required
@business_required
def front_office_zreport(request):
    """
    Front Office Shift Z-Report View.
    Cashiers can only view Z-Reports generated during their own session(s).
    Managers / Admins can view recent branch Z-reports.
    """
    business = request.business
    user = request.user
    membership = getattr(request, 'business_membership', None)
    is_cashier_only = membership and membership.role in ['cashier', 'sales'] and not user.is_superuser

    if is_cashier_only:
        # Cashier: only own Z-reports
        zreports = ZReport.objects.filter(
            business=business,
            created_by=user,
            is_voided=False
        ).select_related('session', 'created_by').order_by('-created_at')[:20]
    else:
        # Manager / Admin: branch or store Z-reports
        branch = getattr(request, 'branch', None)
        qs = ZReport.objects.filter(business=business, is_voided=False)
        if branch and not user.is_superuser and membership.role not in ['owner', 'admin']:
            qs = qs.filter(session__branch=branch)
        zreports = qs.select_related('session', 'created_by').order_by('-created_at')[:30]

    latest_report = zreports.first() if zreports.exists() else None

    return render(request, 'pos/front_office/shift_zreport.html', {
        'business': business,
        'zreports': zreports,
        'latest_report': latest_report,
        'is_cashier_only': is_cashier_only,
    })
