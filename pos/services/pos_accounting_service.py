"""
POS to Accounting General Ledger Integration Service
Connects POS Z-Reports and Daily Sales Closures to Accounting via public api.py.
Standards: IFRS for SMEs / ICPAK Practice
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from typing import Any, Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _get_core_company_and_branch(pos_business, pos_branch=None):
    """Bridge POS business/branch to Core Company/Branch."""
    try:
        from pos.models import _get_or_create_core_company_and_branch
        return _get_or_create_core_company_and_branch(pos_business, pos_branch)
    except Exception:
        return None, None


class POSAccountingService:
    """
    Translates closed POS Sessions / Z-Reports into double-entry General Ledger journals.
    """

    @staticmethod
    def post_zreport_to_gl(zreport, user=None) -> Optional[Any]:
        """
        Generates and posts balanced General Ledger journal for a finalized Z-Report.

        Debits:
        - Cash In Till (Cash sales + opening cash adjustments)
        - M-Pesa Clearing (M-Pesa payments)
        - Card Clearing (Card payments)
        - Accounts Receivable (Credit sales)
        - COGS (Cost of goods sold)
        - Cash Shortage (if variance is negative)

        Credits:
        - Sales Revenue (Gross Sales - VAT)
        - VAT Output (16% VAT collected)
        - Inventory Asset (Relief of stock sold at cost)
        - Cash Overage (if variance is positive)
        """
        from pos.models import POSGLMapping, Sale, SalePayment, SaleItem
        from accounting import api

        business = zreport.business
        session = zreport.session
        branch = getattr(session, 'branch', None)
        company, core_branch = _get_core_company_and_branch(business, branch)

        if not company:
            logger.warning("Cannot post Z-Report %s to Accounting: Core Company not found.", zreport.z_number)
            return None

        mapping = POSGLMapping.get_for_business(business)
        report_data = zreport.report_data or {}

        # 1. Aggregate Sales Payments by Method
        sales = Sale.objects.filter(session=session)
        if not sales.exists():
            sales = Sale.objects.filter(id__in=[s.get('id') for s in report_data.get('sales', []) if s.get('id')])

        payments = SalePayment.objects.filter(sale__in=sales)

        cash_total = Decimal('0.00')
        mpesa_total = Decimal('0.00')
        card_total = Decimal('0.00')
        credit_total = Decimal('0.00')
        other_payments_total = Decimal('0.00')

        for p in payments.select_related('payment_method'):
            method_code = p.payment_method.code.upper() if (p.payment_method and p.payment_method.code) else 'CASH'
            amt = p.amount or Decimal('0.00')
            if 'CASH' in method_code:
                cash_total += amt
            elif 'MPESA' in method_code or 'M-PESA' in method_code:
                mpesa_total += amt
            elif 'CARD' in method_code or 'VISA' in method_code or 'MASTERCARD' in method_code:
                card_total += amt
            elif 'CREDIT' in method_code or 'INVOICE' in method_code:
                credit_total += amt
            else:
                other_payments_total += amt

        # Fallback to report_data dictionary if payments queryset is empty
        if cash_total == Decimal('0.00') and mpesa_total == Decimal('0.00') and card_total == Decimal('0.00'):
            payment_breakdown = report_data.get('payment_breakdown', {})
            if isinstance(payment_breakdown, dict):
                breakdown_iter = payment_breakdown.items()
            elif isinstance(payment_breakdown, list):
                breakdown_iter = [
                    (item.get('name') or item.get('method') or item.get('payment_method'), item.get('amount') or item.get('total'))
                    for item in payment_breakdown if isinstance(item, dict)
                ]
            else:
                breakdown_iter = []
            for m_name, m_amt in breakdown_iter:
                m_upper = str(m_name or '').upper()
                amt = Decimal(str(m_amt or '0.00'))
                if 'CASH' in m_upper:
                    cash_total += amt
                elif 'MPESA' in m_upper or 'M-PESA' in m_upper:
                    mpesa_total += amt
                elif 'CARD' in m_upper:
                    card_total += amt
                elif 'CREDIT' in m_upper:
                    credit_total += amt
                else:
                    cash_total += amt

        # 2. Financial totals: Total Sales, VAT, Net Revenue, COGS
        total_revenue = Decimal(str(report_data.get('total_sales') or report_data.get('total_revenue') or '0.00'))
        if total_revenue == Decimal('0.00'):
            total_revenue = cash_total + mpesa_total + card_total + credit_total + other_payments_total

        total_tax = Decimal(str(report_data.get('total_tax') or '0.00'))
        net_sales = max(Decimal('0.00'), total_revenue - total_tax)

        # Calculate COGS from SaleItems
        total_cogs = Decimal('0.00')
        sale_items = SaleItem.objects.filter(sale__in=sales).select_related('product')
        for item in sale_items:
            unit_cost = item.product.cost_price if (item.product and item.product.cost_price) else Decimal('0.00')
            total_cogs += unit_cost * Decimal(str(item.quantity))

        # Cash variance (blind cash count difference)
        cash_diff = getattr(session, 'cash_difference', Decimal('0.00')) or Decimal('0.00')

        # Construct double-entry journal lines
        lines = []

        # Debit Payment Asset accounts
        if cash_total > Decimal('0.00'):
            lines.append({
                'account_code': mapping.cash_account_code,
                'debit': cash_total,
                'credit': Decimal('0.00'),
                'description': f"Cash collections - Z-Report {zreport.z_number}",
            })

        if mpesa_total > Decimal('0.00'):
            lines.append({
                'account_code': mapping.mpesa_account_code,
                'debit': mpesa_total,
                'credit': Decimal('0.00'),
                'description': f"M-Pesa Till collections - Z-Report {zreport.z_number}",
            })

        if card_total > Decimal('0.00'):
            lines.append({
                'account_code': mapping.card_account_code,
                'debit': card_total,
                'credit': Decimal('0.00'),
                'description': f"Card / Swipe collections - Z-Report {zreport.z_number}",
            })

        if credit_total > Decimal('0.00'):
            lines.append({
                'account_code': mapping.credit_account_code,
                'debit': credit_total,
                'credit': Decimal('0.00'),
                'description': f"Customer AR credit sales - Z-Report {zreport.z_number}",
            })

        if other_payments_total > Decimal('0.00'):
            lines.append({
                'account_code': mapping.cash_account_code,
                'debit': other_payments_total,
                'credit': Decimal('0.00'),
                'description': f"Other tender collections - Z-Report {zreport.z_number}",
            })

        # Credit Sales Revenue and VAT Output
        if net_sales > Decimal('0.00'):
            lines.append({
                'account_code': mapping.sales_revenue_code,
                'debit': Decimal('0.00'),
                'credit': net_sales,
                'description': f"Retail Sales Revenue - Z-Report {zreport.z_number}",
            })

        if total_tax > Decimal('0.00'):
            lines.append({
                'account_code': mapping.vat_output_code,
                'debit': Decimal('0.00'),
                'credit': total_tax,
                'description': f"VAT Output (16%) - Z-Report {zreport.z_number}",
            })

        # COGS and Inventory Asset Relief (if cost data available)
        if total_cogs > Decimal('0.00'):
            lines.append({
                'account_code': mapping.cogs_account_code,
                'debit': total_cogs,
                'credit': Decimal('0.00'),
                'description': f"Cost of goods sold - Z-Report {zreport.z_number}",
            })
            lines.append({
                'account_code': mapping.inventory_account_code,
                'debit': Decimal('0.00'),
                'credit': total_cogs,
                'description': f"Inventory relief - Z-Report {zreport.z_number}",
            })

        # Cash Over / Short Adjustment
        if cash_diff < Decimal('0.00'):
            # Cash shortage: Debit Expense (Shortage) / Credit Cash Till
            short_amt = abs(cash_diff)
            lines.append({
                'account_code': mapping.cash_variance_code,
                'debit': short_amt,
                'credit': Decimal('0.00'),
                'description': f"Cash till shortage - Session #{session.session_number}",
            })
            lines.append({
                'account_code': mapping.cash_account_code,
                'debit': Decimal('0.00'),
                'credit': short_amt,
                'description': f"Cash till shortage adjustment - Session #{session.session_number}",
            })
        elif cash_diff > Decimal('0.00'):
            # Cash overage: Debit Cash Till / Credit Income (Overage)
            over_amt = cash_diff
            lines.append({
                'account_code': mapping.cash_account_code,
                'debit': over_amt,
                'credit': Decimal('0.00'),
                'description': f"Cash till overage - Session #{session.session_number}",
            })
            lines.append({
                'account_code': mapping.cash_variance_code,
                'debit': Decimal('0.00'),
                'credit': over_amt,
                'description': f"Cash till overage income - Session #{session.session_number}",
            })

        if len(lines) < 2:
            logger.info("Z-Report %s has zero sales activity, skipping GL journal posting.", zreport.z_number)
            return None

        txn_date = zreport.created_at.date() if hasattr(zreport, 'created_at') and zreport.created_at else timezone.localdate()
        idempotency_key = f"pos:zreport:{zreport.pk}"
        source_ref_str = f"ZREP-{zreport.z_number}"

        payload = {
            'source_module': 'pos',
            'source_ref': source_ref_str,
            'date': txn_date.isoformat(),
            'narration': f"POS Daily Sales Close - Z-Report #{zreport.z_number} (Session #{session.session_number})",
            'lines': lines,
            'entry_type': 'sales_close',
            'idempotency_key': idempotency_key,
        }

        try:
            entry = api.post_journal(
                company=company,
                source_module='pos',
                source_ref=source_ref_str,
                date_val=txn_date,
                lines=lines,
                narration=payload['narration'],
                posted_by=user,
                idempotency_key=idempotency_key,
                branch=core_branch,
                entry_type='sales_close',
            )
            logger.info("Successfully posted Z-Report %s to General Ledger: Journal #%s", zreport.z_number, entry.entry_number)
            return entry
        except Exception as e:
            logger.error("Failed to post Z-Report %s directly to GL (%s). Queueing for exception review.", zreport.z_number, e)
            queue_item = api.queue_posting(
                company=company,
                payload=payload,
                source_module='pos',
                source_ref=source_ref_str,
                idempotency_key=idempotency_key,
                process_immediately=False,
            )
            queue_item.status = 'failed'
            queue_item.error_message = str(e)
            queue_item.save(update_fields=['status', 'error_message'])
            return queue_item
