"""
Accounting & General Ledger Selectors (Read & Reporting Layer)
Standards: IFRS for SMEs / ICPAK Practice
"""
from decimal import Decimal
from datetime import date
from typing import Any, Dict, List, Optional
from django.db.models import Sum, Q, F, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.models.organization import Company, Branch
from accounting.models import (
    Account, AccountType, NormalBalance, AccountCategory,
    FiscalYear, FiscalPeriod,
    JournalEntry, JournalEntryLine, JournalEntryStatus,
    Customer, CustomerInvoice, InvoiceStatus,
    Vendor, VendorBill, BillStatus,
    BankAccount, BankReconciliation
)


class TrialBalanceSelector:
    """
    Computes the standard IFRS Trial Balance as of a specific date or period.
    Enforces strict mathematical invariant: Total Debits == Total Credits (Difference == 0.00).
    """

    @staticmethod
    def get_trial_balance(
        company: Company,
        as_of_date: Optional[date] = None,
        start_date: Optional[date] = None,
        branch: Optional[Branch] = None,
        cost_center: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates Trial Balance across all active accounts in the Chart of Accounts.

        Returns:
            Dict containing:
            - 'as_of_date': date
            - 'start_date': date or None
            - 'rows': List of account summary dicts
            - 'total_debits': Decimal
            - 'total_credits': Decimal
            - 'difference': Decimal (must be 0.00)
            - 'is_balanced': bool
        """
        if not as_of_date:
            as_of_date = timezone.localdate()

        accounts = Account.objects.filter(company=company, is_active=True).order_by('code')

        # Base filter for posted entries up to as_of_date
        base_line_filter = Q(
            entry__company=company,
            entry__status=JournalEntryStatus.POSTED,
            entry__date__lte=as_of_date
        )

        if branch:
            base_line_filter &= Q(entry__branch=branch) | Q(branch=branch)
        if cost_center:
            base_line_filter &= Q(cost_center=cost_center)

        rows = []
        grand_total_dr = Decimal('0.00')
        grand_total_cr = Decimal('0.00')

        for acct in accounts:
            # Lines in reporting period (or all up to as_of_date if no start_date)
            period_filter = base_line_filter
            if start_date:
                period_filter &= Q(entry__date__gte=start_date)

            aggs = JournalEntryLine.objects.filter(
                period_filter,
                account=acct
            ).aggregate(
                total_dr=Coalesce(Sum('debit'), Decimal('0.00')),
                total_cr=Coalesce(Sum('credit'), Decimal('0.00'))
            )

            dr_sum = aggs['total_dr']
            cr_sum = aggs['total_cr']

            # Opening balance if start_date is provided
            opening_balance = Decimal('0.00')
            if start_date:
                op_aggs = JournalEntryLine.objects.filter(
                    base_line_filter & Q(entry__date__lt=start_date),
                    account=acct
                ).aggregate(
                    op_dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    op_cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                if acct.normal_balance == NormalBalance.DEBIT:
                    opening_balance = op_aggs['op_dr'] - op_aggs['op_cr']
                else:
                    opening_balance = op_aggs['op_cr'] - op_aggs['op_dr']

            # Net Balance for Trial Balance column
            net_dr = Decimal('0.00')
            net_cr = Decimal('0.00')

            net_difference = dr_sum - cr_sum
            if net_difference > Decimal('0.00'):
                net_dr = net_difference
            elif net_difference < Decimal('0.00'):
                net_cr = abs(net_difference)

            # Accumulate totals
            grand_total_dr += net_dr
            grand_total_cr += net_cr

            # Skip accounts with 0 activity unless they have an opening balance
            if dr_sum == Decimal('0.00') and cr_sum == Decimal('0.00') and opening_balance == Decimal('0.00'):
                continue

            rows.append({
                'account_id': acct.id,
                'account_code': acct.code,
                'account_name': acct.name,
                'account_type': acct.account_type,
                'account_type_display': acct.get_account_type_display(),
                'category': acct.get_category_display(),
                'normal_balance': acct.normal_balance,
                'opening_balance': opening_balance,
                'period_debits': dr_sum,
                'period_credits': cr_sum,
                'closing_debit': net_dr,
                'closing_credit': net_cr,
            })

        difference = abs(grand_total_dr - grand_total_cr)
        is_balanced = round(difference, 2) == Decimal('0.00')

        return {
            'company': company,
            'as_of_date': as_of_date,
            'start_date': start_date,
            'rows': rows,
            'total_debits': grand_total_dr,
            'total_credits': grand_total_cr,
            'difference': difference,
            'is_balanced': is_balanced,
        }


def get_general_ledger(
    company: Company,
    account: Optional[Account] = None,
    account_id: Optional[int] = None,
    account_codes: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    branch: Optional[Branch] = None,
) -> Dict[str, Any]:
    """
    General Ledger query function supporting both single account detail and multi-account code maps.
    """
    if account_codes:
        acc = Account.objects.filter(company=company, code__in=account_codes).first()
        res = GeneralLedgerSelector.get_account_ledger(company, account=acc, start_date=start_date, end_date=end_date, branch=branch)
        return {
            'accounts': {
                acc.code: {'ending_balance': res['closing_balance']} if acc else {'ending_balance': Decimal('0.00')}
            }
        }
    return GeneralLedgerSelector.get_account_ledger(company, account=account, account_id=account_id, start_date=start_date, end_date=end_date, branch=branch)


class GeneralLedgerSelector:
    """
    Returns itemized General Ledger account transaction history with running balances.
    """

    @staticmethod
    def get_account_ledger(
        company: Company,
        account: Optional[Account] = None,
        account_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        branch: Optional[Branch] = None,
    ) -> Dict[str, Any]:
        """Fetch chronological journal line transactions for an account with running balance."""
        if not account and account_id:
            account = Account.objects.get(company=company, pk=account_id)

        if not account:
            return {'account': None, 'entries': [], 'opening_balance': Decimal('0.00'), 'closing_balance': Decimal('0.00')}

        if not end_date:
            end_date = timezone.localdate()

        lines_qs = JournalEntryLine.objects.filter(
            entry__company=company,
            entry__status=JournalEntryStatus.POSTED,
            entry__date__lte=end_date,
            account=account
        ).select_related('entry', 'branch', 'entry__posted_by').order_by('entry__date', 'entry__id')

        if branch:
            lines_qs = lines_qs.filter(Q(entry__branch=branch) | Q(branch=branch))

        # Opening balance prior to start_date
        opening_balance = Decimal('0.00')
        if start_date:
            op_aggs = JournalEntryLine.objects.filter(
                entry__company=company,
                entry__status=JournalEntryStatus.POSTED,
                entry__date__lt=start_date,
                account=account
            ).aggregate(
                total_dr=Coalesce(Sum('debit'), Decimal('0.00')),
                total_cr=Coalesce(Sum('credit'), Decimal('0.00'))
            )
            if account.normal_balance == NormalBalance.DEBIT:
                opening_balance = op_aggs['total_dr'] - op_aggs['total_cr']
            else:
                opening_balance = op_aggs['total_cr'] - op_aggs['total_dr']

            lines_qs = lines_qs.filter(entry__date__gte=start_date)

        running_bal = opening_balance
        ledger_lines = []
        period_dr = Decimal('0.00')
        period_cr = Decimal('0.00')

        for line in lines_qs:
            dr = line.debit
            cr = line.credit
            period_dr += dr
            period_cr += cr

            if account.normal_balance == NormalBalance.DEBIT:
                running_bal += (dr - cr)
            else:
                running_bal += (cr - dr)

            ledger_lines.append({
                'id': line.id,
                'date': line.entry.date,
                'entry_id': line.entry.id,
                'entry_number': line.entry.entry_number,
                'entry_type': line.entry.get_entry_type_display(),
                'source_module': line.entry.source_module,
                'source_ref': line.entry.source_ref,
                'narration': line.entry.narration,
                'line_description': line.description or line.entry.narration,
                'debit': dr,
                'credit': cr,
                'running_balance': running_bal,
                'branch_name': line.branch.name if line.branch else (line.entry.branch.name if line.entry.branch else 'HQ / Company'),
            })

        return {
            'account': account,
            'start_date': start_date,
            'end_date': end_date,
            'opening_balance': opening_balance,
            'period_debits': period_dr,
            'period_credits': period_cr,
            'closing_balance': running_bal,
            'transactions': ledger_lines,
            'entries': ledger_lines,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# SUBLEDGER AGING & RECONCILIATION SELECTORS
# ═══════════════════════════════════════════════════════════════════════════════

def get_ar_aging_report(
    company: Company,
    as_of_date: Optional[date] = None,
    customer_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Accounts Receivable Aging Report.
    Buckets open/partially-paid customer invoices by days overdue:
    - Current (due in future or due today)
    - 1 - 30 Days overdue
    - 31 - 60 Days overdue
    - 61 - 90 Days overdue
    - 90+ Days overdue
    """
    if not as_of_date:
        as_of_date = timezone.localdate()

    invoices = CustomerInvoice.objects.filter(
        company=company,
        status__in=[InvoiceStatus.POSTED, InvoiceStatus.PARTIAL],
        invoice_date__lte=as_of_date,
        balance_due__gt=0
    ).select_related('customer', 'branch')

    if customer_id:
        invoices = invoices.filter(customer_id=customer_id)

    customer_buckets: Dict[int, Dict[str, Any]] = {}
    grand_totals = {
        'current': Decimal('0.00'),
        'days_1_30': Decimal('0.00'),
        'days_31_60': Decimal('0.00'),
        'days_61_90': Decimal('0.00'),
        'days_over_90': Decimal('0.00'),
        'total_due': Decimal('0.00'),
    }

    for inv in invoices:
        cust = inv.customer
        if cust.id not in customer_buckets:
            customer_buckets[cust.id] = {
                'customer_id': cust.id,
                'customer_name': cust.name,
                'kra_pin': cust.kra_pin,
                'phone': cust.phone,
                'current': Decimal('0.00'),
                'days_1_30': Decimal('0.00'),
                'days_31_60': Decimal('0.00'),
                'days_61_90': Decimal('0.00'),
                'days_over_90': Decimal('0.00'),
                'total_due': Decimal('0.00'),
                'invoices': [],
            }

        due_date = inv.due_date
        overdue_days = (as_of_date - due_date).days
        bal = inv.balance_due

        bucket_key = 'current'
        if overdue_days <= 0:
            bucket_key = 'current'
        elif overdue_days <= 30:
            bucket_key = 'days_1_30'
        elif overdue_days <= 60:
            bucket_key = 'days_31_60'
        elif overdue_days <= 90:
            bucket_key = 'days_61_90'
        else:
            bucket_key = 'days_over_90'

        customer_buckets[cust.id][bucket_key] += bal
        customer_buckets[cust.id]['total_due'] += bal
        customer_buckets[cust.id]['invoices'].append({
            'invoice_id': inv.id,
            'invoice_number': inv.invoice_number,
            'invoice_date': inv.invoice_date,
            'due_date': inv.due_date,
            'overdue_days': max(0, overdue_days),
            'total_amount': inv.total_amount,
            'amount_paid': inv.amount_paid,
            'balance_due': bal,
            'bucket': bucket_key,
        })

        grand_totals[bucket_key] += bal
        grand_totals['total_due'] += bal

    return {
        'as_of_date': as_of_date,
        'customers': list(customer_buckets.values()),
        'totals': grand_totals,
    }


def get_ap_aging_report(
    company: Company,
    as_of_date: Optional[date] = None,
    vendor_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Accounts Payable Aging Report.
    Buckets open/partially-paid vendor bills by days overdue:
    - Current (due in future or due today)
    - 1 - 30 Days overdue
    - 31 - 60 Days overdue
    - 61 - 90 Days overdue
    - 90+ Days overdue
    """
    if not as_of_date:
        as_of_date = timezone.localdate()

    bills = VendorBill.objects.filter(
        company=company,
        status__in=[BillStatus.POSTED, BillStatus.PARTIAL],
        bill_date__lte=as_of_date,
        balance_due__gt=0
    ).select_related('vendor', 'branch')

    if vendor_id:
        bills = bills.filter(vendor_id=vendor_id)

    vendor_buckets: Dict[int, Dict[str, Any]] = {}
    grand_totals = {
        'current': Decimal('0.00'),
        'days_1_30': Decimal('0.00'),
        'days_31_60': Decimal('0.00'),
        'days_61_90': Decimal('0.00'),
        'days_over_90': Decimal('0.00'),
        'total_due': Decimal('0.00'),
    }

    for b in bills:
        vend = b.vendor
        if vend.id not in vendor_buckets:
            vendor_buckets[vend.id] = {
                'vendor_id': vend.id,
                'vendor_name': vend.name,
                'kra_pin': vend.kra_pin,
                'phone': vend.phone,
                'current': Decimal('0.00'),
                'days_1_30': Decimal('0.00'),
                'days_31_60': Decimal('0.00'),
                'days_61_90': Decimal('0.00'),
                'days_over_90': Decimal('0.00'),
                'total_due': Decimal('0.00'),
                'bills': [],
            }

        due_date = b.due_date
        overdue_days = (as_of_date - due_date).days
        bal = b.balance_due

        bucket_key = 'current'
        if overdue_days <= 0:
            bucket_key = 'current'
        elif overdue_days <= 30:
            bucket_key = 'days_1_30'
        elif overdue_days <= 60:
            bucket_key = 'days_31_60'
        elif overdue_days <= 90:
            bucket_key = 'days_61_90'
        else:
            bucket_key = 'days_over_90'

        vendor_buckets[vend.id][bucket_key] += bal
        vendor_buckets[vend.id]['total_due'] += bal
        vendor_buckets[vend.id]['bills'].append({
            'bill_id': b.id,
            'bill_number': b.bill_number,
            'supplier_invoice_number': b.supplier_invoice_number,
            'bill_date': b.bill_date,
            'due_date': b.due_date,
            'overdue_days': max(0, overdue_days),
            'total_amount': b.total_amount,
            'amount_paid': b.amount_paid,
            'balance_due': bal,
            'bucket': bucket_key,
        })

        grand_totals[bucket_key] += bal
        grand_totals['total_due'] += bal

    return {
        'as_of_date': as_of_date,
        'vendors': list(vendor_buckets.values()),
        'totals': grand_totals,
    }


def get_bank_reconciliation_summary(
    bank_account: BankAccount,
    as_of_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Calculates detailed live bank reconciliation balances for a given Bank / M-Pesa account.
    """
    from accounting.services import BankReconciliationService
    recon = BankReconciliationService.generate_reconciliation_report(
        bank_account=bank_account,
        as_of_date=as_of_date
    )
    return {
        'bank_account': bank_account,
        'as_of_date': recon.as_of_date,
        'statement_ending_balance': recon.statement_ending_balance,
        'gl_ending_balance': recon.gl_ending_balance,
        'unreconciled_deposits': recon.unreconciled_deposits,
        'unreconciled_payments': recon.unreconciled_payments,
        'adjusted_gl_balance': recon.adjusted_gl_balance,
        'difference': recon.difference,
        'is_balanced': recon.is_balanced,
        'status': recon.status,
    }


def get_vat_return_summary(
    company: Company,
    start_date: date,
    end_date: date
) -> Dict[str, Any]:
    """
    KRA Form VAT 3 return calculation and schedules.
    """
    from accounting.services import TaxService
    return TaxService.generate_vat_return(company=company, start_date=start_date, end_date=end_date)


def get_wht_return_summary(
    company: Company,
    start_date: date,
    end_date: date,
    wht_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Withholding Tax and WHVAT return summary and breakdown.
    """
    from accounting.services import TaxService
    return TaxService.generate_wht_return(company=company, start_date=start_date, end_date=end_date, wht_type=wht_type)


# ─── FINANCIAL STATEMENTS SELECTORS ─────────────────────────────────────────

def get_income_statement(
    company: Company,
    start_date: date,
    end_date: date,
    branch: Optional[Branch] = None,
    compare_start_date: Optional[date] = None,
    compare_end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    IFRS Multi-Period Income Statement (Profit & Loss / P&L).
    """
    return IncomeStatementSelector.get_income_statement(
        company=company,
        start_date=start_date,
        end_date=end_date,
        branch=branch,
        compare_start_date=compare_start_date,
        compare_end_date=compare_end_date,
    )


def get_balance_sheet(
    company: Company,
    as_of_date: Optional[date] = None,
    branch: Optional[Branch] = None,
    compare_as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Classified Balance Sheet (Statement of Financial Position).
    """
    return BalanceSheetSelector.get_balance_sheet(
        company=company,
        as_of_date=as_of_date,
        branch=branch,
        compare_as_of_date=compare_as_of_date,
    )


def get_cash_flow_statement(
    company: Company,
    start_date: date,
    end_date: date,
    branch: Optional[Branch] = None
) -> Dict[str, Any]:
    """
    Statement of Cash Flows via Indirect Method (IAS 7 / IFRS).
    """
    return CashFlowStatementSelector.get_cash_flow_statement(
        company=company,
        start_date=start_date,
        end_date=end_date,
        branch=branch,
    )


class IncomeStatementSelector:
    """
    Computes IFRS-compliant Income Statement (Profit & Loss / P&L) for a given reporting period.
    """

    @staticmethod
    def get_income_statement(
        company: Company,
        start_date: date,
        end_date: date,
        branch: Optional[Branch] = None,
        compare_start_date: Optional[date] = None,
        compare_end_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        def _calc_period_pnl(p_start: date, p_end: date) -> Dict[str, Any]:
            base_filter = Q(
                entry__company=company,
                entry__status=JournalEntryStatus.POSTED,
                entry__date__gte=p_start,
                entry__date__lte=p_end
            )
            if branch:
                base_filter &= Q(entry__branch=branch) | Q(branch=branch)

            # 1. Operating Revenue & Discounts
            rev_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.INCOME,
                category__in=[AccountCategory.OPERATING_REVENUE, AccountCategory.SALES_DISCOUNT]
            ).order_by('code')

            gross_sales_rows = []
            discount_rows = []
            gross_revenue = Decimal('0.00')
            total_discounts = Decimal('0.00')

            for acct in rev_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                if acct.category == AccountCategory.SALES_DISCOUNT:
                    amt = aggs['dr'] - aggs['cr']
                    if amt != Decimal('0.00'):
                        total_discounts += amt
                        discount_rows.append({'account': acct, 'amount': amt})
                else:
                    amt = aggs['cr'] - aggs['dr']
                    if amt != Decimal('0.00') or acct.code == '4000':
                        gross_revenue += amt
                        gross_sales_rows.append({'account': acct, 'amount': amt})

            net_revenue = (gross_revenue - total_discounts).quantize(Decimal('0.01'))

            # 2. Cost of Sales (COGS)
            cogs_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.EXPENSE,
                category=AccountCategory.COST_OF_SALES
            ).order_by('code')

            cogs_rows = []
            total_cogs = Decimal('0.00')
            for acct in cogs_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                amt = aggs['dr'] - aggs['cr']
                if amt != Decimal('0.00') or acct.code == '5000':
                    total_cogs += amt
                    cogs_rows.append({'account': acct, 'amount': amt})

            gross_profit = (net_revenue - total_cogs).quantize(Decimal('0.01'))
            gross_margin_pct = (gross_profit / net_revenue * Decimal('100.00')).quantize(Decimal('0.01')) if net_revenue > Decimal('0.00') else Decimal('0.00')

            # 3. Operating Expenses
            opex_categories = [
                AccountCategory.PAYROLL_EXPENSE,
                AccountCategory.OPERATING_EXPENSE,
                AccountCategory.FINANCIAL_EXPENSE,
                AccountCategory.DEPRECIATION_EXPENSE,
            ]
            opex_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.EXPENSE,
                category__in=opex_categories
            ).order_by('code')

            opex_rows = []
            total_opex = Decimal('0.00')
            for acct in opex_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                amt = aggs['dr'] - aggs['cr']
                if amt != Decimal('0.00'):
                    total_opex += amt
                    opex_rows.append({'account': acct, 'amount': amt})

            operating_profit = (gross_profit - total_opex).quantize(Decimal('0.01'))
            ebit_margin_pct = (operating_profit / net_revenue * Decimal('100.00')).quantize(Decimal('0.01')) if net_revenue > Decimal('0.00') else Decimal('0.00')

            # 4. Other Income & Finance Costs
            other_inc_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.INCOME,
                category=AccountCategory.OTHER_INCOME
            ).order_by('code')
            other_income_rows = []
            total_other_income = Decimal('0.00')
            for acct in other_inc_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                amt = aggs['cr'] - aggs['dr']
                if amt != Decimal('0.00'):
                    total_other_income += amt
                    other_income_rows.append({'account': acct, 'amount': amt})

            # 5. Income Tax Expense (8100)
            tax_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.EXPENSE,
                category=AccountCategory.TAX_EXPENSE
            ).order_by('code')
            tax_rows = []
            total_tax_expense = Decimal('0.00')
            for acct in tax_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                amt = aggs['dr'] - aggs['cr']
                if amt != Decimal('0.00'):
                    total_tax_expense += amt
                    tax_rows.append({'account': acct, 'amount': amt})

            profit_before_tax = (operating_profit + total_other_income).quantize(Decimal('0.01'))
            net_profit = (profit_before_tax - total_tax_expense).quantize(Decimal('0.01'))
            net_margin_pct = (net_profit / net_revenue * Decimal('100.00')).quantize(Decimal('0.01')) if net_revenue > Decimal('0.00') else Decimal('0.00')

            return {
                'start_date': p_start,
                'end_date': p_end,
                'gross_revenue': gross_revenue,
                'gross_sales_rows': gross_sales_rows,
                'total_discounts': total_discounts,
                'discount_rows': discount_rows,
                'net_revenue': net_revenue,
                'total_cogs': total_cogs,
                'cogs_rows': cogs_rows,
                'gross_profit': gross_profit,
                'gross_margin_pct': gross_margin_pct,
                'total_opex': total_opex,
                'opex_rows': opex_rows,
                'operating_profit': operating_profit,
                'ebit_margin_pct': ebit_margin_pct,
                'total_other_income': total_other_income,
                'other_income_rows': other_income_rows,
                'profit_before_tax': profit_before_tax,
                'total_tax_expense': total_tax_expense,
                'tax_rows': tax_rows,
                'net_profit': net_profit,
                'net_margin_pct': net_margin_pct,
            }

        primary = _calc_period_pnl(start_date, end_date)
        comparative = None
        if compare_start_date and compare_end_date:
            comparative = _calc_period_pnl(compare_start_date, compare_end_date)

        return {
            'company': company,
            'branch': branch,
            'primary': primary,
            'comparative': comparative,
            'is_comparative': comparative is not None,
        }


class BalanceSheetSelector:
    """
    Computes Classified Statement of Financial Position (Balance Sheet) per IFRS.
    Assets = Liabilities + Equity (Mathematical Invariant: Difference == 0.00).
    """

    @staticmethod
    def get_balance_sheet(
        company: Company,
        as_of_date: Optional[date] = None,
        branch: Optional[Branch] = None,
        compare_as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        if not as_of_date:
            as_of_date = timezone.localdate()

        def _calc_sheet(target_date: date) -> Dict[str, Any]:
            base_filter = Q(
                entry__company=company,
                entry__status=JournalEntryStatus.POSTED,
                entry__date__lte=target_date
            )
            if branch:
                base_filter &= Q(entry__branch=branch) | Q(branch=branch)

            # ── 1. ASSETS ──
            current_asset_cats = [
                AccountCategory.CASH_AND_BANK,
                AccountCategory.ACCOUNTS_RECEIVABLE,
                AccountCategory.INVENTORY,
                AccountCategory.STATUTORY_TAX_ASSET,
                AccountCategory.CURRENT_ASSET,
            ]
            current_asset_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.ASSET,
                category__in=current_asset_cats
            ).order_by('code')

            current_assets_rows = []
            total_current_assets = Decimal('0.00')
            for acct in current_asset_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                if acct.normal_balance == NormalBalance.DEBIT:
                    bal = aggs['dr'] - aggs['cr']
                else:
                    bal = aggs['cr'] - aggs['dr']
                
                if bal != Decimal('0.00') or acct.code in ['1010', '1030', '1040', '1100', '1200']:
                    current_assets_rows.append({'account': acct, 'balance': bal})
                    total_current_assets += bal if acct.normal_balance == NormalBalance.DEBIT else -bal

            fixed_asset_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.ASSET,
                category__in=[AccountCategory.FIXED_ASSET, AccountCategory.ACCUMULATED_DEPRECIATION]
            ).order_by('code')

            fixed_assets_rows = []
            total_fixed_assets = Decimal('0.00')
            for acct in fixed_asset_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                if acct.category == AccountCategory.ACCUMULATED_DEPRECIATION:
                    bal = aggs['cr'] - aggs['dr']
                    if bal != Decimal('0.00') or acct.code == '1590':
                        fixed_assets_rows.append({'account': acct, 'balance': -bal})
                        total_fixed_assets -= bal
                else:
                    bal = aggs['dr'] - aggs['cr']
                    if bal != Decimal('0.00') or acct.code == '1500':
                        fixed_assets_rows.append({'account': acct, 'balance': bal})
                        total_fixed_assets += bal

            total_assets = (total_current_assets + total_fixed_assets).quantize(Decimal('0.01'))

            # ── 2. LIABILITIES ──
            current_liab_cats = [
                AccountCategory.CURRENT_LIABILITY,
                AccountCategory.ACCOUNTS_PAYABLE,
                AccountCategory.STATUTORY_TAX_LIABILITY,
                AccountCategory.PAYROLL_CLEARING,
            ]
            current_liab_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.LIABILITY,
                category__in=current_liab_cats
            ).order_by('code')

            current_liab_rows = []
            total_current_liabilities = Decimal('0.00')
            for acct in current_liab_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                bal = aggs['cr'] - aggs['dr']
                if bal != Decimal('0.00') or acct.code in ['2000', '2100']:
                    current_liab_rows.append({'account': acct, 'balance': bal})
                    total_current_liabilities += bal

            long_liab_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.LIABILITY,
                category=AccountCategory.LONG_TERM_LIABILITY
            ).order_by('code')

            long_liab_rows = []
            total_long_liabilities = Decimal('0.00')
            for acct in long_liab_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                bal = aggs['cr'] - aggs['dr']
                if bal != Decimal('0.00'):
                    long_liab_rows.append({'account': acct, 'balance': bal})
                    total_long_liabilities += bal

            total_liabilities = (total_current_liabilities + total_long_liabilities).quantize(Decimal('0.01'))

            # ── 3. EQUITY ──
            equity_accounts = Account.objects.filter(
                company=company,
                account_type=AccountType.EQUITY
            ).order_by('code')

            equity_rows = []
            total_equity_base = Decimal('0.00')
            for acct in equity_accounts:
                aggs = JournalEntryLine.objects.filter(base_filter, account=acct).aggregate(
                    dr=Coalesce(Sum('debit'), Decimal('0.00')),
                    cr=Coalesce(Sum('credit'), Decimal('0.00'))
                )
                if acct.category == AccountCategory.OWNER_DRAWING:
                    bal = aggs['dr'] - aggs['cr']
                    if bal != Decimal('0.00'):
                        equity_rows.append({'account': acct, 'balance': -bal})
                        total_equity_base -= bal
                else:
                    bal = aggs['cr'] - aggs['dr']
                    if bal != Decimal('0.00') or acct.code in ['3000', '3100']:
                        equity_rows.append({'account': acct, 'balance': bal})
                        total_equity_base += bal

            pnl_aggs = JournalEntryLine.objects.filter(
                base_filter,
                account__account_type__in=[AccountType.INCOME, AccountType.EXPENSE]
            ).aggregate(
                total_income_cr=Coalesce(Sum('credit', filter=Q(account__account_type=AccountType.INCOME)), Decimal('0.00')),
                total_income_dr=Coalesce(Sum('debit', filter=Q(account__account_type=AccountType.INCOME)), Decimal('0.00')),
                total_expense_dr=Coalesce(Sum('debit', filter=Q(account__account_type=AccountType.EXPENSE)), Decimal('0.00')),
                total_expense_cr=Coalesce(Sum('credit', filter=Q(account__account_type=AccountType.EXPENSE)), Decimal('0.00'))
            )
            net_period_income = ((pnl_aggs['total_income_cr'] - pnl_aggs['total_income_dr']) - 
                                (pnl_aggs['total_expense_dr'] - pnl_aggs['total_expense_cr'])).quantize(Decimal('0.01'))

            total_equity = (total_equity_base + net_period_income).quantize(Decimal('0.01'))
            total_liabilities_and_equity = (total_liabilities + total_equity).quantize(Decimal('0.01'))
            difference = abs(total_assets - total_liabilities_and_equity).quantize(Decimal('0.01'))
            is_balanced = (difference == Decimal('0.00'))

            return {
                'as_of_date': target_date,
                'current_assets': {
                    'rows': current_assets_rows,
                    'total': total_current_assets,
                },
                'fixed_assets': {
                    'rows': fixed_assets_rows,
                    'total': total_fixed_assets,
                },
                'total_assets': total_assets,
                'current_liabilities': {
                    'rows': current_liab_rows,
                    'total': total_current_liabilities,
                },
                'long_term_liabilities': {
                    'rows': long_liab_rows,
                    'total': total_long_liabilities,
                },
                'total_liabilities': total_liabilities,
                'equity': {
                    'rows': equity_rows,
                    'current_period_net_income': net_period_income,
                    'total': total_equity,
                },
                'total_liabilities_and_equity': total_liabilities_and_equity,
                'difference': difference,
                'is_balanced': is_balanced,
            }

        primary = _calc_sheet(as_of_date)
        comparative = None
        if compare_as_of_date:
            comparative = _calc_sheet(compare_as_of_date)

        return {
            'company': company,
            'branch': branch,
            'primary': primary,
            'comparative': comparative,
            'is_comparative': comparative is not None,
        }


class CashFlowStatementSelector:
    """
    Computes Statement of Cash Flows via Indirect Method per IAS 7.
    """

    @staticmethod
    def get_cash_flow_statement(
        company: Company,
        start_date: date,
        end_date: date,
        branch: Optional[Branch] = None
    ) -> Dict[str, Any]:
        from datetime import timedelta
        prior_date = start_date - timedelta(days=1)

        # 1. Operating Activities: Net Profit Before Tax
        pnl_data = IncomeStatementSelector.get_income_statement(company, start_date=start_date, end_date=end_date, branch=branch)['primary']
        net_profit_before_tax = pnl_data['profit_before_tax']

        base_period_filter = Q(
            entry__company=company,
            entry__status=JournalEntryStatus.POSTED,
            entry__date__gte=start_date,
            entry__date__lte=end_date
        )
        if branch:
            base_period_filter &= Q(entry__branch=branch) | Q(branch=branch)

        deprec_aggs = JournalEntryLine.objects.filter(
            base_period_filter,
            account__category=AccountCategory.DEPRECIATION_EXPENSE
        ).aggregate(dr=Coalesce(Sum('debit'), Decimal('0.00')), cr=Coalesce(Sum('credit'), Decimal('0.00')))
        depreciation_addback = (deprec_aggs['dr'] - deprec_aggs['cr']).quantize(Decimal('0.01'))

        def _get_acct_bal(codes, target_date):
            aggs = JournalEntryLine.objects.filter(
                entry__company=company,
                entry__status=JournalEntryStatus.POSTED,
                entry__date__lte=target_date,
                account__code__in=codes
            ).aggregate(dr=Coalesce(Sum('debit'), Decimal('0.00')), cr=Coalesce(Sum('credit'), Decimal('0.00')))
            return aggs['dr'] - aggs['cr']

        def _get_liab_bal(codes, target_date):
            aggs = JournalEntryLine.objects.filter(
                entry__company=company,
                entry__status=JournalEntryStatus.POSTED,
                entry__date__lte=target_date,
                account__code__in=codes
            ).aggregate(dr=Coalesce(Sum('debit'), Decimal('0.00')), cr=Coalesce(Sum('credit'), Decimal('0.00')))
            return aggs['cr'] - aggs['dr']

        beg_ar = _get_acct_bal(['1100', '1110'], prior_date)
        end_ar = _get_acct_bal(['1100', '1110'], end_date)
        delta_ar = -(end_ar - beg_ar)

        beg_inv = _get_acct_bal(['1200', '1250'], prior_date)
        end_inv = _get_acct_bal(['1200', '1250'], end_date)
        delta_inv = -(end_inv - beg_inv)

        beg_prepay = _get_acct_bal(['1300', '1310', '1400', '1410', '1420'], prior_date)
        end_prepay = _get_acct_bal(['1300', '1310', '1400', '1410', '1420'], end_date)
        delta_prepay = -(end_prepay - beg_prepay)

        beg_ap = _get_liab_bal(['2000'], prior_date)
        end_ap = _get_liab_bal(['2000'], end_date)
        delta_ap = +(end_ap - beg_ap)

        stat_codes = ['2100', '2110', '2120', '2130', '2140', '2150', '2160', '2200', '2210']
        beg_stat = _get_liab_bal(stat_codes, prior_date)
        end_stat = _get_liab_bal(stat_codes, end_date)
        delta_stat = +(end_stat - beg_stat)

        cash_from_operations = (net_profit_before_tax + depreciation_addback + delta_ar + delta_inv + delta_prepay + delta_ap + delta_stat).quantize(Decimal('0.01'))

        # 2. Investing Activities: PPE purchase cash outflow
        ppe_aggs = JournalEntryLine.objects.filter(
            base_period_filter,
            account__category=AccountCategory.FIXED_ASSET
        ).aggregate(dr=Coalesce(Sum('debit'), Decimal('0.00')), cr=Coalesce(Sum('credit'), Decimal('0.00')))
        ppe_additions = -(ppe_aggs['dr'] - ppe_aggs['cr']).quantize(Decimal('0.01'))
        cash_from_investing = ppe_additions

        # 3. Financing Activities: Owner Capital Injections, Drawings, and Loans
        equity_aggs = JournalEntryLine.objects.filter(
            base_period_filter,
            account__category=AccountCategory.EQUITY
        ).aggregate(dr=Coalesce(Sum('debit'), Decimal('0.00')), cr=Coalesce(Sum('credit'), Decimal('0.00')))
        capital_injections = (equity_aggs['cr'] - equity_aggs['dr']).quantize(Decimal('0.01'))

        drawings_aggs = JournalEntryLine.objects.filter(
            base_period_filter,
            account__category=AccountCategory.OWNER_DRAWING
        ).aggregate(dr=Coalesce(Sum('debit'), Decimal('0.00')), cr=Coalesce(Sum('credit'), Decimal('0.00')))
        drawings_paid = -(drawings_aggs['dr'] - drawings_aggs['cr']).quantize(Decimal('0.01'))

        loan_aggs = JournalEntryLine.objects.filter(
            base_period_filter,
            account__category=AccountCategory.LONG_TERM_LIABILITY
        ).aggregate(dr=Coalesce(Sum('debit'), Decimal('0.00')), cr=Coalesce(Sum('credit'), Decimal('0.00')))
        loan_delta = (loan_aggs['cr'] - loan_aggs['dr']).quantize(Decimal('0.01'))

        cash_from_financing = (capital_injections + drawings_paid + loan_delta).quantize(Decimal('0.01'))

        net_cash_change = (cash_from_operations + cash_from_investing + cash_from_financing).quantize(Decimal('0.01'))

        cash_codes = ['1010', '1020', '1030', '1040', '1050']
        beginning_cash = _get_acct_bal(cash_codes, prior_date).quantize(Decimal('0.01'))
        ending_cash_computed = (beginning_cash + net_cash_change).quantize(Decimal('0.01'))
        ending_cash_actual = _get_acct_bal(cash_codes, end_date).quantize(Decimal('0.01'))

        difference = abs(ending_cash_computed - ending_cash_actual).quantize(Decimal('0.01'))
        is_reconciled = (difference == Decimal('0.00'))

        return {
            'company': company,
            'start_date': start_date,
            'end_date': end_date,
            'operating_activities': {
                'net_profit_before_tax': net_profit_before_tax,
                'depreciation_addback': depreciation_addback,
                'delta_ar': delta_ar,
                'delta_inv': delta_inv,
                'delta_prepayments': delta_prepay,
                'delta_ap': delta_ap,
                'delta_statutory_and_accruals': delta_stat,
                'net_cash_from_operations': cash_from_operations,
            },
            'investing_activities': {
                'ppe_additions': ppe_additions,
                'net_cash_from_investing': cash_from_investing,
            },
            'financing_activities': {
                'drawings_paid': drawings_paid,
                'loan_delta': loan_delta,
                'net_cash_from_financing': cash_from_financing,
            },
            'summary': {
                'net_cash_change': net_cash_change,
                'beginning_cash': beginning_cash,
                'ending_cash_computed': ending_cash_computed,
                'ending_cash_actual': ending_cash_actual,
                'difference': difference,
                'is_reconciled': is_reconciled,
            }
        }



