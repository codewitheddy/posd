"""
Accounting & General Ledger Services Layer (Write Operations)
Standards: IFRS for SMEs / ICPAK Practice
"""
import logging
import csv
import io
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.models.organization import Company, Branch
from core.models.audit import AuditLog
from core.numbering.service import next_document_number
from core.events.bus import publish
from core.audit.service import log_audit

from accounting.models import (
    Account, AccountType, NormalBalance,
    FiscalYear, FiscalPeriod,
    JournalEntry, JournalEntryLine,
    JournalEntryType, JournalEntryStatus,
    PostingQueue,
    Customer, Vendor,
    CustomerInvoice, CustomerInvoiceLine, InvoiceStatus,
    CustomerPayment, CustomerPaymentAllocation,
    VendorBill, VendorBillLine, BillStatus,
    VendorPayment, VendorPaymentAllocation,
    BankAccount, BankStatement, BankStatementLine, BankReconciliation,
    WithholdingTaxRecord, WHTType, WHTCategory, TaxRateType
)

logger = logging.getLogger(__name__)


class FiscalPeriodService:
    """
    Manages Fiscal Year and Period lifecycle, locking, and Year-End Closing.
    """

    @staticmethod
    def get_period_for_date(company: Company, date_val: Optional[date] = None) -> Optional[FiscalPeriod]:
        """Resolve the active FiscalPeriod for a specific transaction date."""
        if not date_val:
            date_val = timezone.localdate()

        return FiscalPeriod.objects.filter(
            company=company,
            start_date__lte=date_val,
            end_date__gte=date_val,
        ).select_related('fiscal_year').first()

    @staticmethod
    def is_period_closed(company: Company, date_val: Optional[date] = None) -> bool:
        """Check if transaction date falls in a closed fiscal period or closed fiscal year."""
        if not date_val:
            date_val = timezone.localdate()

        period = FiscalPeriodService.get_period_for_date(company, date_val)
        if period:
            if period.is_closed or period.fiscal_year.is_closed:
                return True
            return False

        # If no period is defined at all, check if a closed fiscal year encompasses this date
        return FiscalYear.objects.filter(
            company=company,
            start_date__lte=date_val,
            end_date__gte=date_val,
            is_closed=True
        ).exists()

    @staticmethod
    @transaction.atomic
    def close_period(period: FiscalPeriod, user=None) -> FiscalPeriod:
        """Lock and close a fiscal period against any new postings."""
        if period.is_closed:
            return period

        period.is_closed = True
        period.closed_at = timezone.now()
        period.closed_by = user if (user and getattr(user, 'is_authenticated', False)) else None
        period.save(update_fields=['is_closed', 'closed_at', 'closed_by'])

        log_audit(
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            action=AuditLog.ACTION_UPDATE,
            instance=period,
            metadata={'description': f"Closed Fiscal Period: {period.name}"},
            company=period.company
        )
        return period

    @staticmethod
    @transaction.atomic
    def reopen_period(period: FiscalPeriod, user=None, reason: str = '') -> FiscalPeriod:
        """Reopen a closed period under supervisor authorization with audit trail."""
        if not period.is_closed:
            return period

        if period.fiscal_year.is_closed:
            raise ValidationError(f"Cannot reopen period '{period.name}': Parent fiscal year '{period.fiscal_year.name}' is closed.")

        period.is_closed = False
        period.reopened_at = timezone.now()
        period.reopened_by = user if (user and getattr(user, 'is_authenticated', False)) else None
        period.save(update_fields=['is_closed', 'reopened_at', 'reopened_by'])

        log_audit(
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            action=AuditLog.ACTION_UPDATE,
            instance=period,
            metadata={'description': f"Reopened Fiscal Period '{period.name}'. Reason: {reason or 'Administrative override'}"},
            company=period.company
        )
        return period

    @staticmethod
    @transaction.atomic
    def close_fiscal_year(fiscal_year: FiscalYear, user=None) -> JournalEntry:
        """
        Executes Year-End Closing:
        1. Aggregates all Income and Expense balances for the fiscal year.
        2. Generates an auto-balancing Year-End Closing Journal Entry (Debit Revenue, Credit Expenses).
        3. Posts the net difference (Net Profit / Loss) into Retained Earnings (Account 3100).
        4. Closes all periods and locks the fiscal year.
        """
        if fiscal_year.is_closed:
            raise ValidationError(f"Fiscal Year '{fiscal_year.name}' is already closed.")

        company = fiscal_year.company

        # Resolve Retained Earnings Account
        retained_earnings_acct = Account.objects.filter(
            company=company,
            system_tag='retained_earnings'
        ).first() or Account.objects.filter(company=company, code='3100').first()

        if not retained_earnings_acct:
            raise ValidationError("Cannot execute Year-End Close: Retained Earnings account (code 3100) not found.")

        # Find or create Period 13 / Closing period
        closing_period = fiscal_year.periods.filter(is_adjustment_period=True).first()
        if not closing_period:
            closing_period = fiscal_year.periods.order_by('-period_number').first()

        # Query all income and expense accounts with net activity in the fiscal year
        from django.db.models import Sum
        lines_to_close = []
        total_income = Decimal('0.00')
        total_expense = Decimal('0.00')

        pnl_accounts = Account.objects.filter(
            company=company,
            account_type__in=[AccountType.INCOME, AccountType.EXPENSE],
            is_active=True
        )

        for acct in pnl_accounts:
            aggs = JournalEntryLine.objects.filter(
                entry__company=company,
                entry__status=JournalEntryStatus.POSTED,
                entry__date__gte=fiscal_year.start_date,
                entry__date__lte=fiscal_year.end_date,
                account=acct
            ).aggregate(
                total_dr=Sum('debit'),
                total_cr=Sum('credit')
            )
            dr = aggs['total_dr'] or Decimal('0.00')
            cr = aggs['total_cr'] or Decimal('0.00')

            if dr == Decimal('0.00') and cr == Decimal('0.00'):
                continue

            if acct.account_type == AccountType.INCOME:
                # Normal Credit balance: to close, Debit account by net Credit
                net_credit = cr - dr
                if net_credit != Decimal('0.00'):
                    total_income += net_credit
                    lines_to_close.append({
                        'account_code': acct.code,
                        'account_name': acct.name,
                        'debit': net_credit if net_credit > 0 else Decimal('0.00'),
                        'credit': -net_credit if net_credit < 0 else Decimal('0.00'),
                        'description': f"Year-End Close: Clear {acct.name}"
                    })
            else:
                # Normal Debit balance: to close, Credit account by net Debit
                net_debit = dr - cr
                if net_debit != Decimal('0.00'):
                    total_expense += net_debit
                    lines_to_close.append({
                        'account_code': acct.code,
                        'account_name': acct.name,
                        'debit': -net_debit if net_debit < 0 else Decimal('0.00'),
                        'credit': net_debit if net_debit > 0 else Decimal('0.00'),
                        'description': f"Year-End Close: Clear {acct.name}"
                    })

        net_profit_loss = total_income - total_expense

        # Post net difference into Retained Earnings
        if net_profit_loss > Decimal('0.00'):
            # Net Profit: Credit Retained Earnings
            lines_to_close.append({
                'account_code': retained_earnings_acct.code,
                'account_name': retained_earnings_acct.name,
                'debit': Decimal('0.00'),
                'credit': net_profit_loss,
                'description': f"Year-End Net Profit transfer to Retained Earnings ({fiscal_year.name})"
            })
        elif net_profit_loss < Decimal('0.00'):
            # Net Loss: Debit Retained Earnings
            lines_to_close.append({
                'account_code': retained_earnings_acct.code,
                'account_name': retained_earnings_acct.name,
                'debit': abs(net_profit_loss),
                'credit': Decimal('0.00'),
                'description': f"Year-End Net Loss transfer from Retained Earnings ({fiscal_year.name})"
            })

        closing_entry = None
        if lines_to_close:
            closing_entry = JournalPostingService.post_journal(
                company=company,
                source_module='accounting',
                source_ref=f"YE-CLOSE-{fiscal_year.name.replace(' ', '')}",
                date_val=fiscal_year.end_date,
                lines=lines_to_close,
                narration=f"Year-End Closing Journal Entry for {fiscal_year.name}. Net P&L: KES {net_profit_loss:,.2f}",
                posted_by=user,
                entry_type=JournalEntryType.CLOSING,
                auto_approve=True,
                bypass_period_check=True
            )

        # Close all periods in the fiscal year
        fiscal_year.periods.update(is_closed=True, closed_at=timezone.now(), closed_by=user if getattr(user, 'is_authenticated', False) else None)

        # Lock fiscal year
        fiscal_year.is_closed = True
        fiscal_year.closed_at = timezone.now()
        fiscal_year.closed_by = user if getattr(user, 'is_authenticated', False) else None
        fiscal_year.save(update_fields=['is_closed', 'closed_at', 'closed_by'])

        log_audit(
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            action=AuditLog.ACTION_UPDATE,
            instance=fiscal_year,
            metadata={'description': f"Closed Fiscal Year '{fiscal_year.name}'. Net P&L KES {net_profit_loss:,.2f} rolled into Retained Earnings."},
            company=company
        )

        return closing_entry


class JournalPostingService:
    """
    Central, high-integrity service for posting, validating, and reversing General Ledger Journals.
    """

    @staticmethod
    @transaction.atomic
    def post_journal(
        company: Company,
        source_module: str,
        source_ref: str,
        date_val: Optional[date] = None,
        lines: Optional[List[Dict[str, Any]]] = None,
        narration: str = '',
        posted_by: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
        branch: Optional[Branch] = None,
        entry_type: str = JournalEntryType.MANUAL,
        auto_approve: bool = True,
        bypass_period_check: bool = False,
    ) -> JournalEntry:
        """
        Public posting service implementing double-entry balancing and idempotency.

        Args:
            company: Tenant Company instance
            source_module: e.g. 'pos', 'hr', 'accounting', 'manual'
            source_ref: e.g. 'INV-001', 'ZREP-20260930-01'
            date_val: Effective journal transaction date
            lines: List of dicts with keys:
                - 'account_code' or 'account_id' (str / int)
                - 'account_name' (optional str)
                - 'debit' (Decimal / str / float)
                - 'credit' (Decimal / str / float)
                - 'currency' (optional str, default 'KES')
                - 'exchange_rate' (optional Decimal, default 1.0)
                - 'foreign_amount' (optional Decimal)
                - 'branch' (optional Branch instance)
                - 'cost_center' (optional str)
                - 'description' (optional str)
            narration: High-level entry description
            posted_by: User instance triggering the posting
            idempotency_key: Optional unique key (defaults to 'source_module:source_ref')
            branch: Optional analytic branch
            entry_type: JournalEntryType choice
            auto_approve: Mark as posted immediately if True
            bypass_period_check: Used only for automated Year-End Closing
        """
        if not company:
            raise ValidationError("A valid Company is required to post to the General Ledger.")

        if not lines or len(lines) < 2:
            raise ValidationError("A Journal Entry requires at least two balanced lines (debit and credit).")

        if not date_val:
            date_val = timezone.localdate()

        # 1. Closed Period Check
        if not bypass_period_check and FiscalPeriodService.is_period_closed(company, date_val):
            raise ValidationError(f"Cannot post journal entry: Fiscal Period for date {date_val.strftime('%d/%m/%Y')} is closed.")

        # 2. Idempotency Protection
        computed_idempotency = idempotency_key or (f"{source_module}:{source_ref}" if source_ref else None)
        if computed_idempotency:
            existing = JournalEntry.objects.filter(
                company=company,
                idempotency_key=computed_idempotency,
            ).first()
            if existing:
                logger.info("Idempotent journal posting match: %s", existing.entry_number)
                return existing

        # 3. Resolve Period
        fiscal_period = FiscalPeriodService.get_period_for_date(company, date_val)

        # 4. Parse & Validate Lines
        total_debits = Decimal('0.00')
        total_credits = Decimal('0.00')
        parsed_lines = []

        # Preload accounts for performance
        account_codes = [str(line.get('account_code', '')).strip() for line in lines if line.get('account_code')]
        account_ids = [line.get('account_id') for line in lines if line.get('account_id')]
        
        accounts_by_code = {
            a.code: a for a in Account.objects.filter(company=company, code__in=account_codes)
        }
        accounts_by_id = {
            a.id: a for a in Account.objects.filter(company=company, id__in=account_ids)
        }

        for idx, raw in enumerate(lines, start=1):
            account = None
            if isinstance(raw.get('account'), Account):
                account = raw['account']
            elif raw.get('account_id') and raw['account_id'] in accounts_by_id:
                account = accounts_by_id[raw['account_id']]
            elif raw.get('account_code') and str(raw['account_code']).strip() in accounts_by_code:
                account = accounts_by_code[str(raw['account_code']).strip()]

            if not account:
                code_label = raw.get('account_code') or raw.get('account_id') or f'Line {idx}'
                raise ValidationError(f"Line {idx}: Account '{code_label}' not found in Company '{company.name}' Chart of Accounts.")

            if not account.is_active:
                raise ValidationError(f"Line {idx}: Account '{account.code} - {account.name}' is inactive.")

            if account.is_locked and entry_type == JournalEntryType.MANUAL:
                raise ValidationError(f"Line {idx}: Account '{account.code} - {account.name}' is locked from manual postings.")

            try:
                raw_dr = raw.get('debit', Decimal('0.00')) or Decimal('0.00')
                raw_cr = raw.get('credit', Decimal('0.00')) or Decimal('0.00')
                debit = Decimal(str(raw_dr)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                credit = Decimal(str(raw_cr)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except Exception as e:
                raise ValidationError(f"Line {idx}: Invalid numeric amount ({e}).")

            if debit < Decimal('0.00') or credit < Decimal('0.00'):
                raise ValidationError(f"Line {idx}: Amounts cannot be negative (Debit: {debit}, Credit: {credit}).")

            if debit == Decimal('0.00') and credit == Decimal('0.00'):
                raise ValidationError(f"Line {idx}: Must specify either a non-zero Debit or Credit.")

            if debit > Decimal('0.00') and credit > Decimal('0.00'):
                raise ValidationError(f"Line {idx}: A single line cannot have both Debit and Credit amounts.")

            # Multi-Currency parsing
            currency = str(raw.get('currency', account.currency or 'KES')).upper()
            fx_rate = Decimal(str(raw.get('exchange_rate', '1.000000') or '1.000000'))
            foreign_amt = Decimal(str(raw.get('foreign_amount', '0.00') or '0.00'))

            line_branch = raw.get('branch') or branch
            cost_center = str(raw.get('cost_center', '')).strip()
            desc = str(raw.get('description', '')).strip() or narration

            total_debits += debit
            total_credits += credit

            parsed_lines.append({
                'account': account,
                'account_code': account.code,
                'account_name': account.name,
                'debit': debit,
                'credit': credit,
                'currency': currency,
                'exchange_rate': fx_rate,
                'foreign_amount': foreign_amt,
                'branch': line_branch,
                'cost_center': cost_center,
                'description': desc,
            })

        # 5. Strict Double-Entry Balance Check
        if round(total_debits, 2) != round(total_credits, 2):
            diff = abs(total_debits - total_credits)
            raise ValidationError(
                f"Unbalanced Journal Entry! Total Debits (KES {total_debits:,.2f}) "
                f"!= Total Credits (KES {total_credits:,.2f}). Difference: KES {diff:,.2f}"
            )

        if total_debits <= Decimal('0.00'):
            raise ValidationError("Journal entry total must be greater than zero.")

        # 6. Generate Document Number
        prefix = 'JRN'
        if entry_type == JournalEntryType.SALES_CLOSE:
            prefix = 'POS-JRN'
        elif entry_type == JournalEntryType.PAYROLL:
            prefix = 'PAY-JRN'
        elif entry_type == JournalEntryType.AR_INVOICE:
            prefix = 'AR-JRN'
        elif entry_type == JournalEntryType.AP_BILL:
            prefix = 'AP-JRN'
        elif entry_type == JournalEntryType.RECEIPT:
            prefix = 'REC-JRN'
        elif entry_type == JournalEntryType.PAYMENT:
            prefix = 'DIS-JRN'
        elif entry_type == JournalEntryType.REVERSING:
            prefix = 'REV-JRN'
        elif entry_type == JournalEntryType.CLOSING:
            prefix = 'CLS-JRN'

        entry_number = next_document_number(
            document_type='journal_entry',
            company=company,
            date_val=date_val,
            prefix=prefix,
            format_pattern='{prefix}-{year}{month:02d}-{seq:04d}',
        )

        status = JournalEntryStatus.POSTED if auto_approve else JournalEntryStatus.DRAFT

        # 7. Create Header & Lines
        entry = JournalEntry.objects.create(
            company=company,
            branch=branch,
            entry_number=entry_number,
            entry_type=entry_type,
            date=date_val,
            fiscal_period=fiscal_period,
            source_module=source_module,
            source_ref=source_ref,
            idempotency_key=computed_idempotency,
            narration=narration or f"Journal posting from {source_module.upper()} ({source_ref})",
            status=status,
            posted_by=posted_by if (posted_by and getattr(posted_by, 'is_authenticated', False)) else None,
            posted_at=timezone.now() if status == JournalEntryStatus.POSTED else None,
            total_amount=total_debits,
        )

        line_objs = [
            JournalEntryLine(
                entry=entry,
                account=item['account'],
                account_code=item['account_code'],
                account_name=item['account_name'],
                debit=item['debit'],
                credit=item['credit'],
                currency=item['currency'],
                exchange_rate=item['exchange_rate'],
                foreign_amount=item['foreign_amount'],
                branch=item['branch'],
                cost_center=item['cost_center'],
                description=item['description'],
            )
            for item in parsed_lines
        ]
        JournalEntryLine.objects.bulk_create(line_objs)

        # 8. Audit Trail
        log_audit(
            user=posted_by if (posted_by and getattr(posted_by, 'is_authenticated', False)) else None,
            action=AuditLog.ACTION_CREATE,
            instance=entry,
            metadata={'description': f"Posted Journal #{entry.entry_number} ({entry.get_entry_type_display()}): KES {entry.total_amount:,.2f}"},
            company=company
        )

        # 9. Publish Domain Event
        try:
            publish(
                event_name='accounting.journal_posted.v1',
                payload={
                    'entry_id': entry.pk,
                    'entry_number': entry.entry_number,
                    'company_id': company.pk,
                    'source_module': source_module,
                    'source_ref': source_ref,
                    'date': date_val.isoformat(),
                    'total_amount': str(total_debits),
                    'line_count': len(line_objs),
                },
                company=company,
                idempotency_key=f"event:journal_posted:{entry.pk}",
            )
        except Exception as e:
            logger.warning("Could not publish accounting event: %s", e)

        return entry

    @staticmethod
    @transaction.atomic
    def reverse_journal(
        entry: JournalEntry,
        reversed_by: Any,
        reason: str = '',
        date_val: Optional[date] = None,
    ) -> JournalEntry:
        """
        Creates an exact countervailing Reversing Journal Entry (Debit -> Credit, Credit -> Debit).
        Marks the original entry as REVERSED and sets bidirectional links.
        """
        if entry.status == JournalEntryStatus.REVERSED:
            raise ValidationError(f"Journal #{entry.entry_number} is already reversed by #{entry.reversal_entry.entry_number if entry.reversal_entry else 'another entry'}.")

        if entry.status != JournalEntryStatus.POSTED:
            raise ValidationError(f"Only POSTED journals can be reversed. Current status is '{entry.get_status_display()}'.")

        reversal_date = date_val or timezone.localdate()

        # Build inverted lines
        reversal_lines = []
        for line in entry.lines.select_related('account', 'branch'):
            reversal_lines.append({
                'account': line.account,
                'account_code': line.account_code,
                'account_name': line.account_name,
                'debit': line.credit,  # Invert!
                'credit': line.debit,  # Invert!
                'currency': line.currency,
                'exchange_rate': line.exchange_rate,
                'foreign_amount': line.foreign_amount,
                'branch': line.branch,
                'cost_center': line.cost_center,
                'description': f"Reversal of #{entry.entry_number}: {line.description}",
            })

        reversal_narration = f"Reversal of Journal #{entry.entry_number}. Reason: {reason or 'Correction / Adjustment'}"

        reversal_entry = JournalPostingService.post_journal(
            company=entry.company,
            source_module='accounting',
            source_ref=f"REV-{entry.entry_number}",
            date_val=reversal_date,
            lines=reversal_lines,
            narration=reversal_narration,
            posted_by=reversed_by,
            branch=entry.branch,
            entry_type=JournalEntryType.REVERSING,
            auto_approve=True,
        )

        # Update original entry status and pointers
        now = timezone.now()
        entry.status = JournalEntryStatus.REVERSED
        entry.reversed_at = now
        entry.reversed_by = reversed_by if getattr(reversed_by, 'is_authenticated', False) else None
        entry.reversal_entry = reversal_entry
        entry.reversal_reason = reason
        entry.save(update_fields=['status', 'reversed_at', 'reversed_by', 'reversal_entry', 'reversal_reason'])

        # Audit
        log_audit(
            user=reversed_by if (reversed_by and getattr(reversed_by, 'is_authenticated', False)) else None,
            action=AuditLog.ACTION_UPDATE,
            instance=entry,
            metadata={'description': f"Reversed Journal #{entry.entry_number} via #{reversal_entry.entry_number}. Reason: {reason}"},
            company=entry.company
        )

        return reversal_entry


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNTS RECEIVABLE (AR) SUBLEDGER SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class ARService:
    """
    Accounts Receivable Subledger Operations.
    Owns Customer Invoicing, Customer Payment Receipts, and Subledger Allocations.
    Posts strictly via JournalPostingService.post_journal.
    """
    @staticmethod
    @transaction.atomic
    def post_customer_invoice(invoice: CustomerInvoice, user: Any = None) -> JournalEntry:
        """
        Calculates invoice totals and posts double-entry journal:
        DR 1100 Accounts Receivable (Total)
        CR 4000/Sales Revenue (Subtotal by line)
        CR 2100 VAT Output Tax Payable (Tax total)
        """
        if invoice.status != InvoiceStatus.DRAFT:
            raise ValidationError(f"Only DRAFT invoices can be posted. Current status: '{invoice.status}'")
        
        lines_qs = invoice.lines.select_related('account')
        if not lines_qs.exists():
            raise ValidationError("Cannot post an invoice without line items.")

        company = invoice.company
        subtotal = Decimal('0.00')
        total_tax = Decimal('0.00')
        gl_lines = []

        # Find AR control account (tag 'ar' or code '1100')
        ar_account = Account.objects.filter(company=company, system_tag='ar').first() or \
                     Account.objects.filter(company=company, code='1100').first()
        if not ar_account:
            raise ValidationError("Accounts Receivable control account (1100) not found in COA.")

        # Find VAT Output account (tag 'vat_output' or code '2100')
        vat_account = Account.objects.filter(company=company, system_tag='vat_output').first() or \
                      Account.objects.filter(company=company, code='2100').first()

        for line in lines_qs:
            qty = line.quantity
            price = line.unit_price
            rate = line.tax_rate
            line_subtotal = (qty * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            line_tax = (line_subtotal * (rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            line.tax_amount = line_tax
            line.line_total = line_subtotal + line_tax
            line.save(update_fields=['tax_amount', 'line_total'])

            subtotal += line_subtotal
            total_tax += line_tax

            # CR Revenue line
            gl_lines.append({
                'account': line.account,
                'debit': Decimal('0.00'),
                'credit': line_subtotal,
                'description': f"Inv #{invoice.invoice_number} - {line.description}",
                'branch': invoice.branch,
            })

        total_amount = subtotal + total_tax

        # CR VAT Output if tax > 0
        if total_tax > Decimal('0.00'):
            if not vat_account:
                raise ValidationError("VAT Output account (2100) not found in COA.")
            gl_lines.append({
                'account': vat_account,
                'debit': Decimal('0.00'),
                'credit': total_tax,
                'description': f"VAT Output on Inv #{invoice.invoice_number}",
                'branch': invoice.branch,
            })

        # DR Accounts Receivable
        gl_lines.insert(0, {
            'account': ar_account,
            'debit': total_amount,
            'credit': Decimal('0.00'),
            'description': f"Customer Invoice #{invoice.invoice_number} - {invoice.customer.name}",
            'branch': invoice.branch,
        })

        # Post journal
        entry = JournalPostingService.post_journal(
            company=company,
            source_module='ar',
            source_ref=f"INV-{invoice.invoice_number}",
            date_val=invoice.invoice_date,
            lines=gl_lines,
            narration=f"Customer Invoice #{invoice.invoice_number} to {invoice.customer.name}",
            posted_by=user,
            branch=invoice.branch,
            entry_type=JournalEntryType.AR_INVOICE,
            auto_approve=True,
        )

        invoice.subtotal = subtotal
        invoice.tax_amount = total_tax
        invoice.total_amount = total_amount
        invoice.balance_due = total_amount - invoice.amount_paid
        invoice.status = InvoiceStatus.POSTED if invoice.balance_due > 0 else InvoiceStatus.PAID
        invoice.journal_entry = entry
        invoice.save(update_fields=['subtotal', 'tax_amount', 'total_amount', 'balance_due', 'status', 'journal_entry'])

        return entry

    @staticmethod
    @transaction.atomic
    def record_customer_payment(
        payment: CustomerPayment,
        allocations: Optional[List[Dict[str, Any]]] = None,
        user: Any = None
    ) -> JournalEntry:
        """
        Records customer payment receipt and posts double entry:
        DR Deposit Account (Cash/Bank/M-Pesa)
        CR 1100 Accounts Receivable
        Allocates payment across open invoices and updates balances.
        """
        company = payment.company
        ar_account = Account.objects.filter(company=company, system_tag='ar').first() or \
                     Account.objects.filter(company=company, code='1100').first()
        if not ar_account:
            raise ValidationError("Accounts Receivable control account (1100) not found in COA.")

        gl_lines = [
            {
                'account': payment.deposit_account,
                'debit': payment.amount,
                'credit': Decimal('0.00'),
                'description': f"Customer Payment #{payment.receipt_number} from {payment.customer.name} ({payment.get_payment_method_display()})",
                'branch': payment.branch,
            },
            {
                'account': ar_account,
                'debit': Decimal('0.00'),
                'credit': payment.amount,
                'description': f"Receipt #{payment.receipt_number} for {payment.customer.name}",
                'branch': payment.branch,
            }
        ]

        entry = JournalPostingService.post_journal(
            company=company,
            source_module='ar',
            source_ref=f"REC-{payment.receipt_number}",
            date_val=payment.payment_date,
            lines=gl_lines,
            narration=f"Customer Receipt #{payment.receipt_number} - {payment.customer.name} - Ref: {payment.reference or 'N/A'}",
            posted_by=user,
            branch=payment.branch,
            entry_type=JournalEntryType.RECEIPT,
            auto_approve=True,
        )

        payment.journal_entry = entry
        payment.save(update_fields=['journal_entry'])

        # Process invoice allocations
        remaining_unallocated = payment.amount
        if allocations:
            for item in allocations:
                inv = item['invoice']
                alloc_amt = Decimal(str(item['amount'])).quantize(Decimal('0.01'))
                if alloc_amt <= Decimal('0.00'):
                    continue
                CustomerPaymentAllocation.objects.create(
                    payment=payment,
                    invoice=inv,
                    amount_allocated=alloc_amt
                )
                inv.amount_paid += alloc_amt
                inv.balance_due = max(Decimal('0.00'), inv.total_amount - inv.amount_paid)
                if inv.balance_due == Decimal('0.00'):
                    inv.status = InvoiceStatus.PAID
                elif inv.amount_paid > Decimal('0.00'):
                    inv.status = InvoiceStatus.PARTIAL
                inv.save(update_fields=['amount_paid', 'balance_due', 'status'])
                remaining_unallocated -= alloc_amt

        # Auto-allocate any remaining payment to oldest open invoices of this customer
        if remaining_unallocated > Decimal('0.00'):
            open_invoices = CustomerInvoice.objects.filter(
                company=company,
                customer=payment.customer,
                status__in=[InvoiceStatus.POSTED, InvoiceStatus.PARTIAL],
                balance_due__gt=0
            ).order_by('invoice_date', 'id')

            for inv in open_invoices:
                if remaining_unallocated <= Decimal('0.00'):
                    break
                alloc_amt = min(remaining_unallocated, inv.balance_due)
                CustomerPaymentAllocation.objects.create(
                    payment=payment,
                    invoice=inv,
                    amount_allocated=alloc_amt
                )
                inv.amount_paid += alloc_amt
                inv.balance_due = max(Decimal('0.00'), inv.total_amount - inv.amount_paid)
                if inv.balance_due == Decimal('0.00'):
                    inv.status = InvoiceStatus.PAID
                else:
                    inv.status = InvoiceStatus.PARTIAL
                inv.save(update_fields=['amount_paid', 'balance_due', 'status'])
                remaining_unallocated -= alloc_amt

        return entry


# ═══════════════════════════════════════════════════════════════════════════════
# ACCOUNTS PAYABLE (AP) SUBLEDGER SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class APService:
    """
    Accounts Payable Subledger Operations.
    Owns Vendor Bills, Vendor Payment Disbursements, and Subledger Allocations.
    Posts strictly via JournalPostingService.post_journal.
    """
    @staticmethod
    @transaction.atomic
    def post_vendor_bill(bill: VendorBill, user: Any = None) -> JournalEntry:
        """
        Calculates bill totals and posts double-entry journal:
        DR 5000/6000 Expense/Cost (Subtotal by line)
        DR 1400 VAT Input Tax Claimable (Tax total)
        CR 2000 Accounts Payable (Total)
        """
        if bill.status != BillStatus.DRAFT:
            raise ValidationError(f"Only DRAFT bills can be posted. Current status: '{bill.status}'")

        lines_qs = bill.lines.select_related('account')
        if not lines_qs.exists():
            raise ValidationError("Cannot post a bill without line items.")

        company = bill.company
        subtotal = Decimal('0.00')
        total_tax = Decimal('0.00')
        gl_lines = []

        ap_account = Account.objects.filter(company=company, system_tag='ap').first() or \
                     Account.objects.filter(company=company, code='2000').first()
        if not ap_account:
            raise ValidationError("Accounts Payable control account (2000) not found in COA.")

        vat_input_account = Account.objects.filter(company=company, system_tag='vat_input').first() or \
                            Account.objects.filter(company=company, code='1400').first()

        for line in lines_qs:
            qty = line.quantity
            price = line.unit_price
            rate = line.tax_rate
            line_subtotal = (qty * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            line_tax = (line_subtotal * (rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            line.tax_amount = line_tax
            line.line_total = line_subtotal + line_tax
            line.save(update_fields=['tax_amount', 'line_total'])

            subtotal += line_subtotal
            total_tax += line_tax

            # DR Expense line
            gl_lines.append({
                'account': line.account,
                'debit': line_subtotal,
                'credit': Decimal('0.00'),
                'description': f"Bill #{bill.bill_number} - {line.description}",
                'branch': bill.branch,
            })

        total_amount = subtotal + total_tax

        # DR VAT Input if tax > 0
        if total_tax > Decimal('0.00'):
            if not vat_input_account:
                raise ValidationError("VAT Input account (1400) not found in COA.")
            gl_lines.append({
                'account': vat_input_account,
                'debit': total_tax,
                'credit': Decimal('0.00'),
                'description': f"VAT Input Claimable on Bill #{bill.bill_number}",
                'branch': bill.branch,
            })

        # CR Accounts Payable
        gl_lines.append({
            'account': ap_account,
            'debit': Decimal('0.00'),
            'credit': total_amount,
            'description': f"Vendor Bill #{bill.bill_number} - {bill.vendor.name}",
            'branch': bill.branch,
        })

        entry = JournalPostingService.post_journal(
            company=company,
            source_module='ap',
            source_ref=f"BILL-{bill.bill_number}",
            date_val=bill.bill_date,
            lines=gl_lines,
            narration=f"Vendor Bill #{bill.bill_number} from {bill.vendor.name} (Supplier Inv: {bill.supplier_invoice_number or 'N/A'})",
            posted_by=user,
            branch=bill.branch,
            entry_type=JournalEntryType.AP_BILL,
            auto_approve=True,
        )

        bill.subtotal = subtotal
        bill.tax_amount = total_tax
        bill.total_amount = total_amount
        bill.balance_due = total_amount - bill.amount_paid
        bill.status = BillStatus.POSTED if bill.balance_due > 0 else BillStatus.PAID
        bill.journal_entry = entry
        bill.save(update_fields=['subtotal', 'tax_amount', 'total_amount', 'balance_due', 'status', 'journal_entry'])

        return entry

    @staticmethod
    @transaction.atomic
    def record_vendor_payment(
        payment: VendorPayment,
        allocations: Optional[List[Dict[str, Any]]] = None,
        user: Any = None
    ) -> JournalEntry:
        """
        Records vendor payment disbursement and posts double entry:
        DR 2000 Accounts Payable
        CR Paid From Account (Bank/Cash/M-Pesa)
        Allocates payment across open bills and updates balances.
        """
        company = payment.company
        ap_account = Account.objects.filter(company=company, system_tag='ap').first() or \
                     Account.objects.filter(company=company, code='2000').first()
        if not ap_account:
            raise ValidationError("Accounts Payable control account (2000) not found in COA.")

        gl_lines = [
            {
                'account': ap_account,
                'debit': payment.amount,
                'credit': Decimal('0.00'),
                'description': f"Payment #{payment.voucher_number} to {payment.vendor.name}",
                'branch': payment.branch,
            },
            {
                'account': payment.paid_from_account,
                'debit': Decimal('0.00'),
                'credit': payment.amount,
                'description': f"Disbursement #{payment.voucher_number} for {payment.vendor.name} ({payment.get_payment_method_display()})",
                'branch': payment.branch,
            }
        ]

        entry = JournalPostingService.post_journal(
            company=company,
            source_module='ap',
            source_ref=f"VOUCH-{payment.voucher_number}",
            date_val=payment.payment_date,
            lines=gl_lines,
            narration=f"Vendor Payment Voucher #{payment.voucher_number} - {payment.vendor.name} - Ref: {payment.reference or 'N/A'}",
            posted_by=user,
            branch=payment.branch,
            entry_type=JournalEntryType.PAYMENT,
            auto_approve=True,
        )

        payment.journal_entry = entry
        payment.save(update_fields=['journal_entry'])

        remaining_unallocated = payment.amount
        if allocations:
            for item in allocations:
                b = item['bill']
                alloc_amt = Decimal(str(item['amount'])).quantize(Decimal('0.01'))
                if alloc_amt <= Decimal('0.00'):
                    continue
                VendorPaymentAllocation.objects.create(
                    payment=payment,
                    bill=b,
                    amount_allocated=alloc_amt
                )
                b.amount_paid += alloc_amt
                b.balance_due = max(Decimal('0.00'), b.total_amount - b.amount_paid)
                if b.balance_due == Decimal('0.00'):
                    b.status = BillStatus.PAID
                elif b.amount_paid > Decimal('0.00'):
                    b.status = BillStatus.PARTIAL
                b.save(update_fields=['amount_paid', 'balance_due', 'status'])
                remaining_unallocated -= alloc_amt

        if remaining_unallocated > Decimal('0.00'):
            open_bills = VendorBill.objects.filter(
                company=company,
                vendor=payment.vendor,
                status__in=[BillStatus.POSTED, BillStatus.PARTIAL],
                balance_due__gt=0
            ).order_by('bill_date', 'id')

            for b in open_bills:
                if remaining_unallocated <= Decimal('0.00'):
                    break
                alloc_amt = min(remaining_unallocated, b.balance_due)
                VendorPaymentAllocation.objects.create(
                    payment=payment,
                    bill=b,
                    amount_allocated=alloc_amt
                )
                b.amount_paid += alloc_amt
                b.balance_due = max(Decimal('0.00'), b.total_amount - b.amount_paid)
                if b.balance_due == Decimal('0.00'):
                    b.status = BillStatus.PAID
                else:
                    b.status = BillStatus.PARTIAL
                b.save(update_fields=['amount_paid', 'balance_due', 'status'])
                remaining_unallocated -= alloc_amt

        return entry


# ═══════════════════════════════════════════════════════════════════════════════
# BANK STATEMENT INGESTION & AUTO-RECONCILIATION SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class BankReconciliationService:
    """
    Bank & M-Pesa Statement Ingestion, Parsing, Auto-Reconciliation, and Statement Matching.
    """
    @staticmethod
    def parse_mpesa_statement(
        bank_account: BankAccount,
        csv_content: str,
        user: Any = None
    ) -> BankStatement:
        """
        Parses Safaricom M-Pesa statement CSV and creates BankStatement + BankStatementLine records.
        Handles standard M-Pesa CSV headers:
        Receipt No., Completion Time, Details, Transaction Status, Paid In, Withdrawn, Balance
        """
        import csv
        import io
        from datetime import datetime

        reader = csv.reader(io.StringIO(csv_content.strip()))
        rows = list(reader)
        if not rows:
            raise ValidationError("Empty CSV statement content.")

        header_idx = -1
        for idx, row in enumerate(rows):
            row_str = ' '.join(row).lower()
            if 'receipt no' in row_str or 'completion time' in row_str or 'details' in row_str:
                header_idx = idx
                break

        if header_idx == -1:
            header_idx = 0

        header = [h.strip().lower() for h in rows[header_idx]]
        
        def find_col(candidates):
            for c in candidates:
                for idx, h in enumerate(header):
                    if c in h:
                        return idx
            return -1

        receipt_col = find_col(['receipt no', 'receipt', 'ref', 'trans id', 'id'])
        time_col = find_col(['completion time', 'time', 'date', 'txn date'])
        details_col = find_col(['details', 'description', 'particulars', 'narration'])
        paid_in_col = find_col(['paid in', 'credit', 'deposit', 'money in', 'amount received'])
        withdrawn_col = find_col(['withdrawn', 'debit', 'withdrawal', 'money out', 'amount paid'])
        balance_col = find_col(['balance', 'running balance'])

        parsed_lines = []
        dates = []

        for row in rows[header_idx + 1:]:
            if not row or not any(row):
                continue
            if len(row) <= max(receipt_col, time_col, details_col, 0):
                continue

            ref = row[receipt_col].strip() if receipt_col >= 0 and receipt_col < len(row) else ''
            time_raw = row[time_col].strip() if time_col >= 0 and time_col < len(row) else ''
            desc = row[details_col].strip() if details_col >= 0 and details_col < len(row) else 'M-Pesa Transaction'
            
            txn_date = None
            for fmt in ['%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                try:
                    txn_date = datetime.strptime(time_raw, fmt).date()
                    break
                except ValueError:
                    pass
            if not txn_date:
                txn_date = timezone.localdate()
            dates.append(txn_date)

            paid_in_str = row[paid_in_col].strip().replace(',', '').replace(' ', '') if paid_in_col >= 0 and paid_in_col < len(row) else '0'
            withdrawn_str = row[withdrawn_col].strip().replace(',', '').replace(' ', '') if withdrawn_col >= 0 and withdrawn_col < len(row) else '0'

            try:
                paid_in = Decimal(paid_in_str) if paid_in_str else Decimal('0.00')
            except Exception:
                paid_in = Decimal('0.00')

            try:
                withdrawn = Decimal(withdrawn_str) if withdrawn_str else Decimal('0.00')
            except Exception:
                withdrawn = Decimal('0.00')

            net_amount = paid_in - withdrawn
            if net_amount == Decimal('0.00') and not ref:
                continue

            bal_str = row[balance_col].strip().replace(',', '').replace(' ', '') if balance_col >= 0 and balance_col < len(row) else None
            try:
                running_bal = Decimal(bal_str) if bal_str else None
            except Exception:
                running_bal = None

            parsed_lines.append({
                'date': txn_date,
                'reference': ref,
                'description': desc,
                'amount': net_amount,
                'balance': running_bal,
            })

        if not parsed_lines:
            raise ValidationError("No valid transaction rows found in the uploaded statement.")

        start_date = min(dates) if dates else timezone.localdate()
        end_date = max(dates) if dates else timezone.localdate()

        statement = BankStatement.objects.create(
            company=bank_account.company,
            bank_account=bank_account,
            statement_date=end_date,
            start_date=start_date,
            end_date=end_date,
            opening_balance=parsed_lines[0]['balance'] - parsed_lines[0]['amount'] if parsed_lines[0]['balance'] is not None else Decimal('0.00'),
            closing_balance=parsed_lines[-1]['balance'] if parsed_lines[-1]['balance'] is not None else Decimal('0.00'),
        )

        for l in parsed_lines:
            BankStatementLine.objects.create(
                statement=statement,
                date=l['date'],
                reference=l['reference'],
                description=l['description'],
                amount=l['amount'],
                balance=l['balance'],
            )

        return statement

    @staticmethod
    def parse_bank_statement(
        bank_account: BankAccount,
        csv_content: str,
        user: Any = None
    ) -> BankStatement:
        """
        Parses standard Kenyan Bank CSV (Equity, KCB, Stanbic, Co-op).
        Headers: Date, Reference/Cheque, Description/Narration, Debit, Credit, Balance
        """
        import csv
        import io
        from datetime import datetime

        reader = csv.reader(io.StringIO(csv_content.strip()))
        rows = list(reader)
        if not rows:
            raise ValidationError("Empty CSV statement content.")

        header_idx = -1
        for idx, row in enumerate(rows):
            row_str = ' '.join(row).lower()
            if 'date' in row_str and ('debit' in row_str or 'credit' in row_str or 'amount' in row_str):
                header_idx = idx
                break

        if header_idx == -1:
            header_idx = 0

        header = [h.strip().lower() for h in rows[header_idx]]

        def find_col(candidates):
            for c in candidates:
                for idx, h in enumerate(header):
                    if c in h:
                        return idx
            return -1

        date_col = find_col(['date', 'txn date', 'value date'])
        ref_col = find_col(['reference', 'ref', 'chq', 'cheque', 'trans no'])
        desc_col = find_col(['description', 'narration', 'particulars', 'details'])
        debit_col = find_col(['debit', 'dr', 'withdrawal', 'money out'])
        credit_col = find_col(['credit', 'cr', 'deposit', 'money in'])
        bal_col = find_col(['balance', 'running balance'])

        parsed_lines = []
        dates = []

        for row in rows[header_idx + 1:]:
            if not row or not any(row):
                continue
            if len(row) <= max(date_col, desc_col, 0):
                continue

            date_raw = row[date_col].strip() if date_col >= 0 and date_col < len(row) else ''
            ref = row[ref_col].strip() if ref_col >= 0 and ref_col < len(row) else ''
            desc = row[desc_col].strip() if desc_col >= 0 and desc_col < len(row) else 'Bank Transaction'

            txn_date = None
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d-%b-%Y']:
                try:
                    txn_date = datetime.strptime(date_raw, fmt).date()
                    break
                except ValueError:
                    pass
            if not txn_date:
                txn_date = timezone.localdate()
            dates.append(txn_date)

            dr_str = row[debit_col].strip().replace(',', '').replace(' ', '') if debit_col >= 0 and debit_col < len(row) else '0'
            cr_str = row[credit_col].strip().replace(',', '').replace(' ', '') if credit_col >= 0 and credit_col < len(row) else '0'

            try:
                debit_val = Decimal(dr_str) if dr_str else Decimal('0.00')
            except Exception:
                debit_val = Decimal('0.00')

            try:
                credit_val = Decimal(cr_str) if cr_str else Decimal('0.00')
            except Exception:
                credit_val = Decimal('0.00')

            # Bank statement: Credit = Deposit (+), Debit = Withdrawal (-)
            net_amount = credit_val - debit_val
            if net_amount == Decimal('0.00') and not ref:
                continue

            bal_str = row[bal_col].strip().replace(',', '').replace(' ', '') if bal_col >= 0 and bal_col < len(row) else None
            try:
                running_bal = Decimal(bal_str) if bal_str else None
            except Exception:
                running_bal = None

            parsed_lines.append({
                'date': txn_date,
                'reference': ref,
                'description': desc,
                'amount': net_amount,
                'balance': running_bal,
            })

        if not parsed_lines:
            raise ValidationError("No valid transaction rows found in bank statement.")

        start_date = min(dates) if dates else timezone.localdate()
        end_date = max(dates) if dates else timezone.localdate()

        statement = BankStatement.objects.create(
            company=bank_account.company,
            bank_account=bank_account,
            statement_date=end_date,
            start_date=start_date,
            end_date=end_date,
            opening_balance=parsed_lines[0]['balance'] - parsed_lines[0]['amount'] if parsed_lines[0]['balance'] is not None else Decimal('0.00'),
            closing_balance=parsed_lines[-1]['balance'] if parsed_lines[-1]['balance'] is not None else Decimal('0.00'),
        )

        for l in parsed_lines:
            BankStatementLine.objects.create(
                statement=statement,
                date=l['date'],
                reference=l['reference'],
                description=l['description'],
                amount=l['amount'],
                balance=l['balance'],
            )

        return statement

    @staticmethod
    @transaction.atomic
    def auto_reconcile(statement: BankStatement) -> Dict[str, int]:
        """
        Auto-reconciliation engine:
        1. Exact Reference Match: Matches statement line reference (M-Pesa code or Cheque #)
           to GL lines on the linked account.
        2. Amount + Date Window Match: Matches exact amount (+/- KES 0.00) within +/- 2 days.
        """
        from datetime import timedelta
        bank_account = statement.bank_account
        gl_account = bank_account.gl_account
        company = statement.company

        # Get all unreconciled GL lines for this account within reasonable window
        window_start = statement.start_date - timedelta(days=7)
        window_end = statement.end_date + timedelta(days=7)

        unreconciled_gl_lines = list(JournalEntryLine.objects.filter(
            entry__company=company,
            entry__status=JournalEntryStatus.POSTED,
            entry__date__gte=window_start,
            entry__date__lte=window_end,
            account=gl_account,
            matched_bank_lines__isnull=True
        ).select_related('entry'))

        matched_count = 0
        unmatched_count = 0

        for line in statement.lines.filter(is_reconciled=False):
            matched_gl = None

            # Rule 1: Exact reference match
            if line.reference:
                ref_clean = line.reference.strip().upper()
                for gl in unreconciled_gl_lines:
                    gl_ref = (gl.entry.source_ref or '').upper()
                    gl_desc = (gl.description or '').upper()
                    if ref_clean in gl_ref or ref_clean in gl_desc:
                        if (line.amount > 0 and gl.debit == line.amount) or \
                           (line.amount < 0 and gl.credit == abs(line.amount)):
                            matched_gl = gl
                            break

            # Rule 2: Exact Amount + Date Window (+/- 2 days)
            if not matched_gl:
                for gl in unreconciled_gl_lines:
                    date_diff = abs((gl.entry.date - line.date).days)
                    if date_diff <= 2:
                        if (line.amount > 0 and gl.debit == line.amount) or \
                           (line.amount < 0 and gl.credit == abs(line.amount)):
                            matched_gl = gl
                            break

            if matched_gl:
                line.is_reconciled = True
                line.matched_journal_line = matched_gl
                line.save(update_fields=['is_reconciled', 'matched_journal_line'])
                unreconciled_gl_lines.remove(matched_gl)
                matched_count += 1
            else:
                unmatched_count += 1

        return {
            'matched': matched_count,
            'unmatched': unmatched_count,
            'total': statement.lines.count()
        }

    @staticmethod
    def generate_reconciliation_report(
        bank_account: BankAccount,
        as_of_date: Optional[date] = None,
        statement: Optional[BankStatement] = None,
        user: Any = None
    ) -> BankReconciliation:
        """
        Computes formal Bank Reconciliation Statement:
        Statement Ending Balance + Uncredited Deposits - Unpresented Cheques/Payments = Adjusted GL Balance
        Difference vs General Ledger Balance.
        """
        as_of = as_of_date or timezone.localdate()
        company = bank_account.company
        gl_account = bank_account.gl_account

        from accounting.selectors import get_general_ledger
        gl_summary = get_general_ledger(
            company=company,
            account_codes=[gl_account.code],
            end_date=as_of
        )
        gl_ending = gl_summary.get('accounts', {}).get(gl_account.code, {}).get('ending_balance', Decimal('0.00'))

        stmt = statement or bank_account.statements.filter(end_date__lte=as_of).order_by('-end_date').first()
        stmt_ending = stmt.closing_balance if stmt else Decimal('0.00')

        unreconciled_deposits = Decimal('0.00')
        unreconciled_payments = Decimal('0.00')

        unreconciled_lines = JournalEntryLine.objects.filter(
            entry__company=company,
            entry__status=JournalEntryStatus.POSTED,
            entry__date__lte=as_of,
            account=gl_account,
            matched_bank_lines__isnull=True
        )

        for l in unreconciled_lines:
            unreconciled_deposits += l.debit
            unreconciled_payments += l.credit

        adjusted_balance = (stmt_ending + unreconciled_deposits - unreconciled_payments).quantize(Decimal('0.01'))
        difference = (adjusted_balance - gl_ending).quantize(Decimal('0.01'))
        is_balanced = (difference == Decimal('0.00'))

        recon, _ = BankReconciliation.objects.update_or_create(
            company=company,
            bank_account=bank_account,
            as_of_date=as_of,
            defaults={
                'statement': stmt,
                'statement_ending_balance': stmt_ending,
                'gl_ending_balance': gl_ending,
                'unreconciled_deposits': unreconciled_deposits,
                'unreconciled_payments': unreconciled_payments,
                'adjusted_gl_balance': adjusted_balance,
                'difference': difference,
                'is_balanced': is_balanced,
                'status': 'completed' if is_balanced else 'draft',
            }
        )

        return recon


class TaxService:
    """
    Kenyan Tax Engine for KRA (Kenya Revenue Authority) Compliance:
    - VAT Return Schedule (Form VAT 3): 16% Standard Rated, 0% Zero Rated, Exempt, Output/Input VAT, WHVAT.
    - Withholding Tax (WHT) Schedules: 5% (Management/Professional), 3% (Contractual), 10% (Rent), 2% (WHVAT).
    - KRA iTax CSV Exporters (Sales Schedule, Purchases Schedule, WHT Schedule).
    """

    @staticmethod
    def record_withholding_tax(
        company: Company,
        wht_type: str,
        category: str,
        party_name: str,
        transaction_date: date,
        base_amount: Decimal,
        rate_percentage: Decimal,
        party_pin: str = '',
        certificate_number: str = '',
        customer_invoice: Optional[CustomerInvoice] = None,
        vendor_bill: Optional[VendorBill] = None,
        journal_entry: Optional[JournalEntry] = None,
        notes: str = '',
        user: Any = None
    ) -> WithholdingTaxRecord:
        """
        Records a Withholding Tax or Withholding VAT certificate transaction.
        """
        tax_amount = (Decimal(str(base_amount)) * (Decimal(str(rate_percentage)) / Decimal('100.00'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        record = WithholdingTaxRecord.objects.create(
            company=company,
            wht_type=wht_type,
            category=category,
            party_name=party_name,
            party_pin=party_pin.strip().upper(),
            transaction_date=transaction_date,
            base_amount=Decimal(str(base_amount)).quantize(Decimal('0.01')),
            rate_percentage=Decimal(str(rate_percentage)).quantize(Decimal('0.01')),
            tax_amount=tax_amount,
            certificate_number=certificate_number.strip(),
            customer_invoice=customer_invoice,
            vendor_bill=vendor_bill,
            journal_entry=journal_entry,
            notes=notes,
            created_by=user if user and getattr(user, 'is_authenticated', False) else None
        )

        return record

    @staticmethod
    def generate_vat_return(
        company: Company,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Generates KRA Form VAT 3 Return Schedule for the given period.
        Aggregates:
        1. Sales:
           - Standard Rated (16%)
           - Zero Rated (0%)
           - Exempt (0%)
           - Total Output VAT
        2. Purchases:
           - Standard Rated (16%)
           - Zero Rated / Exempt
           - Total Claimable Input VAT
        3. Withholding VAT (2%):
           - WHVAT Credits (Withheld by Customers)
        4. Net VAT Payable / (Credit Carried Forward)
        """
        # 1. Output VAT & Sales from Customer Invoices
        invoices = CustomerInvoice.objects.filter(
            company=company,
            invoice_date__gte=start_date,
            invoice_date__lte=end_date,
            status__in=[InvoiceStatus.POSTED, InvoiceStatus.PARTIAL, InvoiceStatus.PAID]
        ).prefetch_related('lines', 'customer')

        sales_standard_taxable = Decimal('0.00')
        sales_zero_rated = Decimal('0.00')
        sales_exempt = Decimal('0.00')
        output_vat_invoices = Decimal('0.00')
        sales_schedule = []

        for inv in invoices:
            for line in inv.lines.all():
                qty = line.quantity or Decimal('1.00')
                subtotal = (qty * line.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                tax_amt = line.tax_amount or Decimal('0.00')
                rate = line.tax_rate or Decimal('0.00')

                if rate == Decimal('16.00'):
                    sales_standard_taxable += subtotal
                    output_vat_invoices += tax_amt
                elif rate == Decimal('0.00'):
                    sales_zero_rated += subtotal
                else:
                    sales_exempt += subtotal

                sales_schedule.append({
                    'customer_pin': inv.customer.kra_pin,
                    'customer_name': inv.customer.name,
                    'invoice_number': inv.invoice_number,
                    'invoice_date': inv.invoice_date,
                    'description': line.description,
                    'tax_rate': rate,
                    'taxable_amount': subtotal,
                    'vat_amount': tax_amt,
                    'total_amount': line.line_total,
                })

        # Also aggregate POS Sales from GL Account 2100 (VAT Output) if any directly posted
        pos_vat_output = Decimal('0.00')
        pos_taxable_sales = Decimal('0.00')
        pos_entries = JournalEntryLine.objects.filter(
            entry__company=company,
            entry__status=JournalEntryStatus.POSTED,
            entry__entry_type=JournalEntryType.SALES_CLOSE,
            entry__date__gte=start_date,
            entry__date__lte=end_date,
            account__code='2100'
        )
        for line in pos_entries:
            pos_vat_output += line.credit - line.debit
            if line.credit > 0:
                pos_taxable_sales += (line.credit / Decimal('0.16')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        total_sales_standard = sales_standard_taxable + pos_taxable_sales
        total_output_vat = output_vat_invoices + pos_vat_output
        total_gross_sales = total_sales_standard + sales_zero_rated + sales_exempt + total_output_vat

        # 2. Input VAT & Purchases from Vendor Bills
        bills = VendorBill.objects.filter(
            company=company,
            bill_date__gte=start_date,
            bill_date__lte=end_date,
            status__in=[BillStatus.POSTED, BillStatus.PARTIAL, BillStatus.PAID]
        ).prefetch_related('lines', 'vendor')

        purchases_standard_taxable = Decimal('0.00')
        purchases_zero_rated_exempt = Decimal('0.00')
        input_vat_bills = Decimal('0.00')
        purchases_schedule = []

        for b in bills:
            for line in b.lines.all():
                qty = line.quantity or Decimal('1.00')
                subtotal = (qty * line.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                tax_amt = line.tax_amount or Decimal('0.00')
                rate = line.tax_rate or Decimal('0.00')

                if rate == Decimal('16.00'):
                    purchases_standard_taxable += subtotal
                    input_vat_bills += tax_amt
                else:
                    purchases_zero_rated_exempt += subtotal

                purchases_schedule.append({
                    'supplier_pin': b.vendor.kra_pin,
                    'supplier_name': b.vendor.name,
                    'invoice_number': b.supplier_invoice_number or b.bill_number,
                    'bill_date': b.bill_date,
                    'description': line.description,
                    'tax_rate': rate,
                    'taxable_amount': subtotal,
                    'vat_amount': tax_amt,
                    'total_amount': line.line_total,
                })

        total_input_vat = input_vat_bills
        total_gross_purchases = purchases_standard_taxable + purchases_zero_rated_exempt + total_input_vat

        # 3. Withholding VAT (2%) Deducted / Claimable
        whvat_records = WithholdingTaxRecord.objects.filter(
            company=company,
            category=WHTCategory.WITHHOLDING_VAT,
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        )
        whvat_credits = Decimal('0.00')
        whvat_payable = Decimal('0.00')
        for rec in whvat_records:
            if rec.wht_type == WHTType.RECEIVABLE:
                whvat_credits += rec.tax_amount
            else:
                whvat_payable += rec.tax_amount

        # 4. Net VAT Calculation
        net_vat_payable = (total_output_vat - total_input_vat - whvat_credits).quantize(Decimal('0.01'))

        return {
            'company': company,
            'start_date': start_date,
            'end_date': end_date,
            'sales': {
                'standard_sales': total_sales_standard,
                'standard_16_taxable': total_sales_standard,
                'zero_rated_sales': sales_zero_rated,
                'zero_rated': sales_zero_rated,
                'exempt_sales': sales_exempt,
                'exempt': sales_exempt,
                'total_taxable_and_exempt': total_sales_standard + sales_zero_rated + sales_exempt,
                'output_vat_standard': total_output_vat,
                'output_vat': total_output_vat,
                'total_output_vat': total_output_vat,
                'total_sales': total_gross_sales,
                'total_gross_sales': total_gross_sales,
                'schedule': sales_schedule,
            },
            'purchases': {
                'standard_purchases': purchases_standard_taxable,
                'standard_16_taxable': purchases_standard_taxable,
                'zero_rated_purchases': purchases_zero_rated_exempt,
                'zero_rated_exempt': purchases_zero_rated_exempt,
                'exempt_purchases': Decimal('0.00'),
                'total_purchases_base': purchases_standard_taxable + purchases_zero_rated_exempt,
                'input_vat_standard': total_input_vat,
                'input_vat': total_input_vat,
                'total_input_vat': total_input_vat,
                'total_purchases': total_gross_purchases,
                'total_gross_purchases': total_gross_purchases,
                'schedule': purchases_schedule,
            },
            'whvat_credits': whvat_credits,
            'net_vat_payable': net_vat_payable,
            'withholding_vat': {
                'whvat_credits_receivable': whvat_credits,
                'whvat_retained_payable': whvat_payable,
            },
            'summary': {
                'total_output_vat': total_output_vat,
                'total_input_vat': total_input_vat,
                'whvat_credits': whvat_credits,
                'net_vat_payable': net_vat_payable if net_vat_payable > Decimal('0.00') else Decimal('0.00'),
                'credit_carried_forward': abs(net_vat_payable) if net_vat_payable < Decimal('0.00') else Decimal('0.00'),
                'is_payable': net_vat_payable > Decimal('0.00'),
            }
        }

    @staticmethod
    def generate_wht_return(
        company: Company,
        start_date: date,
        end_date: date,
        wht_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Aggregates Withholding Tax records for KRA reporting.
        """
        qs = WithholdingTaxRecord.objects.filter(
            company=company,
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        )
        if wht_type:
            qs = qs.filter(wht_type=wht_type)

        records = list(qs.select_related('customer_invoice', 'vendor_bill', 'journal_entry'))
        
        total_base = Decimal('0.00')
        total_tax = Decimal('0.00')
        total_withheld_by_us = Decimal('0.00')
        total_withheld_from_us = Decimal('0.00')
        category_breakdown: Dict[str, Dict[str, Any]] = {}

        for rec in records:
            total_base += rec.base_amount
            total_tax += rec.tax_amount
            if rec.wht_type == WHTType.PAYABLE:
                total_withheld_by_us += rec.tax_amount
            else:
                total_withheld_from_us += rec.tax_amount
            cat = rec.category
            if cat not in category_breakdown:
                category_breakdown[cat] = {
                    'category': cat,
                    'label': rec.get_category_display(),
                    'count': 0,
                    'base_amount': Decimal('0.00'),
                    'tax_amount': Decimal('0.00')
                }
            category_breakdown[cat]['count'] += 1
            category_breakdown[cat]['base_amount'] += rec.base_amount
            category_breakdown[cat]['tax_amount'] += rec.tax_amount

        return {
            'company': company,
            'start_date': start_date,
            'end_date': end_date,
            'total_base_amount': total_base,
            'total_tax_amount': total_tax,
            'totals': {
                'gross_amount': total_base,
                'wht_amount': total_tax,
                'total_withheld_by_us': total_withheld_by_us,
                'total_withheld_from_us': total_withheld_from_us,
            },
            'records': records,
            'categories': list(category_breakdown.values()),
        }

    @staticmethod
    def export_itax_vat_sales_csv(
        company: Company,
        start_date: date,
        end_date: date
    ) -> str:
        """
        Generates standard KRA iTax CSV upload format for Sales Schedule.
        Columns: PIN of Customer, Name of Customer, Invoice Date, Invoice Number, Description, Taxable Value, VAT Amount
        """
        vat_data = TaxService.generate_vat_return(company, start_date, end_date)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'PIN of Customer',
            'Name of Customer',
            'Invoice Date (DD/MM/YYYY)',
            'Invoice Number',
            'Description of Goods / Services',
            'Taxable Value (KES)',
            'VAT Amount (KES)'
        ])

        for line in vat_data['sales']['schedule']:
            inv_date = line['invoice_date'].strftime('%d/%m/%Y') if hasattr(line['invoice_date'], 'strftime') else str(line['invoice_date'])
            writer.writerow([
                line['customer_pin'] or 'N/A',
                line['customer_name'],
                inv_date,
                line['invoice_number'],
                line['description'],
                f"{line['taxable_amount']:.2f}",
                f"{line['vat_amount']:.2f}",
            ])

        return output.getvalue()

    @staticmethod
    def export_itax_vat_purchases_csv(
        company: Company,
        start_date: date,
        end_date: date
    ) -> str:
        """
        Generates standard KRA iTax CSV upload format for Purchases Schedule (Input VAT Claims).
        Columns: PIN of Supplier, Name of Supplier, Invoice Date, Invoice Number, Description, Taxable Value, VAT Amount
        """
        vat_data = TaxService.generate_vat_return(company, start_date, end_date)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'PIN of Supplier',
            'Name of Supplier',
            'Invoice Date (DD/MM/YYYY)',
            'Supplier Invoice Number',
            'Description of Goods / Services',
            'Taxable Value (KES)',
            'VAT Amount (KES)'
        ])

        for line in vat_data['purchases']['schedule']:
            b_date = line['bill_date'].strftime('%d/%m/%Y') if hasattr(line['bill_date'], 'strftime') else str(line['bill_date'])
            writer.writerow([
                line['supplier_pin'] or 'N/A',
                line['supplier_name'],
                b_date,
                line['invoice_number'],
                line['description'],
                f"{line['taxable_amount']:.2f}",
                f"{line['vat_amount']:.2f}",
            ])

        return output.getvalue()

    @staticmethod
    def export_itax_wht_csv(
        company: Company,
        start_date: date,
        end_date: date,
        wht_type: Optional[str] = None
    ) -> str:
        """
        Generates KRA iTax CSV upload format for Withholding Tax remittances.
        Columns: PIN of Payee, Payee Name, Nature of Transaction, Transaction Date, Certificate/Ref No, Gross Amount, Rate %, Tax Deducted
        """
        wht_data = TaxService.generate_wht_return(company, start_date, end_date, wht_type=wht_type)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'PIN of Payee',
            'Name of Payee',
            'Nature of Transaction',
            'Transaction Date (DD/MM/YYYY)',
            'Certificate / Ref Number',
            'Gross Taxable Amount (KES)',
            'Tax Rate (%)',
            'Tax Deducted (KES)'
        ])

        for rec in wht_data['records']:
            tx_date = rec.transaction_date.strftime('%d/%m/%Y') if hasattr(rec.transaction_date, 'strftime') else str(rec.transaction_date)
            writer.writerow([
                rec.party_pin or 'N/A',
                rec.party_name,
                rec.get_category_display(),
                tx_date,
                rec.certificate_number or 'N/A',
                f"{rec.base_amount:.2f}",
                f"{rec.rate_percentage:.2f}",
                f"{rec.tax_amount:.2f}",
            ])

        return output.getvalue()


