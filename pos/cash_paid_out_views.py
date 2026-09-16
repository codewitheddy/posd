"""
Views and Controllers for Cash Paid-Out / Till Expenses Module
"""

import json
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count, Q

from pos.decorators import business_required
from pos.models import (
    Business, Branch, POSTerminal, POSSession, Shift, ExpenseCategory, Expense,
    CashPaidOut, BankingAuditLog, ActivityLog
)
from pos.cash_paid_out_services import CashPaidOutService
from pos.security_utils import is_user_supervisor


@login_required
@business_required
def cash_paid_out_list(request, slug=None):
    """
    Primary Ledger view for Cash Paid-Outs (Till Expenses).
    Shows running metrics, status filter badges, and searchable payout records.
    """
    business = request.business
    membership = getattr(request, 'business_membership', None)

    # Filter params
    status_filter = request.GET.get('status', '').strip()
    category_id = request.GET.get('category', '').strip()
    branch_id = request.GET.get('branch', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    search_query = request.GET.get('q', '').strip()

    queryset = CashPaidOut.objects.filter(business=business).select_related(
        'branch', 'terminal', 'session', 'category', 'requested_by', 'authorized_by', 'expense_entry'
    )

    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if category_id:
        queryset = queryset.filter(category_id=category_id)
    if branch_id:
        queryset = queryset.filter(branch_id=branch_id)
    if date_from:
        queryset = queryset.filter(paid_out_time__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(paid_out_time__date__lte=date_to)
    if search_query:
        queryset = queryset.filter(
            Q(paid_out_number__icontains=search_query) |
            Q(payee__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(receipt_reference__icontains=search_query) |
            Q(requested_by__username__icontains=search_query) |
            Q(authorized_by__username__icontains=search_query)
        )

    # Calculate summary metrics
    today = timezone.localdate()
    today_payouts = CashPaidOut.objects.filter(
        business=business, paid_out_time__date=today,
        status__in=['paid_pending_receipt', 'confirmed', 'written_off']
    )
    today_total = today_payouts.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    pending_qs = CashPaidOut.objects.filter(business=business, status='paid_pending_receipt')
    pending_count = pending_qs.count()
    pending_amount = pending_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    now = timezone.now()
    overdue_count = pending_qs.filter(receipt_due_by__lt=now).count()
    confirmed_count = CashPaidOut.objects.filter(business=business, status='confirmed').count()

    metrics = {
        'today_total': today_total,
        'today_count': today_payouts.count(),
        'pending_count': pending_count,
        'pending_amount': pending_amount,
        'overdue_count': overdue_count,
        'confirmed_count': confirmed_count,
    }

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    categories = ExpenseCategory.objects.filter(
        Q(business=business) | Q(business__isnull=True)
    ).order_by('name')
    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')

    can_authorize = request.user.is_superuser or (membership and membership.has_permission('can_authorize_cash_paid_out')) or (membership and membership.role in ['owner', 'admin', 'manager'])
    can_request = request.user.is_superuser or (membership and membership.has_permission('can_request_cash_paid_out')) or (membership and membership.role in ['owner', 'admin', 'manager', 'cashier', 'sales'])
    can_manage_receipts = request.user.is_superuser or (membership and membership.has_permission('can_manage_paid_out_receipts')) or (membership and membership.role in ['owner', 'admin', 'manager', 'cashier'])

    drawer_status = CashPaidOutService.get_drawer_cash_summary(business, cashier=request.user)

    context = {
        'paid_outs': page_obj,
        'page_obj': page_obj,
        'metrics': metrics,
        'categories': categories,
        'branches': branches,
        'drawer_status': drawer_status,
        'status_filter': status_filter,
        'category_id': category_id,
        'branch_filter': branch_id,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'can_authorize': can_authorize,
        'can_request': can_request,
        'can_manage_receipts': can_manage_receipts,
    }
    return render(request, 'pos/cash_paid_outs/paid_out_list.html', context)


@login_required
@business_required
def cash_paid_out_detail(request, slug=None, paid_out_id=None):
    """
    Detailed audit view of a Cash Paid-Out record including receipt attachment,
    exception log, linked GL expense entry, and reversal options.
    """
    business = request.business
    paid_out = get_object_or_404(
        CashPaidOut.objects.select_related(
            'branch', 'terminal', 'session', 'category', 'requested_by', 'authorized_by',
            'expense_entry', 'exception_approved_by', 'reversed_by'
        ),
        id=paid_out_id, business=business
    )

    membership = getattr(request, 'business_membership', None)
    can_authorize = request.user.is_superuser or (membership and membership.has_permission('can_authorize_cash_paid_out')) or (membership and membership.role in ['owner', 'admin', 'manager'])
    can_manage_receipts = request.user.is_superuser or (membership and membership.has_permission('can_manage_paid_out_receipts')) or (membership and membership.role in ['owner', 'admin', 'manager', 'cashier'])

    is_overdue = paid_out.status == 'paid_pending_receipt' and paid_out.receipt_due_by and paid_out.receipt_due_by < timezone.now()

    context = {
        'paid_out': paid_out,
        'is_overdue': is_overdue,
        'can_authorize': can_authorize,
        'can_manage_receipts': can_manage_receipts,
    }
    return render(request, 'pos/cash_paid_outs/paid_out_detail.html', context)


@login_required
@business_required
def cash_paid_out_slip_print(request, slug=None, paid_out_id=None):
    """
    Printable 80mm thermal voucher for cash paid-out expense with dual signature lines.
    """
    business = request.business
    paid_out = get_object_or_404(
        CashPaidOut.objects.select_related('branch', 'terminal', 'session', 'category', 'requested_by', 'authorized_by'),
        id=paid_out_id, business=business
    )
    return render(request, 'pos/cash_paid_outs/paid_out_slip_print.html', {
        'paid_out': paid_out,
        'business': business,
        'print_time': timezone.now(),
    })


@login_required
@business_required
@require_http_methods(['GET', 'POST'])
def cash_paid_out_create(request, slug=None):
    """
    Create a new Cash Paid-Out disbursement.
    Supports standard web form submissions and POS terminal AJAX JSON requests.
    Validates approval thresholds and supervisor credentials.
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
        category_id = data.get('category_id') or data.get('category')
        payee = str(data.get('payee', '')).strip()
        description = str(data.get('description', '')).strip()
        supervisor_credential = str(data.get('supervisor_credential', '') or data.get('pin', '') or data.get('password', '')).strip()
        receipt_reference = str(data.get('receipt_reference', '')).strip()
        is_petty_cash = data.get('is_petty_cash_fund') in [True, 'true', '1']
        notes = data.get('notes', '').strip()

        try:
            amount = Decimal(str(amount_raw))
        except Exception:
            if is_json:
                return JsonResponse({'success': False, 'error': 'Invalid payout amount format.'}, status=400)
            messages.error(request, 'Invalid payout amount format.')
            return redirect('cash_paid_out_list', slug=business.slug)

        category = get_object_or_404(ExpenseCategory, id=category_id)

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

        # Handle optional receipt file upload from form
        receipt_file = request.FILES.get('receipt_attachment')

        try:
            paid_out = CashPaidOutService.record_paid_out(
                business=business,
                requested_by=request.user,
                category=category,
                amount=amount,
                payee=payee,
                description=description,
                supervisor_credential=supervisor_credential,
                session=session,
                terminal=terminal,
                branch=branch,
                is_petty_cash_fund=is_petty_cash,
                receipt_reference=receipt_reference,
                notes=notes,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

            if receipt_file:
                paid_out.receipt_attachment = receipt_file
                paid_out.status = 'confirmed'
                paid_out.receipt_received_at = timezone.now()
                # Post GL Expense
                CashPaidOutService.attach_receipt(paid_out, request.user, receipt_reference, receipt_file)

        except ValidationError as e:
            err_text = str(e.messages[0] if hasattr(e, 'messages') else e)
            if is_json:
                return JsonResponse({'success': False, 'error': err_text}, status=400)
            messages.error(request, err_text)
            return redirect('cash_paid_out_list', slug=business.slug)
        except Exception as e:
            if is_json:
                return JsonResponse({'success': False, 'error': f'Failed to record cash payout: {str(e)}'}, status=500)
            messages.error(request, f'Failed to record cash payout: {str(e)}')
            return redirect('cash_paid_out_list', slug=business.slug)

        if is_json:
            return JsonResponse({
                'success': True,
                'paid_out': {
                    'id': paid_out.id,
                    'paid_out_number': paid_out.paid_out_number,
                    'amount': float(paid_out.amount),
                    'category': paid_out.category.name,
                    'payee': paid_out.payee,
                    'description': paid_out.description,
                    'time': paid_out.paid_out_time.strftime('%H:%M:%S'),
                    'requester': paid_out.requested_by.username,
                    'authorized_by': paid_out.authorized_by.username,
                    'status': paid_out.status,
                },
                'message': f"Cash Paid-Out {paid_out.paid_out_number} of KES {paid_out.amount:.2f} recorded successfully."
            })

        messages.success(request, f"Cash Paid-Out {paid_out.paid_out_number} recorded successfully.")
        return redirect('cash_paid_out_detail', slug=business.slug, paid_out_id=paid_out.id)

    # GET: Form View
    categories = ExpenseCategory.objects.filter(
        Q(business=business) | Q(business__isnull=True)
    ).order_by('name')
    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')
    drawer_status = CashPaidOutService.get_drawer_cash_summary(business, cashier=request.user)

    return render(request, 'pos/cash_paid_outs/paid_out_form.html', {
        'categories': categories,
        'branches': branches,
        'drawer_status': drawer_status,
        'business': business,
    })


@login_required
@business_required
@require_POST
def cash_paid_out_attach_receipt(request, slug=None, paid_out_id=None):
    """
    Submits a vendor receipt reference or file upload for an outstanding payout.
    """
    business = request.business
    paid_out = get_object_or_404(CashPaidOut, id=paid_out_id, business=business)

    receipt_ref = request.POST.get('receipt_reference', '').strip()
    receipt_file = request.FILES.get('receipt_attachment')
    notes = request.POST.get('notes', '').strip()

    try:
        CashPaidOutService.attach_receipt(
            paid_out=paid_out,
            user=request.user,
            receipt_reference=receipt_ref,
            receipt_file=receipt_file,
            notes=notes
        )
        messages.success(request, f"Receipt attached for {paid_out.paid_out_number}. Transaction is now confirmed and posted to Expense GL.")
    except Exception as e:
        messages.error(request, f"Failed to attach receipt: {str(e)}")

    return redirect('cash_paid_out_detail', slug=business.slug, paid_out_id=paid_out.id)


@login_required
@business_required
@require_POST
def cash_paid_out_receipt_exception(request, slug=None, paid_out_id=None):
    """
    Manager signs an exception note for an informal vendor without formal receipt.
    """
    business = request.business
    paid_out = get_object_or_404(CashPaidOut, id=paid_out_id, business=business)

    # Verify manager permission
    if not is_user_supervisor(request.user, business):
        messages.error(request, "Only supervisors and managers can sign receipt exception notes.")
        return redirect('cash_paid_out_detail', slug=business.slug, paid_out_id=paid_out.id)

    exception_reason = request.POST.get('exception_reason', '').strip()

    try:
        CashPaidOutService.grant_receipt_exception(
            paid_out=paid_out,
            supervisor_user=request.user,
            exception_reason=exception_reason
        )
        messages.success(request, f"Manager exception note approved for {paid_out.paid_out_number}. Status updated to Confirmed.")
    except Exception as e:
        messages.error(request, f"Failed to sign exception note: {str(e)}")

    return redirect('cash_paid_out_detail', slug=business.slug, paid_out_id=paid_out.id)


@login_required
@business_required
@require_POST
def cash_paid_out_reverse(request, slug=None, paid_out_id=None):
    """
    Reverses an unspent or cancelled paid out transaction and returns cash to till.
    """
    business = request.business
    paid_out = get_object_or_404(CashPaidOut, id=paid_out_id, business=business)

    supervisor_credential = request.POST.get('supervisor_credential', '').strip()
    reversal_reason = request.POST.get('reversal_reason', '').strip()

    try:
        CashPaidOutService.reverse_paid_out(
            paid_out=paid_out,
            user=request.user,
            supervisor_credential=supervisor_credential,
            reversal_reason=reversal_reason
        )
        messages.success(request, f"Cash Paid-Out {paid_out.paid_out_number} successfully reversed. Cash KES {paid_out.amount:.2f} returned to drawer.")
    except Exception as e:
        messages.error(request, f"Failed to reverse payout: {str(e)}")

    return redirect('cash_paid_out_detail', slug=business.slug, paid_out_id=paid_out.id)


@login_required
@business_required
def cash_paid_out_drawer_status(request, slug=None):
    """
    Live JSON API endpoint queried by POS terminals for current drawer balance,
    category thresholds, and pending receipt alerts.
    """
    business = request.business
    drawer_status = CashPaidOutService.get_drawer_cash_summary(business, cashier=request.user)

    categories = ExpenseCategory.objects.filter(
        Q(business=business) | Q(business__isnull=True)
    ).order_by('name')

    cat_list = [
        {
            'id': cat.id,
            'name': cat.name,
            'threshold': float(cat.requires_manager_approval_above or 1000.00),
            'code': cat.chart_of_accounts_code,
        }
        for cat in categories
    ]

    return JsonResponse({
        'success': True,
        'current_drawer_cash': float(drawer_status['current_drawer_cash']),
        'opening_float': float(drawer_status['opening_float']),
        'total_cash_sales': float(drawer_status['total_cash_sales']),
        'total_pickups': float(drawer_status['total_pickups']),
        'total_paid_outs': float(drawer_status['total_paid_outs']),
        'pending_receipts_count': drawer_status['pending_receipts_count'],
        'pending_receipts_amount': float(drawer_status['pending_receipts_amount']),
        'categories': cat_list,
    })


# ============================================================================
# FINANCIAL & AUDIT REPORTS
# ============================================================================

@login_required
@business_required
def report_paid_outs_log(request, slug=None):
    """
    Comprehensive itemized audit log of all cash payouts.
    """
    business = request.business
    date_from = request.GET.get('date_from', timezone.localdate().replace(day=1).isoformat())
    date_to = request.GET.get('date_to', timezone.localdate().isoformat())
    category_id = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')

    queryset = CashPaidOut.objects.filter(
        business=business,
        paid_out_time__date__gte=date_from,
        paid_out_time__date__lte=date_to
    ).select_related('category', 'requested_by', 'authorized_by', 'branch', 'terminal', 'expense_entry')

    if category_id:
        queryset = queryset.filter(category_id=category_id)
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    total_amount = queryset.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    categories = ExpenseCategory.objects.filter(Q(business=business) | Q(business__isnull=True)).order_by('name')

    return render(request, 'pos/cash_paid_outs/reports/paid_outs_log.html', {
        'payouts': queryset.order_by('-paid_out_time'),
        'total_amount': total_amount,
        'categories': categories,
        'date_from': date_from,
        'date_to': date_to,
        'category_id': category_id,
        'status_filter': status_filter,
    })


@login_required
@business_required
def report_missing_receipts(request, slug=None):
    """
    Chase-up schedule of all payouts in 'paid_pending_receipt' status.
    """
    business = request.business
    branch_id = request.GET.get('branch', '')
    branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None

    missing = CashPaidOutService.get_missing_receipts(business=business, branch=branch)
    total_pending = sum(m['paid_out'].amount for m in missing)
    overdue_count = sum(1 for m in missing if m['is_overdue'])
    branches = Branch.objects.filter(business=business, is_active=True).order_by('name')

    return render(request, 'pos/cash_paid_outs/reports/missing_receipts.html', {
        'missing_receipts': missing,
        'total_pending': total_pending,
        'overdue_count': overdue_count,
        'branches': branches,
        'selected_branch': branch_id,
    })


@login_required
@business_required
def report_expense_category_summary(request, slug=None):
    """
    Category expenditure aggregation with monthly budget cap tracking.
    """
    business = request.business
    today = timezone.localdate()
    start_date = date.fromisoformat(request.GET.get('start_date', today.replace(day=1).isoformat()))
    end_date = date.fromisoformat(request.GET.get('end_date', today.isoformat()))

    summary = CashPaidOutService.get_expense_category_summary(
        business=business, start_date=start_date, end_date=end_date
    )
    total_spend = sum(s['total_spent'] for s in summary)

    return render(request, 'pos/cash_paid_outs/reports/category_summary.html', {
        'category_summary': summary,
        'total_spend': total_spend,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
    })


@login_required
@business_required
def report_paid_out_approval_audit(request, slug=None):
    """
    High-value payout supervisor authorizations compliance log.
    """
    business = request.business
    today = timezone.localdate()
    start_date = date.fromisoformat(request.GET.get('start_date', today.replace(day=1).isoformat()))
    end_date = date.fromisoformat(request.GET.get('end_date', today.isoformat()))

    audit_logs = CashPaidOutService.get_approval_audit_trail(
        business=business, start_date=start_date, end_date=end_date
    )

    return render(request, 'pos/cash_paid_outs/reports/approval_audit.html', {
        'audit_logs': audit_logs,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
    })
