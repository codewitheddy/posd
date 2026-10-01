"""
Inventory Valuation & FIFO Service
Provides FIFO layer depletion calculations, stock balance queries, and stock valuation reports.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List, Tuple
from django.db import models, transaction
from inventory.models import (
    Warehouse,
    StockLedgerEntry,
    ValuationLayer,
)
from core.models.organization import Company


def get_stock_balance(
    company: Company,
    warehouse: Warehouse,
    product,
) -> Dict[str, Decimal]:
    """
    Get real-time balance quantity and valuation rate for a specific product and warehouse.
    """
    last_entry = (
        StockLedgerEntry.objects.filter(
            company=company,
            warehouse=warehouse,
            product=product,
        )
        .order_by('-posting_time', '-id')
        .first()
    )
    if not last_entry:
        return {
            'balance_quantity': Decimal('0.0000'),
            'valuation_rate': Decimal(str(getattr(product, 'cost_price', '0.00'))),
            'balance_value': Decimal('0.00'),
        }

    return {
        'balance_quantity': last_entry.balance_quantity,
        'valuation_rate': last_entry.valuation_rate,
        'balance_value': last_entry.balance_value,
    }


def calculate_fifo_cost(
    company: Company,
    warehouse: Warehouse,
    product,
    quantity_to_consume: Decimal,
) -> Tuple[Decimal, List[Dict[str, Any]]]:
    """
    Simulate or calculate FIFO cost for consuming a specified quantity from open valuation layers.
    Returns: (total_fifo_cost, layers_consumed)
    """
    quantity_to_consume = Decimal(str(quantity_to_consume))
    if quantity_to_consume <= 0:
        return Decimal('0.00'), []

    open_layers = (
        ValuationLayer.objects.filter(
            company=company,
            warehouse=warehouse,
            product=product,
            is_exhausted=False,
        )
        .order_by('received_date', 'id')
    )

    remaining_to_allocate = quantity_to_consume
    total_cost = Decimal('0.00')
    layers_consumed = []

    for layer in open_layers:
        if remaining_to_allocate <= Decimal('0.0000'):
            break

        take_qty = min(layer.remaining_quantity, remaining_to_allocate)
        layer_cost = (take_qty * layer.unit_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_cost += layer_cost

        layers_consumed.append({
            'layer_id': layer.id,
            'quantity_taken': take_qty,
            'unit_cost': layer.unit_cost,
            'layer_cost': layer_cost,
            'batch_number': layer.batch_number,
        })
        remaining_to_allocate -= take_qty

    # If quantity requested exceeds available FIFO layers, cost remaining at product cost_price
    if remaining_to_allocate > Decimal('0.0000'):
        fallback_rate = Decimal(str(getattr(product, 'cost_price', '0.00')))
        fallback_cost = (remaining_to_allocate * fallback_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_cost += fallback_cost
        layers_consumed.append({
            'layer_id': None,
            'quantity_taken': remaining_to_allocate,
            'unit_cost': fallback_rate,
            'layer_cost': fallback_cost,
            'batch_number': 'FALLBACK',
        })

    return total_cost, layers_consumed


def get_inventory_valuation_summary(
    company: Company,
    warehouse: Optional[Warehouse] = None,
) -> Dict[str, Any]:
    """
    Generate aggregate inventory valuation summary across products and warehouses.
    """
    # Get latest entry id for each (warehouse, product) pair
    qs = StockLedgerEntry.objects.filter(company=company)
    if warehouse:
        qs = qs.filter(warehouse=warehouse)

    latest_entries = (
        qs.values('warehouse_id', 'product_id')
        .annotate(latest_id=models.Max('id'))
    )
    latest_ids = [item['latest_id'] for item in latest_entries]

    entries = (
        StockLedgerEntry.objects.filter(id__in=latest_ids, balance_quantity__gt=0)
        .select_related('warehouse', 'product')
        .order_by('warehouse__name', 'product__name')
    )

    total_units = Decimal('0.0000')
    total_valuation = Decimal('0.00')
    items = []

    for entry in entries:
        total_units += entry.balance_quantity
        total_valuation += entry.balance_value
        items.append({
            'warehouse': entry.warehouse,
            'product': entry.product,
            'warehouse_code': entry.warehouse.code,
            'warehouse_name': entry.warehouse.name,
            'product_id': entry.product.id,
            'product_name': entry.product.name,
            'product_code': getattr(entry.product, 'product_code', ''),
            'balance_quantity': entry.balance_quantity,
            'valuation_rate': entry.valuation_rate,
            'balance_value': entry.balance_value,
            'total_value': entry.balance_value,
        })

    return {
        'total_units': total_units,
        'total_valuation': total_valuation,
        'items_count': len(items),
        'items': items,
    }
