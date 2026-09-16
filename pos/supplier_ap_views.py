"""
Supplier Accounts Payable, Outgoing Payments & Credit Notes Views for Marid POS
"""

import json
from decimal import Decimal
from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
from django.core.paginator import Paginator

from .models import (
    Business, Supplier, SupplierInvoice, SupplierPayment, PaymentAllocation,
    SupplierCredit, SupplierCreditApplication, SupplierRefund, BankAccount,
    BankStatementLine, Purchase, GoodsReceivedNote, GoodsReturnedNote,
    ActivityLog, POSSession
)
from .supplier_ap_services import (
    SupplierInvoiceService, SupplierPaymentAPService, SupplierCreditService,
    SupplierReportService
)


# ==================== 1. SUPPLIER INVOICES (AP BILLS) ====================

@login_required
def supplier_invoice_list(request, slug=None):
    """List all Accounts Payable supplier invoices"""
    business = request.business
    status = request.GET.get('status', '')
    supplier_id = request.GET.get('supplier_id', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    search_query = request.GET.get('q', '').strip()

    invoices_qs = SupplierInvoice.objects.filter(business=business).select_related('supplier', 'purchase')

    if status == 'overdue':
        invoices_qs = invoices_qs.filter(
            due_date__lt=timezone.now().date(),
            status__in=['unpaid', 'partially_paid']
        )
    elif status:
        invoices_qs = invoices_qs.filter(status=status)

    if supplier_id:
        invoices_qs = invoices_qs.filter(supplier_id=supplier_id)
    if start_date:
        invoices_qs = invoices_qs.filter(invoice_date__gte=start_date)
    if end_date:
        invoices_qs = invoices_qs.filter(invoice_date__lte=end_date)
    if search_query:
        invoices_qs = invoices_qs.filter(
            Q(invoice_number__icontains=search_query) |
            Q(supplier__name__icontains=search_query) |
            Q(notes__icontains=search_query)
        )

    # Metrics
    all_invoices = SupplierInvoice.objects.filter(business=business)
    total_invoiced = all_invoices.exclude(status='cancelled').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    
    unpaid_qs = all_invoices.filter(status__in=['unpaid', 'partially_paid', 'disputed'])
    total_outstanding = sum(inv.remaining_balance() for inv in unpaid_qs)
    overdue_count = sum(1 for inv in unpaid_qs if inv.is_overdue())
    paid_count = all_invoices.filter(status='paid').count()

    paginator = Paginator(invoices_qs, 25)
    page_number = request.GET.get('page')
    invoices = paginator.get_page(page_number)

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')

    context = {
        'invoices': invoices,
        'suppliers': suppliers,
        'status': status,
        'supplier_id': supplier_id,
        'start_date': start_date,
        'end_date': end_date,
        'search_query': search_query,
        'total_invoiced': total_invoiced,
        'total_outstanding': total_outstanding,
        'overdue_count': overdue_count,
        'paid_count': paid_count,
    }
    return render(request, 'pos/supplier_ap/invoice_list.html', context)


@login_required
def supplier_invoice_create(request, slug=None):
    """Create a new Accounts Payable supplier invoice"""
    business = request.business

    if request.method == 'POST':
        supplier_id = request.POST.get('supplier_id')
        invoice_number = request.POST.get('invoice_number', '').strip()
        invoice_date_str = request.POST.get('invoice_date')
        due_date_str = request.POST.get('due_date')
        amount_str = request.POST.get('amount', '0.00')
        subtotal_str = request.POST.get('subtotal', '0.00')
        tax_str = request.POST.get('tax_amount', '0.00')
        discount_str = request.POST.get('discount_amount', '0.00')
        purchase_id = request.POST.get('purchase_id')
        notes = request.POST.get('notes', '')
        attachment = request.FILES.get('attachment')

        try:
            supplier = get_object_or_404(Supplier, id=supplier_id, business=business)
            amount = Decimal(amount_str)
            subtotal = Decimal(subtotal_str) if subtotal_str else amount
            tax_amount = Decimal(tax_str) if tax_str else Decimal('0.00')
            discount_amount = Decimal(discount_str) if discount_str else Decimal('0.00')

            inv_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date() if invoice_date_str else timezone.now().date()
            due_d = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else (inv_date + timedelta(days=30))

            purchase = Purchase.objects.filter(id=purchase_id, business=business).first() if purchase_id else None

            invoice = SupplierInvoiceService.create_invoice(
                business=business,
                supplier=supplier,
                invoice_number=invoice_number,
                invoice_date=inv_date,
                due_date=due_d,
                amount=amount,
                subtotal=subtotal,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                purchase=purchase,
                attachment=attachment,
                notes=notes,
                created_by=request.user
            )

            messages.success(request, f"Supplier Invoice {invoice.invoice_number} for {supplier.name} (KES {invoice.amount:,.2f}) recorded successfully!")
            return redirect('supplier_invoice_detail', invoice_id=invoice.id)

        except Exception as e:
            messages.error(request, f"Error creating supplier invoice: {str(e)}")

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')
    purchases = Purchase.objects.filter(business=business, status__in=['received', 'partially_received', 'closed']).order_by('-date')[:50]

    context = {
        'suppliers': suppliers,
        'purchases': purchases,
        'today': timezone.now().date().isoformat(),
        'default_due': (timezone.now().date() + timedelta(days=30)).isoformat(),
    }
    return render(request, 'pos/supplier_ap/invoice_form.html', context)


@login_required
def supplier_invoice_detail(request, slug=None, invoice_id=None):
    """View details of a supplier invoice with payments and credits applied"""
    business = request.business
    invoice = get_object_or_404(SupplierInvoice, id=invoice_id, business=business)

    allocations = invoice.payment_allocations.select_related('payment', 'payment__created_by').order_by('-created_at')
    credits_applied = invoice.credit_applications.select_related('credit', 'applied_by').order_by('-applied_at')

    # Available credits from same supplier that can be applied
    available_credits = SupplierCredit.objects.filter(
        business=business,
        supplier=invoice.supplier,
        status__in=['approved_by_supplier', 'partially_resolved']
    ).exclude(id__in=credits_applied.values_list('credit_id', flat=True))

    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    context = {
        'invoice': invoice,
        'allocations': allocations,
        'credits_applied': credits_applied,
        'available_credits': available_credits,
        'bank_accounts': bank_accounts,
        'today': timezone.now().date().isoformat(),
    }
    return render(request, 'pos/supplier_ap/invoice_detail.html', context)


# ==================== 2. SUPPLIER PAYMENTS ====================

@login_required
def supplier_payment_list(request, slug=None):
    """List all outgoing supplier payments"""
    business = request.business
    status = request.GET.get('status', '')
    supplier_id = request.GET.get('supplier_id', '')
    source_type = request.GET.get('source_type', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    payments_qs = SupplierPayment.objects.filter(business=business).select_related('supplier', 'bank_account', 'created_by')

    if status:
        payments_qs = payments_qs.filter(status=status)
    if supplier_id:
        payments_qs = payments_qs.filter(supplier_id=supplier_id)
    if source_type:
        payments_qs = payments_qs.filter(source_type=source_type)
    if start_date:
        payments_qs = payments_qs.filter(payment_date__gte=start_date)
    if end_date:
        payments_qs = payments_qs.filter(payment_date__lte=end_date)

    all_payments = SupplierPayment.objects.filter(business=business, is_reversed=False)
    total_paid = all_payments.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    total_cleared = all_payments.filter(status='cleared').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    total_in_transit = all_payments.filter(status__in=['sent', 'pending']).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    paginator = Paginator(payments_qs, 25)
    page_number = request.GET.get('page')
    payments = paginator.get_page(page_number)

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')

    context = {
        'payments': payments,
        'suppliers': suppliers,
        'status': status,
        'supplier_id': supplier_id,
        'source_type': source_type,
        'start_date': start_date,
        'end_date': end_date,
        'total_paid': total_paid,
        'total_cleared': total_cleared,
        'total_in_transit': total_in_transit,
    }
    return render(request, 'pos/supplier_ap/payment_list.html', context)


@login_required
def supplier_payment_create(request, slug=None):
    """Record an outgoing payment to a supplier"""
    business = request.business

    if request.method == 'POST':
        supplier_id = request.POST.get('supplier_id')
        amount_str = request.POST.get('amount', '0.00')
        payment_date_str = request.POST.get('payment_date')
        source_type = request.POST.get('source_type', 'bank_account')
        payment_method_type = request.POST.get('payment_method_type', 'bank_transfer')
        bank_account_id = request.POST.get('bank_account_id')
        reference_number = request.POST.get('reference_number', '').strip()
        notes = request.POST.get('notes', '').strip()

        try:
            supplier = get_object_or_404(Supplier, id=supplier_id, business=business)
            amount = Decimal(amount_str)
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date() if payment_date_str else timezone.now().date()

            bank_account = BankAccount.objects.filter(id=bank_account_id, business=business).first() if bank_account_id else None

            # Check for specific manual invoice allocations in form
            allocations = []
            for key, val in request.POST.items():
                if key.startswith('alloc_invoice_') and val:
                    inv_id = key.replace('alloc_invoice_', '')
                    alloc_amt = Decimal(val)
                    if alloc_amt > 0:
                        inv = SupplierInvoice.objects.filter(id=inv_id, supplier=supplier, business=business).first()
                        if inv:
                            allocations.append({'invoice': inv, 'amount': alloc_amt})

            # Check POS Session if cash drawer payout
            pos_session = POSSession.objects.filter(
                business=business,
                status='open'
            ).filter(
                Q(cashier=request.user) | Q(opened_by=request.user)
            ).first()

            payment = SupplierPaymentAPService.record_payment(
                business=business,
                supplier=supplier,
                amount=amount,
                payment_date=payment_date,
                payment_method_type=payment_method_type,
                source_type=source_type,
                bank_account=bank_account,
                reference_number=reference_number,
                authorized_by=request.user,
                created_by=request.user,
                notes=notes,
                allocations=allocations if allocations else None,
                pos_session=pos_session
            )

            messages.success(request, f"Supplier Payment {payment.payment_number} (KES {payment.amount:,.2f}) recorded successfully!")
            return redirect('supplier_payment_detail', payment_id=payment.id)

        except Exception as e:
            messages.error(request, f"Error recording supplier payment: {str(e)}")

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')
    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    preselect_supplier_id = request.GET.get('supplier_id')
    preselect_invoice_id = request.GET.get('invoice_id')

    context = {
        'suppliers': suppliers,
        'bank_accounts': bank_accounts,
        'preselect_supplier_id': preselect_supplier_id,
        'preselect_invoice_id': preselect_invoice_id,
        'today': timezone.now().date().isoformat(),
    }
    return render(request, 'pos/supplier_ap/payment_form.html', context)


@login_required
def supplier_payment_detail(request, slug=None, payment_id=None):
    """View payment voucher details, allocations, and bank match status"""
    business = request.business
    payment = get_object_or_404(SupplierPayment, id=payment_id, business=business)
    allocations = payment.allocations.select_related('invoice', 'purchase').all()

    context = {
        'payment': payment,
        'allocations': allocations,
    }
    return render(request, 'pos/supplier_ap/payment_detail.html', context)


@login_required
def supplier_payment_reverse(request, slug=None, payment_id=None):
    """Reverse a supplier payment with mandatory explanation"""
    business = request.business
    payment = get_object_or_404(SupplierPayment, id=payment_id, business=business)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, "A reason for payment reversal is required.")
            return redirect('supplier_payment_detail', payment_id=payment.id)

        try:
            SupplierPaymentAPService.reverse_payment(
                payment=payment,
                user=request.user,
                reason=reason
            )
            messages.success(request, f"Supplier Payment {payment.payment_number} has been reversed successfully.")
        except Exception as e:
            messages.error(request, f"Error reversing payment: {str(e)}")

    return redirect('supplier_payment_detail', payment_id=payment.id)


@login_required
def supplier_unpaid_invoices_api(request, slug=None):
    """JSON API to fetch open unpaid invoices and available credit claims for a supplier"""
    supplier_id = request.GET.get('supplier_id')
    if not supplier_id:
        return JsonResponse({'error': 'supplier_id is required'}, status=400)

    invoices = SupplierInvoice.objects.filter(
        business=request.business,
        supplier_id=supplier_id,
        status__in=['unpaid', 'partially_paid']
    ).order_by('due_date', 'invoice_date')

    invoices_data = []
    for inv in invoices:
        rem = inv.remaining_balance()
        if rem > Decimal('0.00'):
            invoices_data.append({
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'invoice_date': inv.invoice_date.isoformat(),
                'due_date': inv.due_date.isoformat(),
                'amount': float(inv.amount),
                'remaining_balance': float(rem),
                'is_overdue': inv.is_overdue(),
                'days_overdue': inv.days_overdue() if inv.is_overdue() else 0
            })

    # Fetch approved/open credit notes for this supplier
    credits = SupplierCredit.objects.filter(
        business=request.business,
        supplier_id=supplier_id,
        status__in=['approved_by_supplier', 'partially_resolved']
    ).order_by('date_raised')

    credits_data = []
    total_available_credit = Decimal('0.00')
    for cr in credits:
        rem_cr = cr.remaining_credit()
        if rem_cr > Decimal('0.00'):
            total_available_credit += rem_cr
            credits_data.append({
                'id': cr.id,
                'credit_number': cr.credit_number,
                'date_raised': cr.date_raised.isoformat(),
                'reason': cr.get_reason_display(),
                'amount': float(cr.amount),
                'remaining_credit': float(rem_cr)
            })

    return JsonResponse({
        'invoices': invoices_data,
        'credits': credits_data,
        'total_available_credits': float(total_available_credit)
    })


# ==================== 3. SUPPLIER CREDITS & REFUNDS ====================

@login_required
def supplier_credit_list(request, slug=None):
    """List all supplier credit notes and claims"""
    business = request.business
    status = request.GET.get('status', '')
    supplier_id = request.GET.get('supplier_id', '')

    credits_qs = SupplierCredit.objects.filter(business=business).select_related('supplier', 'related_invoice')

    if status:
        credits_qs = credits_qs.filter(status=status)
    if supplier_id:
        credits_qs = credits_qs.filter(supplier_id=supplier_id)

    total_credits = SupplierCredit.objects.filter(business=business).exclude(status='rejected').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    unresolved_credits = sum(cr.remaining_credit() for cr in SupplierCredit.objects.filter(business=business, status__in=['pending_approval', 'approved_by_supplier', 'partially_resolved']))

    paginator = Paginator(credits_qs, 25)
    page_number = request.GET.get('page')
    credits = paginator.get_page(page_number)

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')

    context = {
        'credits': credits,
        'suppliers': suppliers,
        'status': status,
        'supplier_id': supplier_id,
        'total_credits': total_credits,
        'unresolved_credits': unresolved_credits,
    }
    return render(request, 'pos/supplier_ap/credit_list.html', context)


@login_required
def supplier_credit_create(request, slug=None):
    """Raise a credit claim against a supplier"""
    business = request.business

    if request.method == 'POST':
        supplier_id = request.POST.get('supplier_id')
        amount_str = request.POST.get('amount', '0.00')
        reason = request.POST.get('reason', 'return')
        date_raised_str = request.POST.get('date_raised')
        related_invoice_id = request.POST.get('related_invoice_id')
        notes = request.POST.get('notes', '').strip()
        attachment = request.FILES.get('attachment')

        try:
            supplier = get_object_or_404(Supplier, id=supplier_id, business=business)
            amount = Decimal(amount_str)
            date_raised = datetime.strptime(date_raised_str, '%Y-%m-%d').date() if date_raised_str else timezone.now().date()

            related_inv = SupplierInvoice.objects.filter(id=related_invoice_id, supplier=supplier, business=business).first() if related_invoice_id else None

            credit = SupplierCreditService.raise_credit(
                business=business,
                supplier=supplier,
                amount=amount,
                reason=reason,
                date_raised=date_raised,
                related_invoice=related_inv,
                notes=notes,
                attachment=attachment,
                authorized_by=request.user,
                created_by=request.user
            )

            messages.success(request, f"Supplier Credit {credit.credit_number} (KES {credit.amount:,.2f}) raised successfully!")
            return redirect('supplier_credit_detail', credit_id=credit.id)

        except Exception as e:
            messages.error(request, f"Error raising supplier credit: {str(e)}")

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')
    context = {
        'suppliers': suppliers,
        'today': timezone.now().date().isoformat(),
    }
    return render(request, 'pos/supplier_ap/credit_form.html', context)


@login_required
def supplier_credit_detail(request, slug=None, credit_id=None):
    """View details of a supplier credit with applied invoices and refunds history"""
    business = request.business
    credit = get_object_or_404(SupplierCredit, id=credit_id, business=business)

    applications = credit.applications.select_related('invoice', 'applied_by').all()
    refunds = credit.refunds.select_related('destination_account', 'received_by').all()

    # Open invoices from same supplier that can be offset
    open_invoices = SupplierInvoice.objects.filter(
        business=business,
        supplier=credit.supplier,
        status__in=['unpaid', 'partially_paid']
    ).order_by('due_date')

    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    context = {
        'credit': credit,
        'applications': applications,
        'refunds': refunds,
        'open_invoices': open_invoices,
        'bank_accounts': bank_accounts,
        'today': timezone.now().date().isoformat(),
    }
    return render(request, 'pos/supplier_ap/credit_detail.html', context)


@login_required
def supplier_credit_apply(request, slug=None, credit_id=None):
    """Apply a supplier credit to offset an open invoice"""
    business = request.business
    credit = get_object_or_404(SupplierCredit, id=credit_id, business=business)

    if request.method == 'POST':
        invoice_id = request.POST.get('invoice_id')
        amount_str = request.POST.get('amount', '0.00')
        notes = request.POST.get('notes', '')

        try:
            invoice = get_object_or_404(SupplierInvoice, id=invoice_id, business=business, supplier=credit.supplier)
            amount = Decimal(amount_str)

            SupplierCreditService.apply_credit_to_invoice(
                credit=credit,
                invoice=invoice,
                amount=amount,
                user=request.user,
                notes=notes
            )
            messages.success(request, f"Credit of KES {amount:,.2f} applied to Invoice {invoice.invoice_number} successfully.")
        except Exception as e:
            messages.error(request, f"Error applying credit: {str(e)}")

    return redirect('supplier_credit_detail', credit_id=credit.id)


@login_required
def supplier_credit_refund(request, slug=None, credit_id=None):
    """Record incoming cash/bank refund from supplier settling a credit note"""
    business = request.business
    credit = get_object_or_404(SupplierCredit, id=credit_id, business=business)

    if request.method == 'POST':
        amount_str = request.POST.get('amount', '0.00')
        received_date_str = request.POST.get('received_date')
        received_via = request.POST.get('received_via', 'bank_transfer')
        destination_account_id = request.POST.get('destination_account_id')
        destination_type = request.POST.get('destination_type', 'bank_account')
        reference = request.POST.get('reference', '').strip()
        notes = request.POST.get('notes', '')

        try:
            amount = Decimal(amount_str)
            received_date = datetime.strptime(received_date_str, '%Y-%m-%d').date() if received_date_str else timezone.now().date()
            dest_acc = BankAccount.objects.filter(id=destination_account_id, business=business).first() if destination_account_id else None

            refund = SupplierCreditService.record_refund(
                credit=credit,
                amount=amount,
                received_date=received_date,
                received_via=received_via,
                destination_account=dest_acc,
                destination_type=destination_type,
                reference=reference,
                user=request.user,
                notes=notes
            )
            messages.success(request, f"Supplier refund {refund.refund_number} of KES {refund.amount:,.2f} recorded successfully.")
        except Exception as e:
            messages.error(request, f"Error recording refund: {str(e)}")

    return redirect('supplier_credit_detail', credit_id=credit.id)


# ==================== 4. FINANCIAL & AUDIT REPORTS ====================

@login_required
def report_ap_aging(request, slug=None):
    """Accounts Payable Aging Report"""
    business = request.business
    as_of_str = request.GET.get('as_of_date')
    supplier_id = request.GET.get('supplier_id')

    as_of_date = datetime.strptime(as_of_str, '%Y-%m-%d').date() if as_of_str else timezone.now().date()
    report_data = SupplierReportService.get_ap_aging_report(
        business=business,
        as_of_date=as_of_date,
        supplier_id=supplier_id
    )

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')

    context = {
        'report': report_data,
        'suppliers': suppliers,
        'selected_supplier_id': supplier_id,
        'as_of_date': as_of_date.isoformat(),
    }
    return render(request, 'pos/supplier_ap/reports/ap_aging.html', context)


@login_required
def report_supplier_statement(request, slug=None):
    """Full Statement of Account for a Supplier"""
    business = request.business
    supplier_id = request.GET.get('supplier_id')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')
    statement_data = None
    selected_supplier = None

    if supplier_id:
        selected_supplier = get_object_or_404(Supplier, id=supplier_id, business=business)
        start_d = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_d = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else timezone.now().date()

        statement_data = SupplierReportService.get_supplier_statement(
            supplier=selected_supplier,
            start_date=start_d,
            end_date=end_d
        )

    context = {
        'suppliers': suppliers,
        'selected_supplier': selected_supplier,
        'statement': statement_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    return render(request, 'pos/supplier_ap/reports/supplier_statement.html', context)


@login_required
def report_outstanding_credits(request, slug=None):
    """Schedule of unresolved supplier credits (money/claims owed to business)"""
    business = request.business
    supplier_id = request.GET.get('supplier_id')

    report_data = SupplierReportService.get_outstanding_credits_report(
        business=business,
        supplier_id=supplier_id
    )
    suppliers = Supplier.objects.filter(business=business, is_active=True).order_by('name')

    context = {
        'report': report_data,
        'suppliers': suppliers,
        'selected_supplier_id': supplier_id,
    }
    return render(request, 'pos/supplier_ap/reports/outstanding_credits.html', context)


@login_required
def report_outstanding_cheques(request, slug=None):
    """Schedule of sent payments not yet cleared on bank statements (payments in transit)"""
    business = request.business
    bank_account_id = request.GET.get('bank_account_id')

    report_data = SupplierReportService.get_outstanding_cheques_report(
        business=business,
        bank_account_id=bank_account_id
    )
    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    context = {
        'report': report_data,
        'bank_accounts': bank_accounts,
        'selected_bank_account_id': bank_account_id,
    }
    return render(request, 'pos/supplier_ap/reports/outstanding_cheques.html', context)


@login_required
def report_unmatched_statement_lines(request, slug=None):
    """Master Two-Way Bank Statement Unmatched Lines Audit"""
    business = request.business
    bank_account_id = request.GET.get('bank_account_id')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    start_d = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
    end_d = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

    report_data = SupplierReportService.get_unmatched_statement_lines_report(
        business=business,
        bank_account_id=bank_account_id,
        start_date=start_d,
        end_date=end_d
    )
    bank_accounts = BankAccount.objects.filter(business=business, is_active=True)

    context = {
        'report': report_data,
        'bank_accounts': bank_accounts,
        'selected_bank_account_id': bank_account_id,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    return render(request, 'pos/supplier_ap/reports/unmatched_statement_lines.html', context)
