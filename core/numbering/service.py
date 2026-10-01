"""
Concurrency-Safe Document Numbering Engine
Guarantees collision-free, gap-aware sequential numbers under high concurrency.
"""
from typing import Optional
from datetime import date
from django.db import transaction
from django.utils import timezone
from core.models.numbering import DocumentSequence
from core.models.organization import Company, Branch


DEFAULT_PREFIXES = {
    'sale_invoice': 'INV',
    'sale_receipt': 'REC',
    'sale_return': 'RET',
    'purchase_order': 'PO',
    'goods_received_note': 'GRN',
    'goods_returned_note': 'GRNR',
    'supplier_payment': 'PAY',
    'supplier_credit': 'SCR',
    'expense': 'EXP',
    'shift': 'SHIFT',
    'cash_float': 'FLT',
    'cash_pickup': 'PCK',
    'cash_paid_out': 'PDO',
    'stock_requisition': 'REQ',
    'stock_transfer': 'TRF',
}


def next_document_number(
    document_type: str,
    company: Company,
    branch: Optional[Branch] = None,
    date_val: Optional[date] = None,
    prefix: Optional[str] = None,
    format_pattern: Optional[str] = None,
) -> str:
    """
    Generate the next unique document number in an atomic row-locked transaction.
    Tokens supported in pattern:
      {prefix}        - Custom document prefix (e.g. INV)
      {branch_code}   - Branch short code (e.g. HQ, NBI01)
      {year}          - 4-digit fiscal year (e.g. 2026)
      {year2}         - 2-digit fiscal year (e.g. 26)
      {month}         - 2-digit month (01-12)
      {day}           - 2-digit day (01-31)
      {seq:04d}       - Formatted sequential number (e.g. 0001)
    """
    if not date_val:
        date_val = timezone.now().date()

    fiscal_year = date_val.year
    default_prefix = prefix or DEFAULT_PREFIXES.get(document_type, 'DOC')
    default_pattern = format_pattern or '{prefix}-{branch_code}-{year}{month:02d}-{seq:04d}'

    with transaction.atomic():
        # Atomically lock and fetch or create sequence row
        seq_obj = (
            DocumentSequence.objects.select_for_update()
            .filter(
                company=company,
                branch=branch,
                document_type=document_type,
                fiscal_year=fiscal_year,
            )
            .first()
        )

        if not seq_obj:
            seq_obj = DocumentSequence.objects.create(
                company=company,
                branch=branch,
                document_type=document_type,
                prefix=default_prefix,
                fiscal_year=fiscal_year,
                format_pattern=default_pattern,
                current_number=0,
            )
            # Re-select for update
            seq_obj = DocumentSequence.objects.select_for_update().get(id=seq_obj.id)

        seq_obj.current_number += 1
        seq_obj.save(update_fields=['current_number', 'updated_at'])

        seq_number = seq_obj.current_number
        branch_code = branch.code if branch else 'HQ'
        pattern = seq_obj.format_pattern or default_pattern

        # Format tokens
        context = {
            'prefix': seq_obj.prefix,
            'branch_code': branch_code,
            'year': date_val.year,
            'year2': f"{date_val.year % 100:02d}",
            'month': date_val.month,
            'day': date_val.day,
            'seq': seq_number,
        }

        try:
            return pattern.format(**context)
        except Exception:
            return f"{seq_obj.prefix}-{branch_code}-{date_val.year}{date_val.month:02d}-{seq_number:04d}"
