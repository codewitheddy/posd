"""
Inventory & General Ledger Reconciliation Service
Comprehensive multi-level reconciliation between Product Master, Branch Stock,
the Append-Only Stock Ledger, and the General Ledger (Account 1200 Inventory Asset).
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from django.db.models import Sum, F, Value, DecimalField
from django.db.models.functions import Coalesce

from core.models.organization import Company
from inventory.models import Warehouse, StockLedgerEntry
from pos.models import Business, Product, Branch, BranchStock, POSGLMapping
from accounting.models import Account, JournalEntryLine

logger = logging.getLogger(__name__)


def perform_stock_reconciliation(
    business: Business,
    company: Optional[Company] = None
) -> Dict[str, Any]:
    """
    Run an end-to-end reconciliation audit for a business across:
    1. Product Master vs Branch Stock sums
    2. Product Master vs Stock Ledger append-only running movements
    3. Operational Stock Valuation vs GL 1200 Inventory Asset Account Balance

    Returns an actionable audit report dictionary.
    """
    if not company:
        from pos.models import _get_or_create_core_company_and_branch
        company, _ = _get_or_create_core_company_and_branch(business)

    discrepancies: List[Dict[str, Any]] = []
    total_products = 0
    total_operational_valuation = Decimal('0.00')

    # Query products with branch stock totals
    products = Product.objects.filter(business=business, is_active=True).annotate(
        sum_branch_stock=Coalesce(
            Sum('branch_stocks__quantity'),
            Value(Decimal('0.000'), output_field=DecimalField(max_digits=12, decimal_places=3))
        )
    )

    branches_exist = Branch.objects.filter(business=business, is_active=True).exists()

    for p in products:
        total_products += 1
        master_qty = p.stock_quantity or Decimal('0.000')
        cost_price = p.cost_price or Decimal('0.00')
        item_val = (master_qty * cost_price).quantize(Decimal('0.01'))
        if item_val > Decimal('0.00'):
            total_operational_valuation += item_val

        # Check 1: Branch stock sync (only if branches exist)
        if branches_exist:
            branch_sum = p.sum_branch_stock
            if abs(master_qty - branch_sum) > Decimal('0.001'):
                discrepancies.append({
                    'type': 'branch_stock_mismatch',
                    'product_id': p.id,
                    'sku': p.sku or str(p.id),
                    'product_name': p.name,
                    'master_quantity': master_qty,
                    'branch_sum_quantity': branch_sum,
                    'variance': master_qty - branch_sum,
                    'severity': 'HIGH'
                })

        # Check 2: Stock Ledger Running Movements
        if company:
            ledger_sum = StockLedgerEntry.objects.filter(
                company=company, product=p
            ).aggregate(
                total=Coalesce(Sum('quantity'), Value(Decimal('0.000'), output_field=DecimalField(max_digits=12, decimal_places=3)))
            )['total']

            # If ledger entries exist for this product, compare
            if StockLedgerEntry.objects.filter(company=company, product=p).exists():
                if abs(master_qty - ledger_sum) > Decimal('0.001'):
                    discrepancies.append({
                        'type': 'ledger_movement_mismatch',
                        'product_id': p.id,
                        'sku': p.sku or str(p.id),
                        'product_name': p.name,
                        'master_quantity': master_qty,
                        'ledger_quantity': ledger_sum,
                        'variance': master_qty - ledger_sum,
                        'severity': 'MEDIUM'
                    })

    # Check 3: General Ledger Account 1200 Balance
    gl_balance = Decimal('0.00')
    gl_inventory_code = '1200'
    gl_map = POSGLMapping.get_for_business(business)
    if gl_map and gl_map.inventory_account_code:
        gl_inventory_code = gl_map.inventory_account_code

    if company:
        inv_account = Account.objects.filter(company=company, code=gl_inventory_code).first()
        if inv_account:
            # Asset account: Balance = Debits - Credits
            lines = JournalEntryLine.objects.filter(
                entry__company=company,
                entry__status='posted',
                account=inv_account
            ).aggregate(
                total_dr=Coalesce(Sum('debit'), Value(Decimal('0.00'), output_field=DecimalField(max_digits=18, decimal_places=2))),
                total_cr=Coalesce(Sum('credit'), Value(Decimal('0.00'), output_field=DecimalField(max_digits=18, decimal_places=2))),
            )
            gl_balance = lines['total_dr'] - lines['total_cr']

    valuation_variance = total_operational_valuation - gl_balance
    is_valuation_balanced = abs(valuation_variance) < Decimal('0.05')

    status = 'HEALTHY'
    if discrepancies or not is_valuation_balanced:
        status = 'DISCREPANCY_DETECTED' if any(d['severity'] == 'HIGH' for d in discrepancies) else 'WARNING'

    return {
        'status': status,
        'business_name': business.name,
        'total_products_checked': total_products,
        'total_operational_valuation': total_operational_valuation,
        'gl_inventory_code': gl_inventory_code,
        'gl_account_balance': gl_balance,
        'valuation_variance': valuation_variance,
        'is_valuation_balanced': is_valuation_balanced,
        'discrepancies_count': len(discrepancies),
        'discrepancies': discrepancies,
    }
