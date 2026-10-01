"""
Inventory Selectors
Query helpers for Warehouse stock levels, ledger reports, and low-stock alerts.
"""
from decimal import Decimal
from typing import Optional
from django.db.models import QuerySet, Q, Max, F
from inventory.models import (
    Warehouse,
    StockLedgerEntry,
    StockItemSettings,
)
from core.models.organization import Company


def get_warehouses(
    company: Company,
    branch=None,
    is_active: bool = True,
) -> QuerySet[Warehouse]:
    """Retrieve warehouses scoped to company/branch."""
    qs = Warehouse.objects.filter(company=company, is_active=is_active)
    if branch:
        qs = qs.filter(Q(branch=branch) | Q(branch__isnull=True))
    return qs.select_related('branch', 'manager')


def get_stock_ledger_entries(
    company: Company,
    warehouse: Optional[Warehouse] = None,
    product=None,
    voucher_type: Optional[str] = None,
    start_date=None,
    end_date=None,
) -> QuerySet[StockLedgerEntry]:
    """Retrieve immutable stock ledger entries with filters."""
    qs = StockLedgerEntry.objects.filter(company=company)
    if warehouse:
        qs = qs.filter(warehouse=warehouse)
    if product:
        qs = qs.filter(product=product)
    if voucher_type:
        qs = qs.filter(voucher_type=voucher_type)
    if start_date:
        qs = qs.filter(posting_date__gte=start_date)
    if end_date:
        qs = qs.filter(posting_date__lte=end_date)
    return qs.select_related('warehouse', 'product', 'created_by').order_by('-posting_time', '-id')


def get_low_stock_items(company: Company, warehouse: Optional[Warehouse] = None):
    """
    Retrieve products where current on-hand balance is less than or equal to reorder_level.
    """
    settings_qs = StockItemSettings.objects.filter(company=company, reorder_level__gt=0).select_related('product')
    low_stock = []

    for s in settings_qs:
        last_entry = (
            StockLedgerEntry.objects.filter(company=company, product=s.product)
        )
        if warehouse:
            last_entry = last_entry.filter(warehouse=warehouse)
        latest = last_entry.order_by('-posting_time', '-id').first()
        current_qty = latest.balance_quantity if latest else Decimal('0.0000')

        if current_qty <= s.reorder_level:
            low_stock.append({
                'product': s.product,
                'current_quantity': current_qty,
                'reorder_level': s.reorder_level,
                'reorder_quantity': s.reorder_quantity,
                'shortage': s.reorder_level - current_qty,
            })
    return low_stock
