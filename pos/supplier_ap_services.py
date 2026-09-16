"""
Supplier Accounts Payable & Financial Control Services for Marid POS
Handles:
- Accrual-based Supplier Invoices (AP Bills)
- Multi-Source Supplier Payments (Bank EFT, Cheques, Till Cash Drawer, Petty Cash)
- Automatic Till Drawer Cash Paid-Out Integration
- Supplier Credits (Debit Notes / Claims) & Invoice Offsetting
- Supplier Refunds (Incoming Money from Supplier)
- P&L & COGS Cost Netting Integrity
- AP Aging, Supplier Statements, and Transit Reconciliations
"""

from decimal import Decimal
from datetime import datetime, date, timedelta
from django.db import transaction
from django.db.models import Sum, F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import (
    Business, Supplier, SupplierInvoice, SupplierPayment, PaymentAllocation,
    SupplierCredit, SupplierCreditApplication, SupplierRefund, BankAccount,
    BankStatementLine, Purchase, GoodsReceivedNote, GoodsReturnedNote,
    ExpenseCategory, CashPaidOut, ActivityLog
)


class SupplierInvoiceService:
    """Business logic for managing Accounts Payable supplier bills and invoices"""

    @staticmethod
    @transaction.atomic
    def create_invoice(business, supplier, invoice_number, invoice_date, due_date,
                       amount, subtotal=None, tax_amount=None, discount_amount=None,
                       purchase=None, goods_received_note=None, attachment=None,
                       notes='', created_by=None):
        """
        Creates an Accounts Payable invoice.
        Recognizes the expense liability at the invoice date (accrual basis).
        """
        if amount <= Decimal('0.00'):
            raise ValidationError("Invoice amount must be greater than zero.")

        if due_date < invoice_date:
            raise ValidationError("Due date cannot precede invoice date.")

        if SupplierInvoice.objects.filter(business=business, supplier=supplier, invoice_number__iexact=invoice_number.strip()).exists():
            raise ValidationError(f"Invoice number '{invoice_number}' already exists for supplier {supplier.name}.")

        subtotal_val = subtotal if subtotal is not None else amount
        tax_val = tax_amount if tax_amount is not None else Decimal('0.00')
        disc_val = discount_amount if discount_amount is not None else Decimal('0.00')

        invoice = SupplierInvoice.objects.create(
            business=business,
            supplier=supplier,
            invoice_number=invoice_number.strip(),
            invoice_date=invoice_date,
            due_date=due_date,
            amount=amount,
            subtotal=subtotal_val,
            tax_amount=tax_val,
            discount_amount=disc_val,
            status='unpaid',
            purchase=purchase,
            goods_received_note=goods_received_note,
            attachment=attachment,
            notes=notes,
            created_by=created_by
        )

        ActivityLog.log_activity(
            user=created_by,
            action_type='create',
            description=f"Created AP Supplier Invoice {invoice.invoice_number} for {supplier.name} (KES {invoice.amount:,.2f})",
            model_name='SupplierInvoice',
            object_id=invoice.id,
            business=business
        )

        return invoice

    @staticmethod
    @transaction.atomic
    def auto_create_from_purchase(purchase, user, invoice_number=None, due_date=None):
        """Generates a SupplierInvoice from a received Purchase Order"""
        inv_num = invoice_number or f"INV-{purchase.purchase_number}"
        inv_date = purchase.received_date.date() if purchase.received_date else purchase.date.date()
        due_d = due_date or (inv_date + timedelta(days=30))

        return SupplierInvoiceService.create_invoice(
            business=purchase.business,
            supplier=purchase.supplier,
            invoice_number=inv_num,
            invoice_date=inv_date,
            due_date=due_d,
            amount=purchase.total_amount,
            subtotal=purchase.subtotal,
            tax_amount=purchase.tax_amount,
            discount_amount=purchase.discount_amount,
            purchase=purchase,
            notes=f"Auto-generated from PO {purchase.purchase_number}",
            created_by=user
        )

    @staticmethod
    def recalculate_invoice_status(invoice):
        """Refreshes status according to payment and credit applications"""
        return invoice.recalculate_status()


class SupplierPaymentAPService:
    """Business logic for recording outgoing supplier payments with multi-source funding"""

    @staticmethod
    @transaction.atomic
    def record_payment(business, supplier, amount, payment_date, payment_method_type='bank_transfer',
                       source_type='bank_account', bank_account=None, reference_number='',
                       authorized_by=None, created_by=None, notes='', allocations=None,
                       pos_session=None):
        """
        Records an outgoing payment to a supplier.
        Supports Bank Account, Cheque, Cash Drawer (Till), or Petty Cash.
        """
        if amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be greater than zero.")

        if source_type == 'bank_account' and not bank_account:
            # Fallback to default bank account if none provided
            bank_account = BankAccount.objects.filter(business=business, is_active=True, is_default=True).first()
            if not bank_account:
                bank_account = BankAccount.objects.filter(business=business, is_active=True).first()
            if not bank_account:
                raise ValidationError("A bank account must be selected for bank payments.")

        # If paying via cash drawer or petty cash, handle Till Cash Paid-Out integration
        linked_cash_paid_out = None
        if source_type in ('cash_drawer', 'petty_cash'):
            # Fetch or create "Supplier Payment" expense category
            category, _ = ExpenseCategory.objects.get_or_create(
                business=business,
                name="Supplier Payment",
                defaults={
                    'description': 'Direct cash payments made to suppliers for goods/services',
                    'requires_manager_approval_above': Decimal('1000000.00')
                }
            )

            from .cash_paid_out_services import CashPaidOutService
            try:
                linked_cash_paid_out = CashPaidOutService.record_paid_out(
                    business=business,
                    requested_by=created_by or authorized_by,
                    category=category,
                    amount=amount,
                    payee=supplier.name,
                    description=f"Supplier Payment for {supplier.name} ({reference_number or 'Cash Settlement'})",
                    receipt_reference=reference_number or f"SUPP-{supplier.id}",
                    session=pos_session,
                    is_petty_cash_fund=(source_type == 'petty_cash'),
                    notes=notes
                )
                if authorized_by and linked_cash_paid_out:
                    linked_cash_paid_out.authorized_by = authorized_by
                    linked_cash_paid_out.save(update_fields=['authorized_by'])
            except Exception as e:
                raise ValidationError(f"Till Cash Paid-Out failed: {str(e)}")

        payment = SupplierPayment.objects.create(
            business=business,
            supplier=supplier,
            payment_date=payment_date,
            amount=amount,
            payment_method_type=payment_method_type,
            source_type=source_type,
            bank_account=bank_account if source_type == 'bank_account' else None,
            cash_paid_out=linked_cash_paid_out,
            reference_number=reference_number,
            status='cleared' if source_type in ('cash_drawer', 'petty_cash') else ('sent' if payment_method_type != 'pending' else 'pending'),
            authorized_by=authorized_by,
            created_by=created_by,
            notes=notes
        )

        # Allocate payment across invoices
        if allocations:
            total_allocated = Decimal('0.00')
            for item in allocations:
                inv = item.get('invoice')
                purch = item.get('purchase')
                alloc_amt = Decimal(str(item.get('amount', '0.00')))

                if alloc_amt <= Decimal('0.00'):
                    continue

                if inv:
                    rem = inv.remaining_balance()
                    if alloc_amt > rem:
                        alloc_amt = rem

                    PaymentAllocation.objects.create(
                        payment=payment,
                        invoice=inv,
                        amount=alloc_amt
                    )
                    inv.recalculate_status()
                    total_allocated += alloc_amt
                elif purch:
                    rem = purch.remaining_balance()
                    if alloc_amt > rem:
                        alloc_amt = rem

                    PaymentAllocation.objects.create(
                        payment=payment,
                        purchase=purch,
                        amount=alloc_amt
                    )
                    total_allocated += alloc_amt

            if total_allocated > amount:
                raise ValidationError("Total allocated amount exceeds the payment amount.")
        else:
            # Auto-allocate using FIFO across unpaid invoices (and then unpaid purchases)
            SupplierPaymentAPService._auto_allocate_fifo(payment)

        ActivityLog.log_activity(
            user=created_by,
            action_type='create',
            description=f"Recorded Supplier Payment {payment.payment_number} to {supplier.name} via {payment.get_source_type_display()} (KES {payment.amount:,.2f})",
            model_name='SupplierPayment',
            object_id=payment.id,
            business=business
        )

        return payment

    @staticmethod
    def _auto_allocate_fifo(payment):
        """Automatically allocates payment amount to oldest unpaid invoices first, then legacy purchases"""
        remaining_funds = payment.amount

        # 1. Unpaid Invoices
        unpaid_invoices = SupplierInvoice.objects.filter(
            business=payment.business,
            supplier=payment.supplier,
            status__in=['unpaid', 'partially_paid']
        ).order_by('invoice_date', 'due_date', 'id')

        for inv in unpaid_invoices:
            if remaining_funds <= Decimal('0.00'):
                break
            rem = inv.remaining_balance()
            if rem <= Decimal('0.00'):
                inv.recalculate_status()
                continue

            alloc_amt = min(remaining_funds, rem)
            PaymentAllocation.objects.create(
                payment=payment,
                invoice=inv,
                amount=alloc_amt
            )
            inv.recalculate_status()
            remaining_funds -= alloc_amt

        # 2. Fallback to legacy Purchases if still remaining funds
        if remaining_funds > Decimal('0.00'):
            unpaid_purchases = Purchase.objects.filter(
                business=payment.business,
                supplier=payment.supplier,
                status__in=['received', 'partially_received', 'closed']
            ).order_by('date', 'id')

            for p in unpaid_purchases:
                if remaining_funds <= Decimal('0.00'):
                    break
                rem = p.remaining_balance()
                if rem <= Decimal('0.00'):
                    continue

                alloc_amt = min(remaining_funds, rem)
                PaymentAllocation.objects.create(
                    payment=payment,
                    purchase=p,
                    amount=alloc_amt
                )
                remaining_funds -= alloc_amt

    @staticmethod
    @transaction.atomic
    def reverse_payment(payment, user, reason=''):
        """Reverses a supplier payment and rolls back all allocations and linked payouts"""
        if payment.is_reversed:
            raise ValidationError("Payment is already reversed.")

        if payment.bank_statement_line:
            raise ValidationError("Payment is matched to a bank statement line. Please unmatch the statement line first.")

        # 1. Re-open invoices
        invoices_to_update = set()
        for alloc in payment.allocations.all():
            if alloc.invoice:
                invoices_to_update.add(alloc.invoice)

        payment.allocations.all().delete()

        for inv in invoices_to_update:
            inv.recalculate_status()

        # 2. If paid via cash drawer, reverse linked CashPaidOut
        if payment.cash_paid_out and not payment.cash_paid_out.is_reversed:
            cpo = payment.cash_paid_out
            cpo.is_reversed = True
            cpo.status = 'reversed'
            cpo.reversed_at = timezone.now()
            cpo.reversed_by = user
            cpo.reversal_reason = f"Reversed via Supplier Payment {payment.payment_number}: {reason}"
            if cpo.expense_entry:
                cpo.expense_entry.delete()
                cpo.expense_entry = None
            cpo.save()

        payment.is_reversed = True
        payment.status = 'reversed'
        payment.reversed_at = timezone.now()
        payment.reversed_by = user
        payment.reversal_reason = reason
        payment.save(update_fields=['is_reversed', 'status', 'reversed_at', 'reversed_by', 'reversal_reason', 'updated_at'])

        ActivityLog.log_activity(
            user=user,
            action_type='reversal',
            description=f"Reversed Supplier Payment {payment.payment_number} to {payment.supplier.name} (KES {payment.amount:,.2f}) | Reason: {reason}",
            model_name='SupplierPayment',
            object_id=payment.id,
            business=payment.business
        )

        return payment


class SupplierCreditService:
    """Business logic for raising supplier claims (credit/debit notes), invoice offsets, and supplier refunds"""

    @staticmethod
    @transaction.atomic
    def raise_credit(business, supplier, amount, reason='return', date_raised=None,
                     related_invoice=None, related_purchase=None, related_grn=None,
                     notes='', attachment=None, authorized_by=None, created_by=None):
        """Raises a claim/credit against a supplier"""
        if amount <= Decimal('0.00'):
            raise ValidationError("Credit note amount must be greater than zero.")

        d_raised = date_raised or timezone.now().date()

        credit = SupplierCredit.objects.create(
            business=business,
            supplier=supplier,
            related_invoice=related_invoice,
            related_purchase=related_purchase,
            related_grn=related_grn,
            amount=amount,
            allocated_amount=Decimal('0.00'),
            reason=reason,
            date_raised=d_raised,
            status='approved_by_supplier' if authorized_by else 'pending_approval',
            resolution_type='unresolved',
            notes=notes,
            attachment=attachment,
            authorized_by=authorized_by,
            created_by=created_by
        )

        ActivityLog.log_activity(
            user=created_by,
            action_type='create',
            description=f"Raised Supplier Credit {credit.credit_number} for {supplier.name} (KES {credit.amount:,.2f}) - Reason: {credit.get_reason_display()}",
            model_name='SupplierCredit',
            object_id=credit.id,
            business=business
        )

        return credit

    @staticmethod
    @transaction.atomic
    def apply_credit_to_invoice(credit, invoice, amount, user, notes=''):
        """Applies a supplier credit note to reduce/offset a supplier invoice"""
        if amount <= Decimal('0.00'):
            raise ValidationError("Applied credit amount must be greater than zero.")

        if credit.supplier != invoice.supplier:
            raise ValidationError("Credit note and invoice must belong to the same supplier.")

        rem_credit = credit.remaining_credit()
        if amount > rem_credit:
            raise ValidationError(f"Applied amount (KES {amount:,.2f}) exceeds available credit (KES {rem_credit:,.2f}).")

        rem_inv = invoice.remaining_balance()
        if amount > rem_inv:
            raise ValidationError(f"Applied amount (KES {amount:,.2f}) exceeds invoice remaining balance (KES {rem_inv:,.2f}).")

        app = SupplierCreditApplication.objects.create(
            credit=credit,
            invoice=invoice,
            amount=amount,
            applied_by=user,
            notes=notes
        )

        credit.recalculate_resolution()
        invoice.recalculate_status()

        ActivityLog.log_activity(
            user=user,
            action_type='update',
            description=f"Applied Credit {credit.credit_number} (KES {amount:,.2f}) to Invoice {invoice.invoice_number}",
            model_name='SupplierCredit',
            object_id=credit.id,
            business=credit.business
        )

        return app

    @staticmethod
    @transaction.atomic
    def record_refund(credit, amount, received_date, received_via='bank_transfer',
                      destination_account=None, destination_type='bank_account',
                      reference='', user=None, notes=''):
        """Records incoming money returned by the supplier settling a credit note"""
        if amount <= Decimal('0.00'):
            raise ValidationError("Refund amount must be greater than zero.")

        rem_credit = credit.remaining_credit()
        if amount > rem_credit:
            raise ValidationError(f"Refund amount (KES {amount:,.2f}) exceeds remaining credit claim (KES {rem_credit:,.2f}).")

        if received_via == 'bank_transfer' and not destination_account:
            destination_account = BankAccount.objects.filter(business=credit.business, is_active=True, is_default=True).first()
            if not destination_account:
                destination_account = BankAccount.objects.filter(business=credit.business, is_active=True).first()

        refund = SupplierRefund.objects.create(
            business=credit.business,
            supplier_credit=credit,
            amount=amount,
            received_date=received_date,
            received_via=received_via,
            destination_account=destination_account if received_via == 'bank_transfer' else None,
            destination_type=destination_type,
            reference=reference,
            status='pending',
            received_by=user,
            notes=notes
        )

        credit.recalculate_resolution()

        ActivityLog.log_activity(
            user=user,
            action_type='create',
            description=f"Received Supplier Refund {refund.refund_number} for Credit {credit.credit_number} (KES {refund.amount:,.2f}) via {refund.get_received_via_display()}",
            model_name='SupplierRefund',
            object_id=refund.id,
            business=credit.business
        )

        return refund


class SupplierReportService:
    """Comprehensive financial and audit reporting for Accounts Payable and Cash/Bank Outflows"""

    @staticmethod
    def get_ap_aging_report(business, as_of_date=None, supplier_id=None):
        """Generates Accounts Payable Aging schedule broken down by aging buckets"""
        as_of = as_of_date or timezone.now().date()

        invoices_qs = SupplierInvoice.objects.filter(
            business=business,
            status__in=['unpaid', 'partially_paid', 'disputed']
        ).select_related('supplier')

        if supplier_id:
            invoices_qs = invoices_qs.filter(supplier_id=supplier_id)

        supplier_map = {}
        for inv in invoices_qs:
            rem = inv.remaining_balance()
            if rem <= Decimal('0.00'):
                continue

            supp = inv.supplier
            if supp.id not in supplier_map:
                supplier_map[supp.id] = {
                    'supplier': supp,
                    'current': Decimal('0.00'),       # 0 - 30 days
                    'days_30': Decimal('0.00'),       # 31 - 60 days
                    'days_60': Decimal('0.00'),       # 61 - 90 days
                    'days_90_plus': Decimal('0.00'),  # 90+ days
                    'total': Decimal('0.00'),
                    'invoices_count': 0,
                    'invoices': []
                }

            days_old = (as_of - inv.invoice_date).days
            if days_old <= 30:
                supplier_map[supp.id]['current'] += rem
            elif days_old <= 60:
                supplier_map[supp.id]['days_30'] += rem
            elif days_old <= 90:
                supplier_map[supp.id]['days_60'] += rem
            else:
                supplier_map[supp.id]['days_90_plus'] += rem

            supplier_map[supp.id]['total'] += rem
            supplier_map[supp.id]['invoices_count'] += 1
            supplier_map[supp.id]['invoices'].append({
                'invoice': inv,
                'remaining': rem,
                'days_old': days_old,
                'is_overdue': inv.due_date < as_of
            })

        aging_list = list(supplier_map.values())
        aging_list.sort(key=lambda x: x['total'], reverse=True)

        totals = {
            'current': sum(row['current'] for row in aging_list),
            'days_30': sum(row['days_30'] for row in aging_list),
            'days_60': sum(row['days_60'] for row in aging_list),
            'days_90_plus': sum(row['days_90_plus'] for row in aging_list),
            'total': sum(row['total'] for row in aging_list),
        }

        return {
            'as_of_date': as_of,
            'rows': aging_list,
            'totals': totals,
            'supplier_count': len(aging_list)
        }

    @staticmethod
    def get_supplier_statement(supplier, start_date=None, end_date=None):
        """
        Generates full Statement of Account for a given supplier:
        Invoices (Debit), Payments (Credit), Credits/Debit Notes (Credit), Refunds (Debit/adjustment).
        """
        today = timezone.now().date()
        end_d = end_date or today

        # 1. Opening balance before start_date
        opening_balance = Decimal('0.00')
        if start_date:
            opening_invoices = SupplierInvoice.objects.filter(
                supplier=supplier,
                invoice_date__lt=start_date,
                status__in=['unpaid', 'partially_paid', 'paid', 'disputed']
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            opening_payments = SupplierPayment.objects.filter(
                supplier=supplier,
                payment_date__lt=start_date,
                is_reversed=False
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            opening_credits = SupplierCredit.objects.filter(
                supplier=supplier,
                date_raised__lt=start_date,
                status__in=['approved_by_supplier', 'applied_to_invoice', 'refunded', 'partially_resolved']
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            opening_refunds = SupplierRefund.objects.filter(
                supplier_credit__supplier=supplier,
                received_date__lt=start_date
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

            opening_balance = (opening_invoices + opening_refunds) - (opening_payments + opening_credits)

        # 2. Transactions within range
        invoices_qs = SupplierInvoice.objects.filter(supplier=supplier).exclude(status='cancelled')
        payments_qs = SupplierPayment.objects.filter(supplier=supplier, is_reversed=False)
        credits_qs = SupplierCredit.objects.filter(supplier=supplier).exclude(status='rejected')
        refunds_qs = SupplierRefund.objects.filter(supplier_credit__supplier=supplier)

        if start_date:
            invoices_qs = invoices_qs.filter(invoice_date__gte=start_date, invoice_date__lte=end_d)
            payments_qs = payments_qs.filter(payment_date__gte=start_date, payment_date__lte=end_d)
            credits_qs = credits_qs.filter(date_raised__gte=start_date, date_raised__lte=end_d)
            refunds_qs = refunds_qs.filter(received_date__gte=start_date, received_date__lte=end_d)
        else:
            invoices_qs = invoices_qs.filter(invoice_date__lte=end_d)
            payments_qs = payments_qs.filter(payment_date__lte=end_d)
            credits_qs = credits_qs.filter(date_raised__lte=end_d)
            refunds_qs = refunds_qs.filter(received_date__lte=end_d)

        transactions = []
        for inv in invoices_qs:
            transactions.append({
                'date': inv.invoice_date,
                'type': 'invoice',
                'reference': inv.invoice_number,
                'description': f"Supplier Invoice: {inv.invoice_number} (Due: {inv.due_date})",
                'debit': inv.amount,
                'credit': Decimal('0.00'),
                'object': inv
            })

        for pay in payments_qs:
            transactions.append({
                'date': pay.payment_date,
                'type': 'payment',
                'reference': pay.payment_number,
                'description': f"Payment via {pay.get_payment_method_type_display()} ({pay.reference_number or 'Direct'})",
                'debit': Decimal('0.00'),
                'credit': pay.amount,
                'object': pay
            })

        for cr in credits_qs:
            transactions.append({
                'date': cr.date_raised,
                'type': 'credit',
                'reference': cr.credit_number,
                'description': f"Credit Claim: {cr.credit_number} ({cr.get_reason_display()})",
                'debit': Decimal('0.00'),
                'credit': cr.amount,
                'object': cr
            })

        for rf in refunds_qs:
            transactions.append({
                'date': rf.received_date,
                'type': 'refund',
                'reference': rf.refund_number,
                'description': f"Supplier Cash/Bank Refund: {rf.refund_number} for {rf.supplier_credit.credit_number}",
                'debit': rf.amount,
                'credit': Decimal('0.00'),
                'object': rf
            })

        transactions.sort(key=lambda x: (x['date'], x['reference']))

        running_balance = opening_balance
        for t in transactions:
            running_balance += (t['debit'] - t['credit'])
            t['balance'] = running_balance

        return {
            'supplier': supplier,
            'start_date': start_date,
            'end_date': end_d,
            'opening_balance': opening_balance,
            'closing_balance': running_balance,
            'transactions': transactions,
            'total_invoiced': sum(t['debit'] for t in transactions if t['type'] == 'invoice'),
            'total_paid': sum(t['credit'] for t in transactions if t['type'] == 'payment'),
            'total_credits': sum(t['credit'] for t in transactions if t['type'] == 'credit'),
            'total_refunded': sum(t['debit'] for t in transactions if t['type'] == 'refund'),
        }

    @staticmethod
    def get_outstanding_credits_report(business, supplier_id=None):
        """Returns all unresolved or partially resolved supplier credits/claims"""
        credits_qs = SupplierCredit.objects.filter(
            business=business,
            status__in=['pending_approval', 'approved_by_supplier', 'partially_resolved']
        ).select_related('supplier', 'related_invoice')

        if supplier_id:
            credits_qs = credits_qs.filter(supplier_id=supplier_id)

        rows = []
        for cr in credits_qs:
            rem = cr.remaining_credit()
            if rem > Decimal('0.00'):
                rows.append({
                    'credit': cr,
                    'remaining_amount': rem,
                    'days_pending': (timezone.now().date() - cr.date_raised).days
                })

        rows.sort(key=lambda x: x['remaining_amount'], reverse=True)
        total_outstanding = sum(r['remaining_amount'] for r in rows)

        return {
            'rows': rows,
            'credits': rows,
            'total_outstanding': total_outstanding,
            'count': len(rows)
        }

    @staticmethod
    def get_outstanding_cheques_report(business, bank_account_id=None):
        """Returns sent supplier payments not yet cleared on bank statement (payments-in-transit)"""
        payments_qs = SupplierPayment.objects.filter(
            business=business,
            status='sent',
            is_reversed=False,
            bank_statement_line__isnull=True
        ).select_related('supplier', 'bank_account')

        if bank_account_id:
            payments_qs = payments_qs.filter(bank_account_id=bank_account_id)

        payments = list(payments_qs.order_by('payment_date'))
        total_in_transit = sum(p.amount for p in payments)

        return {
            'payments': payments,
            'total_in_transit': total_in_transit,
            'total_uncleared': total_in_transit,
            'count': len(payments)
        }

    @staticmethod
    def get_unmatched_statement_lines_report(business, bank_account_id=None, start_date=None, end_date=None):
        """Returns all unmatched bank statement lines (both Inflows/Credits and Outflows/Debits)"""
        lines_qs = BankStatementLine.objects.filter(
            business=business,
            status='unmatched'
        ).select_related('bank_account', 'batch')

        if bank_account_id:
            lines_qs = lines_qs.filter(bank_account_id=bank_account_id)
        if start_date:
            lines_qs = lines_qs.filter(transaction_date__gte=start_date)
        if end_date:
            lines_qs = lines_qs.filter(transaction_date__lte=end_date)

        credits = list(lines_qs.filter(line_type='credit').order_by('transaction_date'))
        debits = list(lines_qs.filter(line_type='debit').order_by('transaction_date'))

        return {
            'credits': credits,
            'debits': debits,
            'total_unmatched_credits': sum(c.amount for c in credits),
            'total_unmatched_debits': sum(d.amount for d in debits),
            'unmatched_credits_count': len(credits),
            'unmatched_debits_count': len(debits),
        }
