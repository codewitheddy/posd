"""
Banking & Bank Reconciliation Views for Marid POS
Handles Bank Accounts, Physical Cash Banking Records, Statement Ingestion,
Reconciliation Matching Workspace, and Accounting Reports.
"""

from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from .decorators import business_required
from .models import (
    Business, Branch, POSTerminal, BankAccount, BankingRecord,
    BankStatementImportBatch, BankStatementLine, ReconciliationMatch,
    BankingAuditLog, BusinessMembership
)
from .banking_services import (
    BankingCalculationService, StatementParserService, ReconciliationEngine
)


def _check_banking_permission(request, permission_code):
    """Helper to verify user has banking permissions in the current business."""
    if request.user.is_superuser:
        return True
    membership = getattr(request, 'business_membership', None)
    if not membership:
        membership = BusinessMembership.objects.filter(
            user=request.user, business=request.business, is_active=True
        ).first()
        request.business_membership = membership
    if membership:
        if membership.role in ['owner', 'admin', 'manager']:
            return True
        return membership.has_permission(permission_code)
    return False


# ==================== BANK ACCOUNTS ====================

@business_required
def bank_account_list(request, slug=None):
    """List and manage commercial bank accounts."""
    business = request.business
    accounts = BankAccount.objects.filter(business=business).annotate(
        records_count=Count('banking_records'),
        unmatched_count=Count('banking_records', filter=Q(banking_records__status__in=['banked', 'pending']))
    )

    total_opening = accounts.aggregate(t=Sum('opening_balance'))['t'] or Decimal('0.00')
    total_current = accounts.aggregate(t=Sum('current_balance'))['t'] or Decimal('0.00')

    context = {
        'accounts': accounts,
        'total_opening': total_opening,
        'total_current': total_current,
        'can_reconcile': _check_banking_permission(request, 'can_reconcile_banking'),
    }
    return render(request, 'pos/banking/bank_accounts.html', context)


@business_required
@require_POST
def bank_account_create_edit(request, slug=None):
    """Create or update a bank account."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        messages.error(request, "You don't have permission to configure bank accounts.")
        return redirect('bank_account_list', slug=request.business.slug)

    business = request.business
    account_id = request.POST.get('account_id')
    bank_name = request.POST.get('bank_name', '').strip()
    account_name = request.POST.get('account_name', '').strip()
    account_number = request.POST.get('account_number', '').strip()
    branch_name = request.POST.get('branch_name', '').strip()
    currency = request.POST.get('currency', 'KES').strip().upper()
    opening_balance_raw = request.POST.get('opening_balance', '0.00').strip()
    is_default = request.POST.get('is_default') == 'on' or request.POST.get('is_default') == 'true'
    notes = request.POST.get('notes', '').strip()

    if not bank_name or not account_name or not account_number:
        messages.error(request, "Bank Name, Account Name, and Account Number are required.")
        return redirect('bank_account_list', slug=business.slug)

    try:
        opening_balance = Decimal(opening_balance_raw)
    except (InvalidOperation, ValueError):
        opening_balance = Decimal('0.00')

    if account_id:
        acc = get_object_or_404(BankAccount, id=account_id, business=business)
        acc.bank_name = bank_name
        acc.account_name = account_name
        acc.account_number = account_number
        acc.branch_name = branch_name
        acc.currency = currency
        acc.opening_balance = opening_balance
        acc.is_default = is_default
        acc.notes = notes
        acc.save()
        messages.success(request, f"Bank account '{acc.bank_name} - {acc.account_name}' updated successfully.")
    else:
        if BankAccount.objects.filter(business=business, account_number=account_number).exists():
            messages.error(request, f"An account with number '{account_number}' already exists.")
            return redirect('bank_account_list', slug=business.slug)

        acc = BankAccount.objects.create(
            business=business,
            bank_name=bank_name,
            account_name=account_name,
            account_number=account_number,
            branch_name=branch_name,
            currency=currency,
            opening_balance=opening_balance,
            current_balance=opening_balance,
            is_default=is_default,
            notes=notes
        )
        messages.success(request, f"Bank account '{acc.bank_name} - {acc.account_name}' created successfully.")

    return redirect('bank_account_list', slug=business.slug)


@business_required
@require_POST
def bank_account_toggle_active(request, slug=None, account_id=None):
    """Toggle active/inactive status of a bank account."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    acc = get_object_or_404(BankAccount, id=account_id, business=request.business)
    acc.is_active = not acc.is_active
    acc.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'is_active': acc.is_active})


# ==================== BANKING RECORDS (PHYSICAL CASH DEPOSITS) ====================

@business_required
def banking_record_list(request, slug=None):
    """List physical cash banking records with filtering and metric summaries."""
    business = request.business
    qs = BankingRecord.objects.filter(business=business).select_related(
        'bank_account', 'branch', 'terminal', 'deposited_by', 'reconciled_by'
    )

    # Filters
    status = request.GET.get('status', '').strip()
    bank_account_id = request.GET.get('bank_account', '').strip()
    branch_id = request.GET.get('branch', '').strip()
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()
    search = request.GET.get('q', '').strip()

    if status:
        qs = qs.filter(status=status)
    if bank_account_id:
        qs = qs.filter(bank_account_id=bank_account_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            qs = qs.filter(deposit_date__gte=start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            qs = qs.filter(deposit_date__lte=end_date)
        except ValueError:
            pass
    if search:
        qs = qs.filter(
            Q(record_number__icontains=search) |
            Q(deposit_reference__icontains=search) |
            Q(notes__icontains=search) |
            Q(bank_account__bank_name__icontains=search)
        )

    # Summary metrics
    metrics = qs.aggregate(
        total_banked=Sum('deposited_amount'),
        total_expected=Sum('expected_amount'),
        total_variance=Sum('variance_amount'),
        count_matched=Count('id', filter=Q(status='matched')),
        count_pending=Count('id', filter=Q(status__in=['banked', 'pending'])),
        count_discrepancy=Count('id', filter=Q(status='discrepancy')),
    )

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)
    branches = Branch.objects.filter(business=business, is_active=True)

    context = {
        'page_obj': page_obj,
        'records': page_obj.object_list,
        'metrics': metrics,
        'bank_accounts': bank_accounts,
        'branches': branches,
        'current_status': status,
        'current_bank': bank_account_id,
        'current_branch': branch_id,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'search_query': search,
        'can_record': _check_banking_permission(request, 'can_record_banking'),
        'can_reconcile': _check_banking_permission(request, 'can_reconcile_banking'),
    }
    return render(request, 'pos/banking/banking_record_list.html', context)


@business_required
def banking_record_create(request, slug=None):
    """Record physical cash/cheque deposit into bank with auto-calculated expected collections."""
    business = request.business
    if not _check_banking_permission(request, 'can_record_banking'):
        messages.error(request, "You do not have permission to record cash banking deposits.")
        return redirect('banking_record_list', slug=business.slug)

    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)
    if not bank_accounts.exists():
        messages.warning(request, "Please create at least one Bank Account before recording cash banking.")
        return redirect('bank_account_list', slug=business.slug)

    branches = Branch.objects.filter(business=business, is_active=True)
    terminals = POSTerminal.objects.filter(business=business, is_active=True)

    today_str = timezone.localdate().isoformat()

    if request.method == 'POST':
        bank_account_id = request.POST.get('bank_account')
        branch_id = request.POST.get('branch') or None
        terminal_id = request.POST.get('terminal') or None
        period_start_str = request.POST.get('period_start') or today_str
        period_end_str = request.POST.get('period_end') or today_str
        deposit_date_str = request.POST.get('deposit_date') or today_str
        payment_type = request.POST.get('payment_type', 'cash')
        deposit_reference = request.POST.get('deposit_reference', '').strip()
        deposited_amount_raw = request.POST.get('deposited_amount', '0').strip()
        expected_amount_raw = request.POST.get('expected_amount', '0').strip()
        variance_reason = request.POST.get('variance_reason', '').strip()
        notes = request.POST.get('notes', '').strip()
        slip_image = request.FILES.get('slip_image')

        if not bank_account_id or not deposit_reference or not deposited_amount_raw:
            messages.error(request, "Bank Account, Deposit Slip Reference, and Deposited Amount are required.")
            return redirect('banking_record_create', slug=business.slug)

        try:
            period_start = datetime.strptime(period_start_str, '%Y-%m-%d').date()
            period_end = datetime.strptime(period_end_str, '%Y-%m-%d').date()
            deposit_date = datetime.strptime(deposit_date_str, '%Y-%m-%d').date()
            deposited_amount = Decimal(deposited_amount_raw)
            expected_amount = Decimal(expected_amount_raw)
        except (ValueError, InvalidOperation):
            messages.error(request, "Invalid date or numeric amount entered.")
            return redirect('banking_record_create', slug=business.slug)

        variance_amount = deposited_amount - expected_amount

        # If variance > 0 or < 0 and variance_reason is missing, enforce explanation
        if abs(variance_amount) > Decimal('100.00') and not variance_reason:
            messages.warning(request, f"Variance of KES {variance_amount:,.2f} requires an explanatory note.")
            context = {
                'bank_accounts': bank_accounts,
                'branches': branches,
                'terminals': terminals,
                'today_str': today_str,
                'form_data': request.POST,
            }
            return render(request, 'pos/banking/banking_record_form.html', context)

        bank_account = get_object_or_404(BankAccount, id=bank_account_id, business=business)
        branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None
        terminal = POSTerminal.objects.filter(id=terminal_id, business=business).first() if terminal_id else None

        status = 'discrepancy' if abs(variance_amount) > Decimal('500.00') else 'banked'

        record = BankingRecord.objects.create(
            business=business,
            branch=branch,
            terminal=terminal,
            bank_account=bank_account,
            period_start=period_start,
            period_end=period_end,
            expected_amount=expected_amount,
            deposited_amount=deposited_amount,
            variance_amount=variance_amount,
            payment_type=payment_type,
            deposit_reference=deposit_reference,
            deposit_date=deposit_date,
            deposited_by=request.user,
            slip_image=slip_image,
            status=status,
            variance_reason=variance_reason,
            notes=notes,
            created_by=request.user,
        )

        BankingAuditLog.objects.create(
            business=business,
            banking_record=record,
            action='record_created',
            performed_by=request.user,
            details={
                'record_number': record.record_number,
                'deposited_amount': float(deposited_amount),
                'expected_amount': float(expected_amount),
                'variance': float(variance_amount),
                'bank': bank_account.bank_name,
                'reference': deposit_reference,
            }
        )

        messages.success(request, f"Banking Record {record.record_number} recorded successfully for KES {deposited_amount:,.2f}.")
        return redirect('banking_record_detail', slug=business.slug, pk=record.pk)

    context = {
        'bank_accounts': bank_accounts,
        'branches': branches,
        'terminals': terminals,
        'today_str': today_str,
    }
    return render(request, 'pos/banking/banking_record_form.html', context)


@business_required
def banking_record_detail(request, slug=None, pk=None):
    """View full details, slip voucher, matched statement lines, and audit history of a deposit record."""
    business = request.business
    record = get_object_or_404(
        BankingRecord.objects.select_related(
            'bank_account', 'branch', 'terminal', 'deposited_by', 'reconciled_by', 'created_by'
        ),
        id=pk, business=business
    )

    reconciliation_matches = record.reconciliation_matches.prefetch_related('statement_lines').all()
    audit_logs = record.audit_logs.select_related('performed_by').all()[:20]

    context = {
        'record': record,
        'reconciliation_matches': reconciliation_matches,
        'audit_logs': audit_logs,
        'can_reconcile': _check_banking_permission(request, 'can_reconcile_banking'),
    }
    return render(request, 'pos/banking/banking_record_detail.html', context)


@business_required
@require_GET
def api_get_expected_cash(request, slug=None):
    """AJAX endpoint providing live calculation of expected cash for a given location and period."""
    business = request.business
    branch_id = request.GET.get('branch_id') or None
    terminal_id = request.GET.get('terminal_id') or None
    start_str = request.GET.get('period_start')
    end_str = request.GET.get('period_end')
    payment_type = request.GET.get('payment_type', 'cash')

    try:
        p_start = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else timezone.localdate()
        p_end = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else timezone.localdate()
    except ValueError:
        p_start = p_end = timezone.localdate()

    branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None
    terminal = POSTerminal.objects.filter(id=terminal_id, business=business).first() if terminal_id else None

    result = BankingCalculationService.calculate_expected_cash(
        business=business,
        branch=branch,
        terminal=terminal,
        period_start=p_start,
        period_end=p_end,
        payment_type=payment_type
    )

    return JsonResponse({
        'success': True,
        'expected_amount': float(result['expected_amount']),
        'total_collected': float(result['total_collected']),
        'already_banked': float(result['already_banked']),
        'expected_remaining': float(result['expected_remaining']),
        'sales_count': result['sales_count'],
        'period_start': result['period_start'].isoformat(),
        'period_end': result['period_end'].isoformat(),
    })


# ==================== BANK STATEMENTS ====================

@business_required
def bank_statement_list(request, slug=None):
    """List statement import batches and individual bank statement lines."""
    business = request.business
    batches = BankStatementImportBatch.objects.filter(business=business).select_related(
        'bank_account', 'imported_by'
    )[:10]

    lines_qs = BankStatementLine.objects.filter(business=business).select_related(
        'bank_account', 'batch', 'matched_banking_record'
    )

    # Filters
    status = request.GET.get('status', '').strip()
    bank_account_id = request.GET.get('bank_account', '').strip()
    line_type = request.GET.get('line_type', '').strip()
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()
    search = request.GET.get('q', '').strip()

    if status:
        lines_qs = lines_qs.filter(status=status)
    if bank_account_id:
        lines_qs = lines_qs.filter(bank_account_id=bank_account_id)
    if line_type:
        lines_qs = lines_qs.filter(line_type=line_type)
    if start_date_str:
        try:
            lines_qs = lines_qs.filter(transaction_date__gte=datetime.strptime(start_date_str, '%Y-%m-%d').date())
        except ValueError:
            pass
    if end_date_str:
        try:
            lines_qs = lines_qs.filter(transaction_date__lte=datetime.strptime(end_date_str, '%Y-%m-%d').date())
        except ValueError:
            pass
    if search:
        lines_qs = lines_qs.filter(
            Q(description__icontains=search) | Q(reference__icontains=search)
        )

    paginator = Paginator(lines_qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    metrics = lines_qs.aggregate(
        total_credits=Sum('amount', filter=Q(line_type='credit')),
        total_debits=Sum('amount', filter=Q(line_type='debit')),
        unmatched_count=Count('id', filter=Q(status='unmatched')),
        matched_count=Count('id', filter=Q(status='matched')),
    )

    context = {
        'batches': batches,
        'page_obj': page_obj,
        'lines': page_obj.object_list,
        'bank_accounts': bank_accounts,
        'metrics': metrics,
        'current_status': status,
        'current_bank': bank_account_id,
        'current_type': line_type,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'search_query': search,
        'can_reconcile': _check_banking_permission(request, 'can_reconcile_banking'),
    }
    return render(request, 'pos/banking/statement_import_list.html', context)


@business_required
@require_POST
def bank_statement_import(request, slug=None):
    """Import CSV or OFX bank statement file."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        messages.error(request, "Permission denied. Only authorized accountants can import bank statements.")
        return redirect('bank_statement_list', slug=request.business.slug)

    business = request.business
    bank_account_id = request.POST.get('bank_account')
    file_format = request.POST.get('file_format', 'csv')
    statement_file = request.FILES.get('statement_file')

    if not bank_account_id or not statement_file:
        messages.error(request, "Please select a Bank Account and choose a statement file to import.")
        return redirect('bank_statement_list', slug=business.slug)

    bank_account = get_object_or_404(BankAccount, id=bank_account_id, business=business)

    try:
        if file_format == 'ofx' or statement_file.name.lower().endswith(('.ofx', '.qbo')):
            batch = StatementParserService.parse_ofx(statement_file, bank_account, request.user)
        else:
            batch = StatementParserService.parse_csv(statement_file, bank_account, request.user)

        messages.success(
            request,
            f"Successfully imported {batch.total_lines} statement lines for '{bank_account.bank_name}'. Total Credits: KES {batch.total_credits:,.2f}"
        )
    except Exception as e:
        messages.error(request, f"Statement Import Failed: {str(e)}")

    return redirect('bank_statement_list', slug=business.slug)


@business_required
@require_POST
def bank_statement_manual_line(request, slug=None):
    """Add a manual single bank statement line when digital statement is unavailable."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        messages.error(request, "Permission denied.")
        return redirect('bank_statement_list', slug=request.business.slug)

    business = request.business
    bank_account_id = request.POST.get('bank_account')
    txn_date_str = request.POST.get('transaction_date') or timezone.localdate().isoformat()
    line_type = request.POST.get('line_type', 'credit')
    amount_raw = request.POST.get('amount', '0').strip()
    reference = request.POST.get('reference', '').strip()
    description = request.POST.get('description', '').strip()

    if not bank_account_id or not amount_raw or not description:
        messages.error(request, "Bank Account, Amount, and Description are required.")
        return redirect('bank_statement_list', slug=business.slug)

    try:
        txn_date = datetime.strptime(txn_date_str, '%Y-%m-%d').date()
        amount = Decimal(amount_raw)
    except (ValueError, InvalidOperation):
        messages.error(request, "Invalid date or numeric amount.")
        return redirect('bank_statement_list', slug=business.slug)

    bank_account = get_object_or_404(BankAccount, id=bank_account_id, business=business)

    line = BankStatementLine.objects.create(
        business=business,
        bank_account=bank_account,
        transaction_date=txn_date,
        line_type=line_type,
        amount=amount,
        reference=reference,
        description=description,
        status='unmatched'
    )

    BankingAuditLog.objects.create(
        business=business,
        statement_line=line,
        action='manual_line_added',
        performed_by=request.user,
        details={'amount': float(amount), 'type': line_type, 'bank': bank_account.bank_name}
    )

    messages.success(request, f"Statement line added: {line_type.upper()} KES {amount:,.2f}.")
    return redirect('bank_statement_list', slug=business.slug)


@business_required
@require_POST
def api_ignore_statement_line(request, slug=None, line_id=None):
    """Toggle a bank statement line between 'ignored' (non-POS) and 'unmatched'."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    line = get_object_or_404(BankStatementLine, id=line_id, business=request.business)
    if line.status == 'matched':
        return JsonResponse({'error': 'Cannot ignore a matched statement line. Please unmatch first.'}, status=400)

    line.status = 'ignored' if line.status == 'unmatched' else 'unmatched'
    line.save(update_fields=['status'])

    BankingAuditLog.objects.create(
        business=request.business,
        statement_line=line,
        action='line_ignored' if line.status == 'ignored' else 'unmatched',
        performed_by=request.user,
        details={'status': line.status}
    )

    return JsonResponse({'success': True, 'new_status': line.status})


# ==================== RECONCILIATION WORKSPACE ====================

@business_required
def bank_reconciliation_workspace(request, slug=None):
    """
    Split-screen interactive reconciliation workspace:
    Left: Unmatched Banking Records (Physical deposits)
    Right: Unmatched Bank Statement Credits
    """
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        messages.error(request, "Permission denied. Access restricted to accountants/reconcilers.")
        return redirect('banking_record_list', slug=request.business.slug)

    business = request.business
    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    selected_account_id = request.GET.get('bank_account')
    selected_account = None
    if selected_account_id:
        selected_account = bank_accounts.filter(id=selected_account_id).first()
    if not selected_account and bank_accounts.exists():
        selected_account = bank_accounts.first()

    # 1. Unmatched Banking Records (Deposits made, waiting to clear)
    records_qs = BankingRecord.objects.filter(
        business=business,
        status__in=['banked', 'pending', 'discrepancy']
    ).select_related('bank_account', 'branch', 'terminal', 'deposited_by')

    if selected_account:
        records_qs = records_qs.filter(bank_account=selected_account)

    # 2. Unmatched Statement Lines (Credits)
    lines_qs = BankStatementLine.objects.filter(
        business=business,
        status='unmatched',
        line_type='credit'
    ).select_related('bank_account', 'batch')

    if selected_account:
        lines_qs = lines_qs.filter(bank_account=selected_account)

    # 3. Recent Matches (History tab)
    recent_matches = ReconciliationMatch.objects.filter(
        business=business
    ).prefetch_related('banking_records', 'statement_lines').order_by('-matched_at')[:20]

    unmatched_records_total = records_qs.aggregate(t=Sum('deposited_amount'))['t'] or Decimal('0.00')
    unmatched_lines_total = lines_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    net_variance = unmatched_records_total - unmatched_lines_total

    context = {
        'bank_accounts': bank_accounts,
        'selected_account': selected_account,
        'unmatched_records': records_qs.order_by('-deposit_date'),
        'unmatched_lines': lines_qs.order_by('-transaction_date'),
        'recent_matches': recent_matches,
        'unmatched_records_total': unmatched_records_total,
        'unmatched_lines_total': unmatched_lines_total,
        'net_variance': net_variance,
    }
    return render(request, 'pos/banking/reconciliation_workspace.html', context)


@business_required
@require_POST
def api_auto_match(request, slug=None):
    """Trigger single-click auto-matching engine."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    business = request.business
    bank_account_id = request.POST.get('bank_account_id')
    tolerance_days_raw = request.POST.get('tolerance_days', '3')

    try:
        tolerance_days = int(tolerance_days_raw)
    except ValueError:
        tolerance_days = 3

    bank_account = BankAccount.objects.filter(id=bank_account_id, business=business).first() if bank_account_id else None

    result = ReconciliationEngine.auto_match(
        business=business,
        bank_account=bank_account,
        date_tolerance_days=tolerance_days,
        user=request.user
    )

    return JsonResponse({
        'success': True,
        'matched_count': result['matched_count'],
        'total_amount': float(result['total_matched_amount']),
        'remaining_records': result['remaining_unmatched_records'],
        'remaining_lines': result['remaining_unmatched_lines'],
    })


@business_required
@require_POST
def api_manual_match(request, slug=None):
    """Execute manual multi-link reconciliation matching."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    business = request.business
    record_ids = request.POST.getlist('record_ids[]') or request.POST.getlist('record_ids')
    line_ids = request.POST.getlist('line_ids[]') or request.POST.getlist('line_ids')
    bank_charge_raw = request.POST.get('bank_charge', '0.00').strip()
    notes = request.POST.get('notes', '').strip()

    if not record_ids or not line_ids:
        return JsonResponse({'error': 'Please select at least one deposit record and one statement line.'}, status=400)

    try:
        bank_charge = Decimal(bank_charge_raw) if bank_charge_raw else Decimal('0.00')
    except InvalidOperation:
        bank_charge = Decimal('0.00')

    try:
        match_obj = ReconciliationEngine.manual_match(
            business=business,
            banking_record_ids=record_ids,
            statement_line_ids=line_ids,
            bank_charge=bank_charge,
            user=request.user,
            notes=notes
        )
        return JsonResponse({
            'success': True,
            'match_number': match_obj.match_number,
            'match_type': match_obj.get_match_type_display(),
            'total_banked': float(match_obj.total_banked_amount),
            'total_statement': float(match_obj.total_statement_amount),
            'variance': float(match_obj.variance_amount),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@business_required
@require_POST
def api_unmatch(request, slug=None, match_id=None):
    """Unmatch a previously reconciled junction."""
    if not _check_banking_permission(request, 'can_reconcile_banking'):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        ReconciliationEngine.unmatch(match_id, request.business, request.user)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ==================== BANKING REPORTS ====================

@business_required
def report_daily_banking_summary(request, slug=None):
    """Daily Banking Summary: Expected Collections vs. Banked vs. Variance per branch/till."""
    business = request.business
    today = timezone.localdate()
    start_str = request.GET.get('start_date', (today - timedelta(days=14)).isoformat())
    end_str = request.GET.get('end_date', today.isoformat())
    branch_id = request.GET.get('branch', '')

    try:
        start_d = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_d = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        start_d = today - timedelta(days=14)
        end_d = today

    branch = Branch.objects.filter(id=branch_id, business=business).first() if branch_id else None

    # Aggregate day-by-day
    day_rows = []
    curr = start_d
    total_expected = Decimal('0.00')
    total_banked = Decimal('0.00')
    total_variance = Decimal('0.00')

    while curr <= end_d:
        calc = BankingCalculationService.calculate_expected_cash(
            business=business, branch=branch, period_start=curr, period_end=curr
        )
        exp = calc['expected_amount']

        banked_qs = BankingRecord.objects.filter(
            business=business, deposit_date=curr
        )
        if branch:
            banked_qs = banked_qs.filter(branch=branch)

        bnk = banked_qs.aggregate(t=Sum('deposited_amount'))['t'] or Decimal('0.00')
        var = bnk - exp

        day_rows.append({
            'date': curr,
            'expected': exp,
            'banked': bnk,
            'variance': var,
            'records_count': banked_qs.count(),
            'status': 'balanced' if abs(var) < Decimal('0.01') else ('over' if var > 0 else 'short')
        })

        total_expected += exp
        total_banked += bnk
        total_variance += var
        curr += timedelta(days=1)

    branches = Branch.objects.filter(business=business, is_active=True)

    context = {
        'day_rows': day_rows[::-1], # latest first
        'total_expected': total_expected,
        'total_banked': total_banked,
        'total_variance': total_variance,
        'start_date': start_str,
        'end_date': end_str,
        'branches': branches,
        'selected_branch': branch,
    }
    return render(request, 'pos/banking/reports/daily_banking_summary.html', context)


@business_required
def report_unbanked_funds(request, slug=None):
    """Un-Banked Funds Report: Real-time calculation of cash collected awaiting physical banking."""
    business = request.business
    today = timezone.localdate()
    branches = Branch.objects.filter(business=business, is_active=True)

    branch_summaries = []
    overall_unbanked = Decimal('0.00')
    overall_collected = Decimal('0.00')
    overall_banked = Decimal('0.00')

    for b in branches:
        res = BankingCalculationService.calculate_unbanked_funds(business, today, b)
        branch_summaries.append({
            'branch': b,
            'collected': res['total_cash_collected'],
            'banked': res['total_cash_banked'],
            'unbanked': res['unbanked_amount'],
        })
        overall_collected += res['total_cash_collected']
        overall_banked += res['total_cash_banked']
        overall_unbanked += res['unbanked_amount']

    # Pending in-transit deposits
    in_transit_records = BankingRecord.objects.filter(
        business=business, status='pending'
    ).select_related('bank_account', 'branch', 'deposited_by')

    context = {
        'as_of_date': today,
        'branch_summaries': branch_summaries,
        'overall_collected': overall_collected,
        'overall_banked': overall_banked,
        'overall_unbanked': overall_unbanked,
        'in_transit_records': in_transit_records,
    }
    return render(request, 'pos/banking/reports/unbanked_funds_report.html', context)


@business_required
def report_bank_reconciliation_statement(request, slug=None):
    """Classic 4-Part Bank Reconciliation Statement (Book Balance vs. Bank Statement Closing Balance)."""
    business = request.business
    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    account_id = request.GET.get('bank_account')
    as_of_str = request.GET.get('as_of_date') or timezone.localdate().isoformat()

    try:
        as_of_date = datetime.strptime(as_of_str, '%Y-%m-%d').date()
    except ValueError:
        as_of_date = timezone.localdate()

    selected_account = None
    if account_id:
        selected_account = bank_accounts.filter(id=account_id).first()
    if not selected_account and bank_accounts.exists():
        selected_account = bank_accounts.first()

    recon_data = None
    if selected_account:
        recon_data = ReconciliationEngine.get_reconciliation_statement(business, selected_account, as_of_date)

    context = {
        'bank_accounts': bank_accounts,
        'selected_account': selected_account,
        'as_of_date': as_of_date.isoformat(),
        'recon': recon_data,
    }
    return render(request, 'pos/banking/reports/reconciliation_statement.html', context)


@business_required
def report_variance_discrepancy(request, slug=None):
    """Variance & Discrepancy Report: Audit trail of all short/over banked deposits with notes."""
    business = request.business
    qs = BankingRecord.objects.filter(
        business=business
    ).exclude(variance_amount=Decimal('0.00')).select_related(
        'bank_account', 'branch', 'deposited_by', 'reconciled_by'
    ).order_by('-deposit_date')

    total_negative = qs.filter(variance_amount__lt=0).aggregate(t=Sum('variance_amount'))['t'] or Decimal('0.00')
    total_positive = qs.filter(variance_amount__gt=0).aggregate(t=Sum('variance_amount'))['t'] or Decimal('0.00')

    context = {
        'discrepancies': qs,
        'total_short': abs(total_negative),
        'total_over': total_positive,
        'net_variance': total_positive + total_negative,
    }
    return render(request, 'pos/banking/reports/variance_report.html', context)


@business_required
def report_aging_unmatched(request, slug=None):
    """Aging of Unmatched Deposits: Deposits banked > X days ago with no statement match."""
    business = request.business
    today = timezone.localdate()

    unmatched_records = BankingRecord.objects.filter(
        business=business,
        status__in=['banked', 'pending']
    ).select_related('bank_account', 'branch', 'deposited_by')

    aging_buckets = {
        '0_to_3': [],
        '4_to_7': [],
        '8_to_14': [],
        '15_plus': [],
    }

    for rec in unmatched_records:
        age_days = (today - rec.deposit_date).days
        item = {'record': rec, 'age_days': age_days}
        if age_days <= 3:
            aging_buckets['0_to_3'].append(item)
        elif age_days <= 7:
            aging_buckets['4_to_7'].append(item)
        elif age_days <= 14:
            aging_buckets['8_to_14'].append(item)
        else:
            aging_buckets['15_plus'].append(item)

    context = {
        'today': today,
        'total_unmatched_count': unmatched_records.count(),
        'total_unmatched_amount': unmatched_records.aggregate(t=Sum('deposited_amount'))['t'] or Decimal('0.00'),
        'aging_buckets': aging_buckets,
    }
    return render(request, 'pos/banking/reports/aging_unmatched_report.html', context)
