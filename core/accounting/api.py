"""
Platform Core Accounting Public Interface
Version: 1.0.0

Provides double-entry journal posting, balance verification, fiscal period gating,
and idempotency protection for all ERP modules (POS, HR, Procurement, Inventory).
"""
from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import date
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.models.organization import Company
from core.models.accounting import JournalEntry, JournalEntryLine, FiscalPeriod
from core.numbering.service import next_document_number
from core.events.bus import publish


def is_fiscal_period_closed(company: Company, date_val: Optional[date] = None) -> bool:
    """Check if the given transaction date falls within a closed fiscal period."""
    if not date_val:
        date_val = timezone.now().date()

    return FiscalPeriod.objects.filter(
        company=company,
        start_date__lte=date_val,
        end_date__gte=date_val,
        is_closed=True,
    ).exists()


def post_journal_entry(
    company: Company,
    entries: List[Dict[str, Any]],
    source_module: str,
    source_ref: str = '',
    date_val: Optional[date] = None,
    narration: str = '',
    posted_by: Optional[Any] = None,
    idempotency_key: Optional[str] = None,
) -> JournalEntry:
    """
    Post a double-entry transaction to the platform ledger.

    Args:
        company: Company instance (tenant)
        entries: List of dicts, each with:
            - 'account_code': str (e.g. '1000')
            - 'account_name': str (e.g. 'Cash at Bank')
            - 'debit': Decimal / float / str (default 0.00)
            - 'credit': Decimal / float / str (default 0.00)
            - 'description': Optional[str]
        source_module: Submitting module name ('pos', 'hr', 'procurement', etc.)
        source_ref: Document reference in source module (e.g. 'INV-20260930-0001')
        date_val: Transaction date (defaults to today)
        narration: High-level entry description
        posted_by: User instance who authorized/triggered posting
        idempotency_key: Client-provided idempotency key (defaults to source_module:source_ref)

    Returns:
        The created or existing JournalEntry instance.

    Raises:
        ValidationError: If unbalanced, period closed, or invalid inputs.
    """
    if not company:
        raise ValidationError("A valid Company is required for journal entry posting.")

    if not entries or len(entries) < 2:
        raise ValidationError("Journal entry requires at least 2 lines (debit and credit).")

    if not date_val:
        date_val = timezone.now().date()

    # 1. Closed Period Check
    if is_fiscal_period_closed(company, date_val):
        raise ValidationError(f"Cannot post journal entry: Fiscal period for {date_val} is closed.")

    # 2. Idempotency Check
    computed_idempotency = idempotency_key or (f"{source_module}:{source_ref}" if source_ref else None)
    if computed_idempotency:
        existing = JournalEntry.objects.filter(
            company=company,
            idempotency_key=computed_idempotency,
        ).first()
        if existing:
            return existing

    # 3. Parse and Balance Check
    total_debits = Decimal('0.00')
    total_credits = Decimal('0.00')
    parsed_lines = []

    for idx, raw in enumerate(entries):
        account_code = str(raw.get('account_code', '')).strip()
        account_name = str(raw.get('account_name', '')).strip() or account_code
        if not account_code:
            raise ValidationError(f"Line {idx + 1} is missing 'account_code'.")

        try:
            debit = Decimal(str(raw.get('debit', '0.00') or '0.00'))
            credit = Decimal(str(raw.get('credit', '0.00') or '0.00'))
        except Exception as e:
            raise ValidationError(f"Line {idx + 1} has invalid amounts: {e}")

        if debit < Decimal('0.00') or credit < Decimal('0.00'):
            raise ValidationError(f"Line {idx + 1} amounts cannot be negative.")

        if debit == Decimal('0.00') and credit == Decimal('0.00'):
            raise ValidationError(f"Line {idx + 1} must have either a debit or credit amount.")

        total_debits += debit
        total_credits += credit
        parsed_lines.append({
            'account_code': account_code,
            'account_name': account_name,
            'debit': debit,
            'credit': credit,
            'description': raw.get('description', ''),
        })

    # Floating point cents tolerance (must match to 2 decimal places)
    if round(total_debits, 2) != round(total_credits, 2):
        raise ValidationError(
            f"Unbalanced journal entry: Total debits (KES {total_debits:,.2f}) "
            f"does not equal total credits (KES {total_credits:,.2f})."
        )

    if total_debits <= Decimal('0.00'):
        raise ValidationError("Journal entry total amount must be greater than zero.")

    # 4. Atomic Document Sequence and Creation
    with transaction.atomic():
        entry_number = next_document_number(
            document_type='journal_entry',
            company=company,
            date_val=date_val,
            prefix='JRN',
            format_pattern='{prefix}-{year}{month:02d}-{seq:04d}',
        )

        entry = JournalEntry.objects.create(
            company=company,
            entry_number=entry_number,
            date=date_val,
            source_module=source_module,
            source_ref=source_ref,
            idempotency_key=computed_idempotency,
            narration=narration or f"Journal posting from {source_module.upper()} ({source_ref})",
            posted_by=posted_by if (posted_by and getattr(posted_by, 'is_authenticated', False)) else None,
            status=JournalEntry.STATUS_POSTED,
            total_amount=total_debits,
        )

        line_objects = [
            JournalEntryLine(
                entry=entry,
                account_code=item['account_code'],
                account_name=item['account_name'],
                debit=item['debit'],
                credit=item['credit'],
                description=item['description'],
            )
            for item in parsed_lines
        ]
        JournalEntryLine.objects.bulk_create(line_objects)

        # 5. Outbox Event
        try:
            publish(
                event_name='accounting.journal_entry_posted.v1',
                payload={
                    'entry_id': entry.pk,
                    'entry_number': entry.entry_number,
                    'company_id': company.pk,
                    'source_module': source_module,
                    'source_ref': source_ref,
                    'date': date_val.isoformat(),
                    'total_amount': str(total_debits),
                    'line_count': len(line_objects),
                },
                company=company,
            )
        except Exception:
            pass

    return entry
