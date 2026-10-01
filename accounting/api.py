"""
Accounting Module Public Interface (api.py)
Version: 1.0.0
Standards: IFRS for SMEs / ICPAK Practice

This is the ONLY file external modules (POS, HR, Procurement, Inventory) are
permitted to import from the 'accounting' module.
Do not import internal models, views, or services directly.
"""
from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError

from core.models.organization import Company, Branch
from accounting.models import Account, JournalEntry, JournalEntryType, PostingQueue
from accounting.services import JournalPostingService, FiscalPeriodService
from accounting.selectors import TrialBalanceSelector


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
    entry_type: str = 'manual',
    auto_approve: bool = True,
) -> JournalEntry:
    """
    Public double-entry journal posting interface.

    Args:
        company: Tenant Company
        source_module: Submitting module name ('pos', 'hr', 'procurement', etc.)
        source_ref: Origin document reference ('ZREP-20260930-01', 'PAY-2026-09')
        date_val: Transaction effective date (defaults to today)
        lines: List of dicts, each with:
            - 'account_code' (str) or 'account_id' (int)
            - 'debit' (Decimal / str / float, default 0.00)
            - 'credit' (Decimal / str / float, default 0.00)
            - 'currency' (optional str, default 'KES')
            - 'exchange_rate' (optional Decimal, default 1.0)
            - 'foreign_amount' (optional Decimal)
            - 'branch' (optional Branch)
            - 'cost_center' (optional str)
            - 'description' (optional str)
        narration: Transaction description
        posted_by: User initiating the posting
        idempotency_key: Client idempotency key (defaults to 'source_module:source_ref')
        branch: Analytic branch
        entry_type: 'manual', 'sales_close', 'payroll', etc.
        auto_approve: Post immediately (True) or leave as draft (False)

    Returns:
        Created or matched existing JournalEntry instance.

    Raises:
        ValidationError: If unbalanced, period closed, account inactive, or invalid amounts.
    """
    return JournalPostingService.post_journal(
        company=company,
        source_module=source_module,
        source_ref=source_ref,
        date_val=date_val,
        lines=lines,
        narration=narration,
        posted_by=posted_by,
        idempotency_key=idempotency_key,
        branch=branch,
        entry_type=entry_type,
        auto_approve=auto_approve,
    )


def reverse_journal(
    entry: JournalEntry,
    reversed_by: Any,
    reason: str = '',
    date_val: Optional[date] = None,
) -> JournalEntry:
    """
    Public journal reversal interface.
    Inverts debits and credits, marks the original entry reversed, and links the two entries.
    """
    return JournalPostingService.reverse_journal(
        entry=entry,
        reversed_by=reversed_by,
        reason=reason,
        date_val=date_val,
    )


def is_fiscal_period_closed(company: Company, date_val: Optional[date] = None) -> bool:
    """Check if the given date falls in a closed fiscal period or year."""
    return FiscalPeriodService.is_period_closed(company, date_val)


def get_account(company: Company, code_or_tag: str) -> Optional[Account]:
    """Look up an Account in the company's Chart of Accounts by code or system tag."""
    if not company or not code_or_tag:
        return None

    code_or_tag = str(code_or_tag).strip()
    return Account.objects.filter(
        company=company,
        is_active=True
    ).filter(
        models_q_code_or_tag(code_or_tag)
    ).first()


def models_q_code_or_tag(val: str):
    from django.db.models import Q
    return Q(code=val) | Q(system_tag=val)


def get_trial_balance(
    company: Company,
    as_of_date: Optional[date] = None,
    start_date: Optional[date] = None,
    branch: Optional[Branch] = None,
) -> Dict[str, Any]:
    """Calculate the Trial Balance for a company as of a specified date."""
    return TrialBalanceSelector.get_trial_balance(
        company=company,
        as_of_date=as_of_date,
        start_date=start_date,
        branch=branch,
    )


def _sanitize_payload(obj: Any) -> Any:
    """Helper to convert Decimals, dates, and non-JSON-serializable objects for JSONField storage."""
    from datetime import date, datetime
    if isinstance(obj, dict):
        return {k: _sanitize_payload(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_sanitize_payload(x) for x in obj]
    elif isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def queue_posting(
    company: Company,
    payload: Dict[str, Any],
    source_module: Optional[str] = None,
    source_ref: Optional[str] = None,
    idempotency_key: str = '',
    process_immediately: bool = False,
) -> PostingQueue:
    """
    Queue an asynchronous or event-driven journal posting for safe processing.
    If process_immediately=True, processes the entry synchronously with error recording.
    """
    from django.utils import timezone
    from datetime import date
    
    src_mod = source_module or payload.get('source_module', 'system')
    src_ref = source_ref or payload.get('source_ref', '')

    sanitized = _sanitize_payload(payload)

    queue_item = PostingQueue.objects.create(
        company=company,
        source_module=src_mod,
        source_ref=src_ref,
        payload=sanitized,
        status=PostingQueue.STATUS_PENDING,
    )

    if process_immediately:
        queue_item.attempts += 1
        try:
            date_raw = payload.get('date') or payload.get('date_val')
            if isinstance(date_raw, str):
                date_val = date.fromisoformat(date_raw)
            elif isinstance(date_raw, date):
                date_val = date_raw
            else:
                date_val = timezone.localdate()

            entry = JournalPostingService.post_journal(
                company=company,
                source_module=queue_item.source_module,
                source_ref=queue_item.source_ref,
                date_val=date_val,
                lines=payload.get('lines', []),
                narration=payload.get('narration', ''),
                idempotency_key=idempotency_key or payload.get('idempotency_key'),
                entry_type=payload.get('entry_type', JournalEntryType.MANUAL),
            )
            queue_item.status = PostingQueue.STATUS_PROCESSED
            queue_item.created_journal_entry = entry
            queue_item.processed_at = timezone.now()
            queue_item.error_message = ''
            queue_item.save()
        except Exception as e:
            queue_item.status = PostingQueue.STATUS_FAILED
            queue_item.error_message = str(e)
            queue_item.save()

    return queue_item


def get_module_status() -> Dict[str, Any]:
    """Return public status and capabilities of the Accounting module."""
    return {
        'module': 'accounting',
        'is_ready': True,
        'standards': ['IFRS for SMEs', 'ICPAK Practice'],
        'base_currency': 'KES',
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 3 PUBLIC INTERFACE (AR, AP, BANK RECONCILIATION)
# ═══════════════════════════════════════════════════════════════════════════════

def post_customer_invoice(invoice: Any, user: Any = None) -> JournalEntry:
    """Post an AR Customer Invoice to the General Ledger."""
    from accounting.services import ARService
    return ARService.post_customer_invoice(invoice=invoice, user=user)


def record_customer_payment(payment: Any, allocations: Optional[List[Dict[str, Any]]] = None, user: Any = None) -> JournalEntry:
    """Record an AR Customer Payment and allocate against invoice(s)."""
    from accounting.services import ARService
    return ARService.record_customer_payment(payment=payment, allocations=allocations, user=user)


def post_vendor_bill(bill: Any, user: Any = None) -> JournalEntry:
    """Post an AP Vendor Bill to the General Ledger."""
    from accounting.services import APService
    return APService.post_vendor_bill(bill=bill, user=user)


def record_vendor_payment(payment: Any, allocations: Optional[List[Dict[str, Any]]] = None, user: Any = None) -> JournalEntry:
    """Record an AP Vendor Payment disbursement and allocate against bill(s)."""
    from accounting.services import APService
    return APService.record_vendor_payment(payment=payment, allocations=allocations, user=user)


def parse_mpesa_statement(bank_account: Any, csv_content: str, user: Any = None) -> Any:
    """Parse a Safaricom M-Pesa CSV statement for a bank account."""
    from accounting.services import BankReconciliationService
    return BankReconciliationService.parse_mpesa_statement(bank_account=bank_account, csv_content=csv_content, user=user)


def parse_bank_statement(bank_account: Any, csv_content: str, user: Any = None) -> Any:
    """Parse a standard Kenyan bank CSV statement for a bank account."""
    from accounting.services import BankReconciliationService
    return BankReconciliationService.parse_bank_statement(bank_account=bank_account, csv_content=csv_content, user=user)


def auto_reconcile_statement(statement: Any) -> Dict[str, int]:
    """Execute auto-matching of statement lines to general ledger lines."""
    from accounting.services import BankReconciliationService
    return BankReconciliationService.auto_reconcile(statement=statement)


def get_ar_aging(company: Company, as_of_date: Optional[date] = None, customer_id: Optional[int] = None) -> Dict[str, Any]:
    """Retrieve Accounts Receivable Aging Report."""
    from accounting.selectors import get_ar_aging_report
    return get_ar_aging_report(company=company, as_of_date=as_of_date, customer_id=customer_id)


def get_ap_aging(company: Company, as_of_date: Optional[date] = None, vendor_id: Optional[int] = None) -> Dict[str, Any]:
    """Retrieve Accounts Payable Aging Report."""
    from accounting.selectors import get_ap_aging_report
    return get_ap_aging_report(company=company, as_of_date=as_of_date, vendor_id=vendor_id)


# ─── KENYAN TAX ENGINE API ───────────────────────────────────────────────────

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
    customer_invoice: Optional[Any] = None,
    vendor_bill: Optional[Any] = None,
    journal_entry: Optional[Any] = None,
    notes: str = '',
    user: Any = None
) -> Any:
    """Record a Withholding Tax / WHVAT certificate entry."""
    from accounting.services import TaxService
    return TaxService.record_withholding_tax(
        company=company,
        wht_type=wht_type,
        category=category,
        party_name=party_name,
        transaction_date=transaction_date,
        base_amount=base_amount,
        rate_percentage=rate_percentage,
        party_pin=party_pin,
        certificate_number=certificate_number,
        customer_invoice=customer_invoice,
        vendor_bill=vendor_bill,
        journal_entry=journal_entry,
        notes=notes,
        user=user
    )


def get_vat_return(company: Company, start_date: date, end_date: date) -> Dict[str, Any]:
    """Generate KRA Form VAT 3 return calculation and schedules."""
    from accounting.selectors import get_vat_return_summary
    return get_vat_return_summary(company=company, start_date=start_date, end_date=end_date)


def get_wht_return(company: Company, start_date: date, end_date: date, wht_type: Optional[str] = None) -> Dict[str, Any]:
    """Generate Withholding Tax summary schedule."""
    from accounting.selectors import get_wht_return_summary
    return get_wht_return_summary(company=company, start_date=start_date, end_date=end_date, wht_type=wht_type)


def export_itax_vat_sales_csv(company: Company, start_date: date, end_date: date) -> str:
    """Export KRA iTax formatted CSV for Sales Schedule."""
    from accounting.services import TaxService
    return TaxService.export_itax_vat_sales_csv(company=company, start_date=start_date, end_date=end_date)


def export_itax_vat_purchases_csv(company: Company, start_date: date, end_date: date) -> str:
    """Export KRA iTax formatted CSV for Purchases Schedule."""
    from accounting.services import TaxService
    return TaxService.export_itax_vat_purchases_csv(company=company, start_date=start_date, end_date=end_date)


def export_itax_wht_csv(company: Company, start_date: date, end_date: date, wht_type: Optional[str] = None) -> str:
    """Export KRA iTax formatted CSV for Withholding Tax."""
    from accounting.services import TaxService
    return TaxService.export_itax_wht_csv(company=company, start_date=start_date, end_date=end_date, wht_type=wht_type)


# ─── FINANCIAL STATEMENTS API ────────────────────────────────────────────────

def get_income_statement(
    company: Company,
    start_date: date,
    end_date: date,
    branch: Optional[Any] = None,
    compare_start_date: Optional[date] = None,
    compare_end_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Retrieve multi-period IFRS Income Statement (P&L)."""
    from accounting.selectors import get_income_statement as _get_is
    return _get_is(
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
    branch: Optional[Any] = None,
    compare_as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Retrieve Classified Statement of Financial Position (Balance Sheet)."""
    from accounting.selectors import get_balance_sheet as _get_bs
    return _get_bs(
        company=company,
        as_of_date=as_of_date,
        branch=branch,
        compare_as_of_date=compare_as_of_date,
    )


def get_cash_flow_statement(
    company: Company,
    start_date: date,
    end_date: date,
    branch: Optional[Any] = None
) -> Dict[str, Any]:
    """Retrieve Statement of Cash Flows via indirect method (IAS 7)."""
    from accounting.selectors import get_cash_flow_statement as _get_cfs
    return _get_cfs(
        company=company,
        start_date=start_date,
        end_date=end_date,
        branch=branch,
    )



