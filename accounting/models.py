"""
Accounting & General Ledger Models for Marid ERP
Version: 1.0.0
Standards: IFRS for SMEs / Full IFRS per ICPAK Practice

Owns the single source of truth for:
- Hierarchical, typed Chart of Accounts (Asset, Liability, Equity, Income, Expense)
- Fiscal Years & Periods with Year-End Closing and audit-logged reopening
- General Ledger Transactions, balanced Debit/Credit enforcement, Multi-Currency lines,
  Analytic Dimensions (Branch, Cost Center), and Posting Queue
"""
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.models.base import CompanyScopedModel, BranchScopedModel, AuditedModel, TimeStampedModel
from core.models.organization import Company, Branch


class AccountType(models.TextChoices):
    ASSET = 'asset', 'Asset'
    LIABILITY = 'liability', 'Liability'
    EQUITY = 'equity', 'Equity'
    INCOME = 'income', 'Income'
    EXPENSE = 'expense', 'Expense'


class AccountCategory(models.TextChoices):
    # Assets
    CURRENT_ASSET = 'current_asset', 'Current Asset'
    CASH_AND_BANK = 'cash_and_bank', 'Cash and Bank Equivalents'
    ACCOUNTS_RECEIVABLE = 'accounts_receivable', 'Accounts Receivable (Trade Debtors)'
    INVENTORY = 'inventory', 'Merchandise Inventory'
    STATUTORY_TAX_ASSET = 'statutory_tax_asset', 'Statutory Tax Credits & Claimable VAT'
    FIXED_ASSET = 'fixed_asset', 'Property, Plant & Equipment'
    ACCUMULATED_DEPRECIATION = 'accumulated_depreciation', 'Accumulated Depreciation'
    
    # Liabilities
    CURRENT_LIABILITY = 'current_liability', 'Current Liability'
    ACCOUNTS_PAYABLE = 'accounts_payable', 'Accounts Payable (Trade Creditors)'
    STATUTORY_TAX_LIABILITY = 'statutory_tax_liability', 'Statutory Tax & Remittance Liabilities'
    PAYROLL_CLEARING = 'payroll_clearing', 'Payroll Clearing & Net Salaries'
    LONG_TERM_LIABILITY = 'long_term_liability', 'Long-Term Borrowings & Liabilities'
    
    # Equity
    EQUITY = 'equity', 'Owner / Share Capital'
    RETAINED_EARNINGS = 'retained_earnings', 'Retained Earnings / Accumulated Reserves'
    OWNER_DRAWING = 'owner_drawing', 'Owner Drawings & Dividends Paid'
    
    # Income / Revenue
    OPERATING_REVENUE = 'operating_revenue', 'Operating Sales Revenue'
    SALES_DISCOUNT = 'sales_discount', 'Sales Discounts & Allowances'
    OTHER_INCOME = 'other_income', 'Other Income & Net Gains'
    
    # Expenses / Costs
    COST_OF_SALES = 'cost_of_sales', 'Cost of Goods Sold (Direct Costs)'
    PAYROLL_EXPENSE = 'payroll_expense', 'Salaries, Wages & Employer Statutory Costs'
    OPERATING_EXPENSE = 'operating_expense', 'Operating & Administrative Expenses'
    FINANCIAL_EXPENSE = 'financial_expense', 'Bank Charges & Financial Fees'
    DEPRECIATION_EXPENSE = 'depreciation_expense', 'Depreciation & Amortization'
    TAX_EXPENSE = 'tax_expense', 'Income Tax & Corporate Tax'


class NormalBalance(models.TextChoices):
    DEBIT = 'debit', 'Debit (DR)'
    CREDIT = 'credit', 'Credit (CR)'


class Account(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """
    General Ledger Account within the Chart of Accounts.
    Hierarchical parent-child support, typed categories, and protection against deletion.
    """
    code = models.CharField(max_length=20, db_index=True, help_text="e.g. 1010, 2100, 4000")
    name = models.CharField(max_length=150, db_index=True, help_text="e.g. Cash in Till, VAT Output Payable")
    account_type = models.CharField(max_length=20, choices=AccountType.choices, db_index=True)
    category = models.CharField(max_length=40, choices=AccountCategory.choices, db_index=True)
    normal_balance = models.CharField(max_length=10, choices=NormalBalance.choices, default=NormalBalance.DEBIT)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='children',
        help_text="Parent account for hierarchical reporting"
    )
    currency = models.CharField(max_length=3, default='KES', help_text="ISO 4217 Currency Code")
    
    # System & Protection Flags
    is_system = models.BooleanField(
        default=False,
        db_index=True,
        help_text="System-managed account (e.g. Retained Earnings, Control Accounts). Cannot be deleted."
    )
    system_tag = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        db_index=True,
        help_text="Canonical tag for system mapping (e.g. 'ar', 'ap', 'vat_output', 'retained_earnings')"
    )
    is_reconciliation = models.BooleanField(
        default=False,
        help_text="Designates this account for bank/cash statement reconciliation"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_locked = models.BooleanField(default=False, db_index=True, help_text="Locked accounts disallow manual postings")
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Chart of Account'
        verbose_name_plural = 'Chart of Accounts'
        unique_together = [['company', 'code']]
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name} ({self.get_account_type_display()})"

    def clean(self):
        super().clean()
        # Set default normal balance based on account type if not specified
        if not self.normal_balance:
            if self.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
                self.normal_balance = NormalBalance.DEBIT
            else:
                self.normal_balance = NormalBalance.CREDIT

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValidationError(f"Account '{self.code} - {self.name}' is a system-protected account and cannot be deleted.")
        if self.journal_lines.exists():
            raise ValidationError(f"Account '{self.code} - {self.name}' has recorded transactions and cannot be deleted. Deactivate or lock it instead.")
        super().delete(*args, **kwargs)


class FiscalYear(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """
    Financial reporting year (e.g. 2026).
    Enforces opening and closing controls for annual financial cycles.
    """
    name = models.CharField(max_length=50, help_text="e.g. 'FY 2026'")
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    is_closed = models.BooleanField(default=False, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accounting_closed_fiscal_years'
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accounting_reopened_fiscal_years'
    )

    class Meta:
        verbose_name = 'Fiscal Year'
        verbose_name_plural = 'Fiscal Years'
        unique_together = [['company', 'name']]
        ordering = ['-start_date']

    def __str__(self):
        status = " (Closed)" if self.is_closed else " (Open)"
        return f"{self.name} ({self.start_date.strftime('%d/%m/%Y')} - {self.end_date.strftime('%d/%m/%Y')}){status}"


class FiscalPeriod(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """
    Monthly or Quarterly accounting period.
    Posting is restricted when the period is marked closed.
    """
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.CASCADE,
        related_name='periods',
        db_index=True
    )
    period_number = models.PositiveSmallIntegerField(help_text="1 to 12 (or 13 for Year-End Adjustments)")
    name = models.CharField(max_length=50, help_text="e.g. 'January 2026'")
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    is_closed = models.BooleanField(default=False, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accounting_closed_periods'
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accounting_reopened_periods'
    )
    is_adjustment_period = models.BooleanField(default=False, help_text="True for Period 13 year-end adjusting entries")

    class Meta:
        verbose_name = 'Fiscal Period'
        verbose_name_plural = 'Fiscal Periods'
        unique_together = [['company', 'fiscal_year', 'period_number']]
        ordering = ['fiscal_year__start_date', 'period_number']

    def __str__(self):
        status = " (Closed)" if self.is_closed else " (Open)"
        return f"{self.name} - {self.company.name}{status}"


class JournalEntryType(models.TextChoices):
    MANUAL = 'manual', 'Manual General Journal'
    SALES_CLOSE = 'sales_close', 'POS Sales / Shift Close'
    PAYROLL = 'payroll', 'Payroll Run Journal'
    AR_INVOICE = 'ar_invoice', 'Customer Invoice'
    AP_BILL = 'ap_bill', 'Supplier Bill'
    PAYMENT = 'payment', 'Payment Voucher / Disbursement'
    RECEIPT = 'receipt', 'Customer Collection / Receipt'
    BANK_RECONCILIATION = 'bank_reconciliation', 'Bank Reconciliation Adjustment'
    DEPRECIATION = 'depreciation', 'Fixed Asset Depreciation'
    REVERSING = 'reversing', 'Reversing Journal Entry'
    RECURRING = 'recurring', 'Recurring Journal Entry'
    CLOSING = 'closing', 'Year-End Closing Entry'
    ADJUSTMENT = 'adjustment', 'Period-End Adjustment'


class JournalEntryStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PENDING_APPROVAL = 'pending_approval', 'Pending Approval'
    POSTED = 'posted', 'Posted'
    REVERSED = 'reversed', 'Reversed'


class JournalEntry(CompanyScopedModel, BranchScopedModel, AuditedModel, TimeStampedModel):
    """
    Standard double-entry transaction header.
    Immutable once posted; changes must occur via reversals or adjustment entries.
    """
    entry_number = models.CharField(max_length=50, db_index=True, help_text="e.g. JRN-202609-0001")
    entry_type = models.CharField(max_length=30, choices=JournalEntryType.choices, default=JournalEntryType.MANUAL, db_index=True)
    date = models.DateField(default=timezone.now, db_index=True)
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='journal_entries'
    )
    
    # Originating Source Module & Reference
    source_module = models.CharField(max_length=50, default='accounting', db_index=True, help_text="e.g. pos, hr, manual")
    source_ref = models.CharField(max_length=100, blank=True, db_index=True, help_text="Origin doc reference e.g. ZREP-20260930-01")
    idempotency_key = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_index=True,
        help_text="Unique key ensuring exactly-once posting"
    )
    
    narration = models.TextField(help_text="Transaction description and business purpose")
    status = models.CharField(max_length=20, choices=JournalEntryStatus.choices, default=JournalEntryStatus.POSTED, db_index=True)
    
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accounting_posted_journals'
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    
    # Reversal Tracking
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accounting_reversed_journals'
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_entry = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reverses_entry',
        help_text="Pointer to the countervailing reversing journal entry"
    )
    reversal_reason = models.CharField(max_length=255, blank=True)
    
    # Recurring Controls
    is_recurring = models.BooleanField(default=False)
    recurring_frequency = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('annual', 'Annual'),
        ]
    )
    recurring_end_date = models.DateField(null=True, blank=True)
    
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'
        unique_together = [['company', 'entry_number']]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                name='unique_company_accounting_idempotency_key',
                condition=models.Q(idempotency_key__isnull=False)
            )
        ]
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.entry_number} ({self.date.strftime('%d/%m/%Y')}) - KES {self.total_amount:,.2f} [{self.get_status_display()}]"

    def calculate_totals(self):
        """Calculate and return total debits and credits."""
        lines = list(self.lines.all())
        total_dr = sum((line.debit for line in lines), Decimal('0.00'))
        total_cr = sum((line.credit for line in lines), Decimal('0.00'))
        return total_dr, total_cr

    def is_balanced(self) -> bool:
        """Verify debit sum equals credit sum to 2 decimal places."""
        dr, cr = self.calculate_totals()
        return round(dr, 2) == round(cr, 2) and dr > Decimal('0.00')


class JournalEntryLine(TimeStampedModel):
    """
    Individual debit or credit ledger record belonging to a JournalEntry.
    """
    entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='lines',
        db_index=True
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='journal_lines',
        db_index=True
    )
    account_code = models.CharField(max_length=20, db_index=True)
    account_name = models.CharField(max_length=150)
    
    # Financial Amounts (Base Currency KES)
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    
    # Multi-Currency Support
    currency = models.CharField(max_length=3, default='KES', help_text="Transaction Currency (e.g. KES, USD)")
    foreign_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal('1.000000'))
    
    # Analytic Dimensions
    branch = models.ForeignKey(
        Branch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='accounting_journal_lines',
        help_text="Analytic branch dimension"
    )
    cost_center = models.CharField(max_length=50, blank=True, db_index=True, help_text="e.g. 'CC-SALES', 'CC-OPS'")
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Journal Entry Line'
        verbose_name_plural = 'Journal Entry Lines'
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                check=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name='accounting_line_non_negative_amounts'
            ),
            models.CheckConstraint(
                check=(models.Q(debit__gt=0) & models.Q(credit=0)) | (models.Q(credit__gt=0) & models.Q(debit=0)),
                name='accounting_line_either_debit_or_credit'
            ),
        ]

    def __str__(self):
        if self.debit > Decimal('0.00'):
            return f"DR {self.account_code} - {self.account_name}: KES {self.debit:,.2f}"
        return f"CR {self.account_code} - {self.account_name}: KES {self.credit:,.2f}"


class PostingQueue(CompanyScopedModel, TimeStampedModel):
    """
    Queue for asynchronous, delayed or offline journal postings submitted to Accounting.
    Ensures safe degradation, retry mechanism, and resilience.
    """
    STATUS_PENDING = 'pending'
    STATUS_PROCESSED = 'processed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSED, 'Processed'),
        (STATUS_FAILED, 'Failed'),
    ]

    source_module = models.CharField(max_length=50, db_index=True)
    source_ref = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField(help_text="Serialized journal lines and metadata")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='queued_postings'
    )

    class Meta:
        verbose_name = 'Posting Queue'
        verbose_name_plural = 'Posting Queue Entries'
        ordering = ['-created_at']

    def __str__(self):
        return f"PostQueue #{self.id} from {self.source_module} ({self.source_ref}) [{self.get_status_display()}]"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3: SUBLEDGERS (AR, AP) & BANK RECONCILIATION MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class Customer(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Customer entity for Accounts Receivable subledger."""
    name = models.CharField(max_length=150, db_index=True)
    kra_pin = models.CharField(max_length=50, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Customer (Debtor)'
        verbose_name_plural = 'Customers (Debtors)'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.kra_pin})" if self.kra_pin else self.name


class Vendor(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Vendor / Supplier entity for Accounts Payable subledger."""
    name = models.CharField(max_length=150, db_index=True)
    kra_pin = models.CharField(max_length=50, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    payment_terms_days = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Vendor (Creditor)'
        verbose_name_plural = 'Vendors (Creditors)'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.kra_pin})" if self.kra_pin else self.name


class InvoiceStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    POSTED = 'posted', 'Posted'
    PARTIAL = 'partial', 'Partially Paid'
    PAID = 'paid', 'Fully Paid'
    CANCELLED = 'cancelled', 'Cancelled'


class CustomerInvoice(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Accounts Receivable Customer Invoice."""
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_invoices')
    invoice_number = models.CharField(max_length=50, db_index=True)
    invoice_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT, db_index=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='customer_invoices'
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Customer Invoice'
        verbose_name_plural = 'Customer Invoices'
        unique_together = [['company', 'invoice_number']]
        ordering = ['-invoice_date', '-id']

    def __str__(self):
        return f"Inv #{self.invoice_number} - {self.customer.name} (KES {self.total_amount:,.2f})"


class CustomerInvoiceLine(TimeStampedModel):
    """Line item on a Customer Invoice."""
    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='customer_invoice_lines')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('16.00'))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Customer Invoice Line'
        verbose_name_plural = 'Customer Invoice Lines'
        ordering = ['id']

    def save(self, *args, **kwargs):
        if not self.line_total:
            qty = self.quantity or Decimal('1.00')
            price = self.unit_price or Decimal('0.00')
            subtotal = (qty * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if not self.tax_amount and self.tax_rate:
                self.tax_amount = (subtotal * (self.tax_rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.line_total = subtotal + (self.tax_amount or Decimal('0.00'))
        super().save(*args, **kwargs)


class CustomerPayment(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Customer payment receipt allocated against AR invoices."""
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer / RTGS'),
        ('mpesa', 'M-Pesa'),
        ('card', 'Card'),
        ('cheque', 'Cheque'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='payments')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_payments')
    receipt_number = models.CharField(max_length=50, db_index=True)
    payment_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS, default='mpesa')
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    deposit_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='customer_payment_deposits')
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='customer_payments'
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Customer Payment Receipt'
        verbose_name_plural = 'Customer Payment Receipts'
        unique_together = [['company', 'receipt_number']]
        ordering = ['-payment_date', '-id']

    def __str__(self):
        return f"Receipt #{self.receipt_number} - {self.customer.name} (KES {self.amount:,.2f})"


class CustomerPaymentAllocation(TimeStampedModel):
    """Allocation of Customer Payment to specific Invoice(s)."""
    payment = models.ForeignKey(CustomerPayment, on_delete=models.CASCADE, related_name='allocations')
    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.PROTECT, related_name='payment_allocations')
    amount_allocated = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = 'Customer Payment Allocation'
        verbose_name_plural = 'Customer Payment Allocations'


class BillStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    POSTED = 'posted', 'Posted'
    PARTIAL = 'partial', 'Partially Paid'
    PAID = 'paid', 'Fully Paid'
    CANCELLED = 'cancelled', 'Cancelled'


class VendorBill(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Accounts Payable Vendor Bill."""
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='bills')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_bills')
    bill_number = models.CharField(max_length=50, db_index=True)
    supplier_invoice_number = models.CharField(max_length=100, blank=True, db_index=True)
    bill_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=BillStatus.choices, default=BillStatus.DRAFT, db_index=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='vendor_bills'
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Vendor Bill'
        verbose_name_plural = 'Vendor Bills'
        unique_together = [['company', 'bill_number']]
        ordering = ['-bill_date', '-id']

    def __str__(self):
        return f"Bill #{self.bill_number} - {self.vendor.name} (KES {self.total_amount:,.2f})"


class VendorBillLine(TimeStampedModel):
    """Line item on a Vendor Bill."""
    bill = models.ForeignKey(VendorBill, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='vendor_bill_lines')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('16.00'))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    def save(self, *args, **kwargs):
        if not self.line_total:
            qty = self.quantity or Decimal('1.00')
            price = self.unit_price or Decimal('0.00')
            subtotal = (qty * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if not self.tax_amount and self.tax_rate:
                self.tax_amount = (subtotal * (self.tax_rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.line_total = subtotal + (self.tax_amount or Decimal('0.00'))
        super().save(*args, **kwargs)


class VendorPayment(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Vendor payment disbursement / voucher allocated against AP bills."""
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer / EFT / RTGS'),
        ('mpesa', 'M-Pesa Paybill / B2B'),
        ('card', 'Corporate Card'),
        ('cheque', 'Cheque'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='payments')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendor_payments')
    voucher_number = models.CharField(max_length=50, db_index=True)
    payment_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS, default='bank')
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    paid_from_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='vendor_payment_disbursements')
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='vendor_payments'
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Vendor Payment Voucher'
        verbose_name_plural = 'Vendor Payment Vouchers'
        unique_together = [['company', 'voucher_number']]
        ordering = ['-payment_date', '-id']

    def __str__(self):
        return f"Voucher #{self.voucher_number} - {self.vendor.name} (KES {self.amount:,.2f})"


class VendorPaymentAllocation(TimeStampedModel):
    """Allocation of Vendor Payment to specific Bill(s)."""
    payment = models.ForeignKey(VendorPayment, on_delete=models.CASCADE, related_name='allocations')
    bill = models.ForeignKey(VendorBill, on_delete=models.PROTECT, related_name='payment_allocations')
    amount_allocated = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = 'Vendor Payment Allocation'
        verbose_name_plural = 'Vendor Payment Allocations'


class BankAccount(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Bank or M-Pesa account linked to General Ledger cash/bank clearing account."""
    name = models.CharField(max_length=100, help_text="e.g. KCB Operating or Safaricom Till 123456")
    bank_name = models.CharField(max_length=100, help_text="e.g. KCB Bank, Equity Bank, Safaricom M-Pesa")
    account_number = models.CharField(max_length=50, db_index=True)
    gl_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='bank_accounts')
    currency = models.CharField(max_length=3, default='KES')
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Bank / M-Pesa Account'
        verbose_name_plural = 'Bank / M-Pesa Accounts'
        unique_together = [['company', 'account_number']]
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.account_number}) - GL: {self.gl_account.code}"


class BankStatement(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Imported Bank or M-Pesa statement for reconciliation."""
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='statements')
    statement_date = models.DateField(db_index=True)
    start_date = models.DateField()
    end_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=14, decimal_places=2)
    is_reconciled = models.BooleanField(default=False, db_index=True)
    uploaded_file = models.FileField(upload_to='bank_statements/', null=True, blank=True)

    class Meta:
        verbose_name = 'Bank Statement'
        verbose_name_plural = 'Bank Statements'
        ordering = ['-end_date', '-id']

    def __str__(self):
        return f"Statement {self.bank_account.name} ({self.start_date} to {self.end_date})"


class BankStatementLine(TimeStampedModel):
    """Single transaction line on an imported bank or M-Pesa statement."""
    statement = models.ForeignKey(BankStatement, on_delete=models.CASCADE, related_name='lines')
    date = models.DateField(db_index=True)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    description = models.CharField(max_length=255)
    # Positive (+) for deposits / money received; Negative (-) for withdrawals / charges / payouts
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    is_reconciled = models.BooleanField(default=False, db_index=True)
    matched_journal_line = models.ForeignKey(
        JournalEntryLine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='matched_bank_lines'
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Bank Statement Line'
        verbose_name_plural = 'Bank Statement Lines'
        ordering = ['date', 'id']

    def __str__(self):
        sign = "+" if self.amount >= 0 else ""
        return f"{self.date} | {self.reference} | {self.description} | {sign}{self.amount:,.2f}"


class BankReconciliation(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """Formal bank reconciliation record balancing Bank Statement to General Ledger."""
    STATUS_CHOICES = [
        ('draft', 'Draft In Progress'),
        ('completed', 'Reconciliation Completed'),
    ]
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='reconciliations')
    statement = models.ForeignKey(BankStatement, on_delete=models.SET_NULL, null=True, blank=True, related_name='reconciliations')
    as_of_date = models.DateField(db_index=True)
    statement_ending_balance = models.DecimalField(max_digits=14, decimal_places=2)
    gl_ending_balance = models.DecimalField(max_digits=14, decimal_places=2)
    unreconciled_deposits = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    unreconciled_payments = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    adjusted_gl_balance = models.DecimalField(max_digits=14, decimal_places=2)
    difference = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    is_balanced = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)

    class Meta:
        verbose_name = 'Bank Reconciliation'
        verbose_name_plural = 'Bank Reconciliations'
        ordering = ['-as_of_date', '-id']

    def __str__(self):
        return f"Recon {self.bank_account.name} as of {self.as_of_date} (Diff: KES {self.difference:,.2f})"


# ─── KENYAN TAX ENGINE MODELS ───────────────────────────────────────────────

class TaxRateType(models.TextChoices):
    STANDARD_16 = 'standard_16', '16% Standard VAT'
    ZERO_RATED = 'zero_rated', '0% Zero Rated'
    EXEMPT = 'exempt', 'Exempt'
    WHT_MANAGEMENT_5 = 'wht_management_5', '5% WHT - Management & Professional Fees'
    WHT_CONTRACTUAL_3 = 'wht_contractual_3', '3% WHT - Contractual Fees'
    WHT_RENT_10 = 'wht_rent_10', '10% WHT - Commercial Rent'
    WHT_VAT_2 = 'wht_vat_2', '2% Withholding VAT'


class WHTType(models.TextChoices):
    PAYABLE = 'payable', 'WHT Payable (Deducted from Supplier)'
    RECEIVABLE = 'receivable', 'WHT Receivable (Deducted by Customer)'


class WHTCategory(models.TextChoices):
    MANAGEMENT_PROFESSIONAL = 'management_professional', 'Management / Professional Fees (5%)'
    CONTRACTUAL = 'contractual', 'Contractual Services (3%)'
    RENT = 'rent', 'Commercial Rent (10%)'
    WITHHOLDING_VAT = 'whvat', 'Withholding VAT (2%)'
    OTHER = 'other', 'Other Prescribed Rate'


class WithholdingTaxRecord(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """
    Withholding Tax & Withholding VAT transaction tracking for KRA compliance.
    """
    wht_type = models.CharField(max_length=20, choices=WHTType.choices, db_index=True)
    category = models.CharField(max_length=40, choices=WHTCategory.choices, default=WHTCategory.WITHHOLDING_VAT, db_index=True)
    party_name = models.CharField(max_length=255)
    party_pin = models.CharField(max_length=20, blank=True, help_text="KRA PIN e.g. P051234567Z")
    transaction_date = models.DateField(db_index=True)
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Gross taxable value")
    rate_percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Tax rate e.g. 2.00, 5.00")
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, help_text="Amount of tax withheld")
    certificate_number = models.CharField(max_length=100, blank=True, help_text="KRA WHT Certificate Number")
    
    customer_invoice = models.ForeignKey(
        'CustomerInvoice',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='wht_records'
    )
    vendor_bill = models.ForeignKey(
        'VendorBill',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='wht_records'
    )
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='wht_records'
    )
    is_remitted = models.BooleanField(default=False, help_text="Marked True when remitted to KRA via iTax")
    remittance_date = models.DateField(null=True, blank=True)
    remittance_reference = models.CharField(max_length=100, blank=True, help_text="KRA Payment Slip / E-Slip No.")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Withholding Tax Record'
        verbose_name_plural = 'Withholding Tax Records'
        ordering = ['-transaction_date', '-id']

    def __str__(self):
        return f"WHT ({self.get_category_display()}) - {self.party_name} - KES {self.tax_amount:,.2f}"


