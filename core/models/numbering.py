"""
Concurrency-Safe Document Numbering Model
Generates gap-aware and unique sequential document numbers per Company / Branch / Fiscal Year.
"""
from django.db import models
from core.models.base import TimeStampedModel


class DocumentSequence(TimeStampedModel):
    """
    Maintains atomic monotonic sequence counters for invoices, receipts, purchase orders, etc.
    Format Pattern Tokens:
      {prefix}        - Custom document prefix (e.g. INV, PO, GRN)
      {branch_code}   - Branch short code (e.g. HQ, NBI01)
      {year}          - 4-digit fiscal year (e.g. 2026)
      {year2}         - 2-digit fiscal year (e.g. 26)
      {month}         - 2-digit month (01-12)
      {day}           - 2-digit day (01-31)
      {seq:04d}       - Formatted sequential number (e.g. 0001, 0002)
    """
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='document_sequences',
        db_index=True,
    )
    branch = models.ForeignKey(
        'core.Branch',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='document_sequences',
        db_index=True,
        help_text="Branch scope (NULL for company-wide sequence)",
    )
    document_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="e.g. 'sale_invoice', 'purchase_order', 'goods_received_note', 'expense'",
    )
    prefix = models.CharField(max_length=20, default='DOC')
    fiscal_year = models.PositiveSmallIntegerField(default=2026, db_index=True)
    format_pattern = models.CharField(
        max_length=100,
        default='{prefix}-{year}{month:02d}-{seq:04d}',
        help_text="Tokenized pattern e.g. {prefix}-{branch_code}-{year}-{seq:06d}",
    )
    current_number = models.BigIntegerField(default=0)
    is_gap_aware = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Document Sequence'
        verbose_name_plural = 'Document Sequences'
        unique_together = [['company', 'branch', 'document_type', 'fiscal_year']]
        indexes = [
            models.Index(fields=['company', 'document_type', 'fiscal_year']),
        ]

    def __str__(self):
        branch_str = f"/{self.branch.code}" if self.branch else "/HQ"
        return f"{self.document_type} ({self.company.name}{branch_str}, FY{self.fiscal_year}): Last #{self.current_number}"
