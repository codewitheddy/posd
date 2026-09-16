"""
Cash Pickup / Till Drop Views for Marid POS
Handles dual-custody cash pickups, drawer cash telemetry, safe transfers, and 4 audit reports.
"""

import json
from decimal import Decimal
from datetime import date, datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.urls import reverse
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models import Sum, Count, Q

from pos.models import (
    Business, Branch, POSTerminal, POSSession, Shift,
    CashPickup, BankingRecord, BankingAuditLog, UserProfile, BusinessMembership
)
from pos.decorators import business_required
from pos.cash_pickup_services import CashPickupService
from pos.security_utils import is_user_supervisor


@login_required
@business_required
def cash_pickup_list(request, slug=None):
    """
    Directory list view of all Cash Pickups / Till Drops across the business.
    """
    business = request.business
    membership = getattr(request, 'business_membership', None)

    # Filters
    status_filter = request.GET.get('status', '').strip()
    branch_filter = request.GET.get('branch', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    search_query = request.GET.get('q', '').strip()

    pickups_qs = CashPickup.objects.filter(business=business).select_related(
        'branch', 'terminal', 'session', 'cashier', 'supervisor', 'banking_record'
    )

    if status_filter:
        pickups_qs = pickups_qs.filter(status=status_filter)
    if branch_filter:
        pickups_qs = pickups_qs.filter(branch_id=branch_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            pickups_qs = pickups_qs.filter(pickup_time__date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            pickups_qs = pickups_qs.filter(pickup_time__date__lte=d_to)
        except ValueError:
            pass
    if search_query:
        pickups_qs = pickups_qs.filter(
            Q(pickup_number__icontains=search_query) |
            Q(pickup_reference__icontains=search_query) |
            Q(cashier__username__icontains=search_query) |
            Q(supervisor__username__icontains=search_query) |
            Q(notes__icontains=search_query)
        )

    # KPI Summary Metrics
    today = timezone.localdate()
    today_pickups = CashPickup.objects.filter(business=business, pickup_time__date=today)
    metrics = {
        'total_today': today_pickups.aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
        'count_today': today_pickups.count(),
        'total_in_safe': CashPickup.objects.filter(business=business, status='in_safe').aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
        'count_in_safe': CashPickup.objects.filter(business=business, status='in_safe').count(),
        'total_confirmed_pending': CashPickup.objects.filter(business=business, status='confirmed').aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
        'count_confirmed_pending': CashPickup.objects.filter(business=business, status='confirmed').count(),
        'total_banked': CashPickup.objects.filter(business=business, status='banked').aggregate(t=Sum('amount'))['t'] or Decimal('0.00'),
    }

    paginator = Paginator(pickups_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')
    can_authorize = request.user.is_superuser or (membership and membership.has_permission('can_authorize_cash_pickup'))
    can_request = request.user.is_superuser or (membership and membership.has_permission('can_request_cash_pickup'))

    # Check active session drawer status for quick preview
    drawer_status = CashPickupService.get_drawer_cash_summary(business, cashier=request.user)

    context = {
        'pickups': page_obj,
        'page_obj': page_obj,
        'metrics': metrics,
        'branches': branches,
        'drawer_status': drawer_status,
        'status_filter': status_filter,
        'branch_filter': branch_filter,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'can_authorize': can_authorize,
        'can_request': can_request,
    }
    return render(request, 'pos/cash_pickups/pickup_list.html', context)


@login_required
@business_required
def cash_pickup_detail(request, slug=None, pickup_id=None):
    """
    Detailed view of a Cash Pickup record including 5-step Chain of Custody trajectory.
    """
    business = request.business
    pickup = get_object_or_404(
        CashPickup.objects.select_related('branch', 'terminal', 'session', 'cashier', 'supervisor', 'banking_record'),
        id=pickup_id, business=business
    )

    chain = CashPickupService.get_chain_of_custody(pickup, business)

    context = {
        'pickup': pickup,
        'chain': chain,
    }
    return render(request, 'pos/cash_pickups/pickup_detail.html', context)


@login_required
@business_required
def cash_pickup_slip_print(request, slug=None, pickup_id=None):
    """
    Printable thermal receipt format for the Cash Pickup bag / envelope slip.
    """
    business = request.business
    pickup = get_object_or_404(
        CashPickup.objects.select_related('branch', 'terminal', 'session', 'cashier', 'supervisor'),
        id=pickup_id, business=business
    )
    return render(request, 'pos/cash_pickups/pickup_slip_print.html', {
        'pickup': pickup,
        'business': business,
        'print_time': timezone.now(),
    })


@login_required
@business_required
@require_http_methods(['GET', 'POST'])
def cash_pickup_create(request, slug=None):
    """
    Create a new Cash Pickup / Till Drop.
    Supports standard web form submissions and POS terminal AJAX JSON requests.
    Enforces dual-custody authorization.
    """
    business = request.business
    is_json = (
        (getattr(request, 'content_type', '') or '').startswith('application/json') or
        request.META.get('CONTENT_TYPE', '').startswith('application/json') or
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest' or
        'application/json' in request.META.get('HTTP_ACCEPT', '')
    )

    if request.method == 'POST':
        data = {}
        content_type = getattr(request, 'content_type', '') or request.META.get('CONTENT_TYPE', '')
        if 'application/json' in content_type and request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except Exception:
                pass
        if not data:
            data = request.POST.dict()

        amount_raw = data.get('amount', '0')
        pickup_reference = str(data.get('pickup_reference', '') or data.get('bag_reference', '')).strip()
        supervisor_credential = str(data.get('supervisor_credential', '') or data.get('pin', '') or data.get('password', '')).strip()
        reason = data.get('reason', 'threshold_exceeded')
        tender_type = data.get('tender_type', 'cash')
        notes = data.get('notes', '').strip()
        is_peer_witness = data.get('witness_type') == 'peer_cashier' or data.get('is_peer_witness') in [True, 'true', '1']
        peer_witness_id = data.get('peer_witness_user_id')

        try:
            amount = Decimal(str(amount_raw))
        except Exception:
            if is_json:
                return JsonResponse({'success': False, 'error': 'Invalid pickup amount format.'}, status=400)
            messages.error(request, 'Invalid pickup amount.')
            return redirect('cash_pickup_list', slug=business.slug)

        # Resolve session, terminal, branch
        session_id = data.get('session_id') or request.session.get('pos_session_id')
        session = None
        if session_id:
            session = POSSession.objects.filter(id=session_id, business=business).first()

        terminal_id = data.get('terminal_id') or request.session.get('active_terminal_id')
        terminal = None
        if terminal_id:
            terminal = POSTerminal.objects.filter(id=terminal_id, business=business).first()

        branch = None
        branch_id = data.get('branch_id') or (session.branch_id if session else None) or (terminal.branch_id if terminal else None)
        if branch_id:
            branch = Branch.objects.filter(id=branch_id, business=business).first()

        peer_user = None
        if is_peer_witness and peer_witness_id:
            peer_user = User.objects.filter(id=peer_witness_id).first()

        try:
            pickup = CashPickupService.record_pickup(
                business=business,
                cashier=request.user,
                supervisor_credential=supervisor_credential,
                amount=amount,
                pickup_reference=pickup_reference,
                reason=reason,
                tender_type=tender_type,
                currency='KES',
                session=session,
                terminal=terminal,
                branch=branch,
                notes=notes,
                witness_type='peer_cashier' if is_peer_witness else 'supervisor',
                peer_witness_user=peer_user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        except ValidationError as e:
            err_text = str(e.messages[0] if hasattr(e, 'messages') else e)
            if is_json:
                return JsonResponse({'success': False, 'error': err_text}, status=400)
            messages.error(request, err_text)
            return redirect('cash_pickup_list', slug=business.slug)
        except Exception as e:
            if is_json:
                return JsonResponse({'success': False, 'error': f'Failed to record cash pickup: {str(e)}'}, status=500)
            messages.error(request, f'Failed to record cash pickup: {str(e)}')
            return redirect('cash_pickup_list', slug=business.slug)

        if is_json:
            return JsonResponse({
                'success': True,
                'pickup': {
                    'id': pickup.id,
                    'pickup_number': pickup.pickup_number,
                    'amount': float(pickup.amount),
                    'reference': pickup.pickup_reference,
                    'time': pickup.pickup_time.strftime('%H:%M:%S'),
                    'cashier': pickup.cashier.username,
                    'supervisor': pickup.supervisor.username,
                    'status': pickup.status,
                },
                'message': f"Cash Pickup {pickup.pickup_number} of KES {pickup.amount:.2f} confirmed successfully."
            })

        messages.success(request, f"Cash Pickup {pickup.pickup_number} recorded successfully.")
        return redirect('cash_pickup_detail', slug=business.slug, pickup_id=pickup.id)

    # GET: Form View
    drawer_status = CashPickupService.get_drawer_cash_summary(business, cashier=request.user)
    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')
    peer_cashiers = User.objects.filter(
        business_memberships__business=business,
        business_memberships__is_active=True
    ).exclude(id=request.user.id).order_by('username')

    context = {
        'drawer_status': drawer_status,
        'branches': branches,
        'peer_cashiers': peer_cashiers,
    }
    return render(request, 'pos/cash_pickups/pickup_form.html', context)


@login_required
@business_required
def cash_pickup_drawer_status(request, slug=None):
    """
    Real-time JSON endpoint for POS registers to get live drawer cash totals and suggested pickup.
    """
    business = request.business
    session_id = request.GET.get('session_id') or request.session.get('pos_session_id')
    terminal_id = request.GET.get('terminal_id') or request.session.get('active_terminal_id')

    session = POSSession.objects.filter(id=session_id, business=business).first() if session_id else None
    terminal = POSTerminal.objects.filter(id=terminal_id, business=business).first() if terminal_id else None

    summary = CashPickupService.get_drawer_cash_summary(
        business=business, session=session, terminal=terminal, cashier=request.user
    )

    return JsonResponse({
        'success': True,
        'opening_float': float(summary['opening_float']),
        'total_cash_sales': float(summary['total_cash_sales']),
        'sales_count': summary['sales_count'],
        'total_pickups': float(summary['total_pickups']),
        'pickups_count': summary['pickups_count'],
        'total_refunds': float(summary['total_refunds']),
        'current_drawer_cash': float(summary['current_drawer_cash']),
        'target_float': float(summary['target_float']),
        'suggested_pickup': float(summary['suggested_pickup']),
        'session_id': summary['session'].id if summary['session'] else None,
        'session_number': summary['session'].session_number if summary['session'] else None,
    })


@login_required
@business_required
@require_POST
def cash_pickup_transfer_safe(request, slug=None):
    """
    Transfers one or more confirmed cash pickups into the central vault / safe.
    """
    business = request.business
    pickup_ids = request.POST.getlist('pickup_ids')
    notes = request.POST.get('notes', '').strip()

    if not pickup_ids:
        raw_ids = request.POST.get('pickup_id')
        if raw_ids:
            pickup_ids = [raw_ids]

    if not pickup_ids:
        messages.error(request, 'Please select at least one cash pickup to transfer to safe.')
        return redirect('cash_pickup_list', slug=business.slug)

    try:
        int_ids = [int(x) for x in pickup_ids]
        count = CashPickupService.transfer_to_safe(int_ids, business, request.user, notes)
        messages.success(request, f"Successfully transferred {count} cash pickup(s) to store safe.")
    except Exception as e:
        messages.error(request, f"Error transferring pickups to safe: {str(e)}")

    return redirect('cash_pickup_list', slug=business.slug)


# ============================================================================
# CASH PICKUP & TILL DROP AUDIT REPORTS
# ============================================================================

@login_required
@business_required
def report_cash_pickup_log(request, slug=None):
    """
    Report 1: Cash Pickup Log — Chronological listing of all till drops with tender & actor filters.
    """
    business = request.business
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    branch_id = request.GET.get('branch', '')
    cashier_id = request.GET.get('cashier', '')
    supervisor_id = request.GET.get('supervisor', '')

    pickups_qs = CashPickup.objects.filter(business=business).select_related(
        'branch', 'terminal', 'session', 'cashier', 'supervisor', 'banking_record'
    )

    today = timezone.localdate()
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            pickups_qs = pickups_qs.filter(pickup_time__date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            pickups_qs = pickups_qs.filter(pickup_time__date__lte=d_to)
        except ValueError:
            pass
    if branch_id:
        pickups_qs = pickups_qs.filter(branch_id=branch_id)
    if cashier_id:
        pickups_qs = pickups_qs.filter(cashier_id=cashier_id)
    if supervisor_id:
        pickups_qs = pickups_qs.filter(supervisor_id=supervisor_id)

    totals = pickups_qs.aggregate(
        total_amount=Sum('amount'),
        total_count=Count('id')
    )

    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')
    cashiers = User.objects.filter(business_memberships__business=business).distinct().order_by('username')

    context = {
        'pickups': pickups_qs.order_by('-pickup_time'),
        'totals': totals,
        'branches': branches,
        'cashiers': cashiers,
        'date_from': date_from,
        'date_to': date_to,
        'selected_branch': branch_id,
        'selected_cashier': cashier_id,
        'selected_supervisor': supervisor_id,
    }
    return render(request, 'pos/cash_pickups/reports/pickup_log.html', context)


@login_required
@business_required
def report_chain_of_custody(request, slug=None):
    """
    Report 2: Chain of Custody Report — Traces pickup references from till to bank statement.
    """
    business = request.business
    query = request.GET.get('q', '').strip()
    selected_pickup = None
    chain = None

    if query:
        selected_pickup = CashPickup.objects.filter(
            business=business
        ).filter(
            Q(pickup_number__iexact=query) | Q(pickup_reference__iexact=query)
        ).select_related('branch', 'terminal', 'session', 'cashier', 'supervisor', 'banking_record').first()

        if selected_pickup:
            chain = CashPickupService.get_chain_of_custody(selected_pickup, business)

    recent_pickups = CashPickup.objects.filter(
        business=business
    ).select_related('branch', 'terminal', 'cashier', 'supervisor', 'banking_record').order_by('-pickup_time')[:15]

    context = {
        'query': query,
        'selected_pickup': selected_pickup,
        'chain': chain,
        'recent_pickups': recent_pickups,
    }
    return render(request, 'pos/cash_pickups/reports/chain_of_custody.html', context)


@login_required
@business_required
def report_zreport_variance(request, slug=None):
    """
    Report 3: Z-Report Variance Report — Analyzes register closing variances after factoring pickups.
    """
    business = request.business
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    branch_id = request.GET.get('branch', '')

    branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None

    d_from = None
    d_to = None
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            pass

    analysis = CashPickupService.get_zreport_variance_analysis(
        business=business, start_date=d_from, end_date=d_to, branch=branch
    )

    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')

    total_expected = sum(item['expected_drawer'] for item in analysis)
    total_counted = sum(item['counted_closing'] for item in analysis)
    net_variance = total_counted - total_expected
    discrepant_sessions = sum(1 for item in analysis if not item['is_balanced'])

    context = {
        'analysis': analysis,
        'branches': branches,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'total_expected': total_expected,
        'total_counted': total_counted,
        'net_variance': net_variance,
        'discrepant_sessions': discrepant_sessions,
    }
    return render(request, 'pos/cash_pickups/reports/zreport_variance.html', context)


@login_required
@business_required
def report_supervisor_pickup_summary(request, slug=None):
    """
    Report 4: Supervisor Pickup Summary — Custody and accountability totals per supervisor.
    """
    business = request.business
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    branch_id = request.GET.get('branch', '')

    branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None

    d_from = None
    d_to = None
    if date_from:
        try:
            d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            pass

    summary = CashPickupService.get_supervisor_summary(
        business=business, start_date=d_from, end_date=d_to, branch=branch
    )

    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')
    grand_total = sum(item['total_amount'] for item in summary)
    grand_count = sum(item['pickups_count'] for item in summary)

    context = {
        'summary': summary,
        'branches': branches,
        'selected_branch': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'grand_total': grand_total,
        'grand_count': grand_count,
    }
    return render(request, 'pos/cash_pickups/reports/supervisor_summary.html', context)
