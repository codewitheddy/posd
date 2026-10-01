"""
Stock Ledger Service (Append-Only Movement Engine)
Guarantees atomic row-locked stock updates, perpetual weighted average valuation,
and ledger immutability.
"""
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from inventory.models import (
    Warehouse,
    StockLedgerEntry,
    StockItemSettings,
    ValuationLayer,
)
from core.models.organization import Company

logger = logging.getLogger(__name__)


@transaction.atomic
def post_stock_movement(
    company: Company,
    warehouse: Warehouse,
    product,
    voucher_type: str,
    voucher_no: str,
    quantity: Decimal,
    unit_cost: Optional[Decimal] = None,
    voucher_line_id: str = '',
    batch_number: str = '',
    serial_number: str = '',
    expiry_date=None,
    narration: str = '',
    created_by=None,
    is_reversal: bool = False,
    reversed_entry: Optional[StockLedgerEntry] = None,
) -> StockLedgerEntry:
    """
    Append an immutable movement record to the Stock Ledger.
    
    Locks the latest ledger row with select_for_update() to guarantee:
    1. Collision-free, non-race-condition sequential balance calculation.
    2. Strict non-negative inventory enforcement (unless allowed by policy).
    3. Perpetual Weighted Average unit cost computation.
    """
    quantity = Decimal(str(quantity)).quantize(Decimal('0.0001'))
    if quantity == Decimal('0.0000'):
        raise ValidationError("Stock movement quantity cannot be zero.")

    # 1. Fetch Item Settings (Negative stock allowance & valuation method)
    settings_obj = StockItemSettings.objects.filter(company=company, product=product).first()
    allow_negative = settings_obj.allow_negative_stock if settings_obj else False

    # 2. Row lock on latest stock ledger entry for (company, warehouse, product)
    last_entry = (
        StockLedgerEntry.objects.select_for_update()
        .filter(company=company, warehouse=warehouse, product=product)
        .order_by('-posting_time', '-id')
        .first()
    )

    current_balance_qty = last_entry.balance_quantity if last_entry else Decimal('0.0000')
    current_balance_val = last_entry.balance_value if last_entry else Decimal('0.00')
    current_val_rate = last_entry.valuation_rate if last_entry else (
        Decimal(str(getattr(product, 'cost_price', '0.00')))
    )

    new_balance_qty = current_balance_qty + quantity

    # 3. Non-negative stock check
    if new_balance_qty < Decimal('0.0000') and not allow_negative:
        raise ValidationError(
            f"Insufficient stock for {product.name} at {warehouse.code}. "
            f"Current on-hand: {current_balance_qty}, Requested dispatch: {abs(quantity)}."
        )

    # 4. Valuation & Cost Calculation
    if quantity > Decimal('0.0000'):
        # Inbound movement (Receipt / Transfer In / Restock)
        if unit_cost is None:
            unit_cost = current_val_rate
        else:
            unit_cost = Decimal(str(unit_cost)).quantize(Decimal('0.0001'))

        total_cost = (quantity * unit_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        new_balance_val = (current_balance_val + total_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Update Moving Weighted Average Cost
        if new_balance_qty > Decimal('0.0000'):
            new_val_rate = (new_balance_val / new_balance_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        else:
            new_val_rate = unit_cost
    else:
        # Outbound movement (Sale / Dispatch / Transfer Out)
        # Outbound movements consume inventory at current valuation rate
        if unit_cost is None:
            unit_cost = current_val_rate
        else:
            unit_cost = Decimal(str(unit_cost)).quantize(Decimal('0.0001'))

        total_cost = (quantity * unit_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        new_balance_val = (current_balance_val + total_cost).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if new_balance_val < Decimal('0.00') and new_balance_qty == Decimal('0.0000'):
            new_balance_val = Decimal('0.00')

        new_val_rate = current_val_rate if new_balance_qty > 0 else unit_cost

    # 5. Create immutable Stock Ledger Entry
    now = timezone.now()
    entry = StockLedgerEntry.objects.create(
        company=company,
        warehouse=warehouse,
        product=product,
        posting_date=now.date(),
        posting_time=now,
        voucher_type=voucher_type,
        voucher_no=voucher_no,
        voucher_line_id=voucher_line_id,
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=total_cost,
        valuation_rate=new_val_rate,
        balance_quantity=new_balance_qty,
        balance_value=new_balance_val,
        batch_number=batch_number,
        serial_number=serial_number,
        expiry_date=expiry_date,
        is_reversal=is_reversal,
        reversed_entry=reversed_entry,
        narration=narration,
        created_by=created_by,
    )

    # 6. If inbound, create FIFO Valuation Layer
    if quantity > Decimal('0.0000'):
        ValuationLayer.objects.create(
            company=company,
            warehouse=warehouse,
            product=product,
            stock_ledger_entry=entry,
            batch_number=batch_number,
            original_quantity=quantity,
            remaining_quantity=quantity,
            unit_cost=unit_cost,
            received_date=now.date(),
            is_exhausted=False,
        )

    # 7. Sync product stock_quantity for backward compatibility with POS views
    try:
        # Sum total stock across all active warehouses for this product
        total_stock = (
            StockLedgerEntry.objects.filter(company=company, product=product)
            .values('warehouse')
            .annotate(latest_id=models.Max('id'))
        )
        latest_ids = [item['latest_id'] for item in total_stock]
        sum_qty = StockLedgerEntry.objects.filter(id__in=latest_ids).aggregate(
            t=models.Sum('balance_quantity')
        )['t'] or Decimal('0.000')
        
        product.stock_quantity = sum_qty
        product.save(update_fields=['stock_quantity'])
    except Exception:
        pass

    logger.info(
        "StockLedgerEntry #%s posted: %s %s @ %s (%s). New Balance: %s",
        entry.id, entry.quantity, product.name, warehouse.code, voucher_no, new_balance_qty
    )
    return entry


@transaction.atomic
def reverse_stock_movement(
    entry: StockLedgerEntry,
    reason: str,
    user=None,
) -> StockLedgerEntry:
    """
    Reverse a previously posted stock movement by creating an equal and opposite entry.
    """
    if entry.is_reversal:
        raise ValidationError("Cannot reverse an entry that is already a reversal.")

    reversal_quantity = -entry.quantity
    reversal_entry = post_stock_movement(
        company=entry.company,
        warehouse=entry.warehouse,
        product=entry.product,
        voucher_type=StockLedgerEntry.VOUCHER_REVERSAL,
        voucher_no=f"REV-{entry.voucher_no}",
        quantity=reversal_quantity,
        unit_cost=entry.unit_cost,
        narration=f"Reversal of {entry.voucher_no} (#{entry.id}): {reason}",
        created_by=user,
        is_reversal=True,
        reversed_entry=entry,
    )
    return reversal_entry
