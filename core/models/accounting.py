"""
Core Accounting & Platform Ledger Models
Provides central journal entries, lines, and fiscal periods for all modules (POS, HR, etc.).
"""
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models.base import CompanyScopedModel, AuditedModel, TimeStampedModel
from core.models.organization import Company


class FiscalPeriod(CompanyScopedModel, TimeStampedModel):
    """
    Financial reporting period (Month, Quarter, Year).
    Closed periods prevent modifications and backdated journal postings.
    """
    name = models.CharField(max_length=50, help_text="Period name, e.g. 'January 2026', '2026-Q1'")
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    is_closed = models.BooleanField(default=False, db_index=True, help_text="True if closed for posting")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_fiscal_periods'
    )

    class Meta:
        verbose_name = 'Fiscal Period'
        verbose_name_plural = 'Fiscal Periods'
        ordering = ['-start_date']
        unique_together = [['company', 'name']]

    def __str__(self):
        status = " (Closed)" if self.is_closed else " (Open)"
        return f"{self.name} - {self.company.name}{status}"


class JournalEntry(CompanyScopedModel, AuditedModel, TimeStampedModel):
    """
    Standard double-entry accounting journal transaction.
    Guarantees debit/credit equality and module source traceability.
    """
    STATUS_DRAFT = 'draft'
    STATUS_POSTED = 'posted'
    STATUS_REVERSED = 'reversed'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_POSTED, 'Posted'),
        (STATUS_REVERSED, 'Reversed'),
    ]

    entry_number = models.CharField(max_length=50, db_index=True, help_text="Unique entry reference e.g. JRN-2026-0001")
    date = models.DateField(default=timezone.now, db_index=True)
    source_module = models.CharField(max_length=50, db_index=True, help_text="Origin module e.g. pos, hr, manual")
    source_ref = models.CharField(max_length=100, blank=True, db_index=True, help_text="Origin reference e.g. INV-20260930-0001")
    idempotency_key = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        db_index=True,
        help_text="Unique key preventing double posting"
    )
    narration = models.TextField(blank=True, help_text="Transaction description")
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posted_journal_entries'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_POSTED, db_index=True)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Journal Entry'
        verbose_name_plural = 'Journal Entries'
        ordering = ['-date', '-created_at']
        unique_together = [['company', 'entry_number']]
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                name='unique_company_journal_idempotency_key',
                condition=models.Q(idempotency_key__isnull=False)
            )
        ]

    def __str__(self):
        return f"{self.entry_number} ({self.date}) - KES {self.total_amount:,.2f}"

    def calculate_totals(self):
        """Calculate and update total debits/credits."""
        debit_sum = sum((l.debit for l in self.lines.all()), Decimal('0.00'))
        credit_sum = sum((l.credit for l in self.lines.all()), Decimal('0.00'))
        return debit_sum, credit_sum


class JournalEntryLine(TimeStampedModel):
    """
    Individual debit or credit line on a Journal Entry.
    """
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account_code = models.CharField(max_length=50, db_index=True, help_text="Chart of Accounts code e.g. 1000, 4000")
    account_name = models.CharField(max_length=150, db_index=True)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Journal Entry Line'
        verbose_name_plural = 'Journal Entry Lines'
        ordering = ['id']

    def __str__(self):
        if self.debit > Decimal('0.00'):
            return f"DR {self.account_code} - {self.account_name}: KES {self.debit:,.2f}"
        return f"CR {self.account_code} - {self.account_name}: KES {self.credit:,.2f}"
