"""
Stock Transfer Service
Handles atomic inter-warehouse and inter-branch inventory transfers.
"""
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from django.db import transaction
from django.core.exceptions import ValidationError
from inventory.models import (
    Warehouse,
    StockLedgerEntry,
)
from inventory.services.stock_ledger_service import post_stock_movement
from inventory.services.valuation_service import get_stock_balance
from core.numbering.service import next_document_number
from core.models.organization import Company


@transaction.atomic
def transfer_stock_between_warehouses(
    company: Company,
    source_warehouse: Warehouse,
    target_warehouse: Warehouse,
    items_data: List[Dict[str, Any]],
    narration: str = '',
    user=None,
) -> Tuple[str, List[StockLedgerEntry]]:
    """
    Atomically transfer stock between two warehouses in the same company.
    Posts an outbound movement from source and an inbound movement to target.
    
    items_data format: [{'product': product_obj, 'quantity': Decimal('10'), 'batch_number': ''}]
    """
    if source_warehouse.id == target_warehouse.id:
        raise ValidationError("Source and target warehouse cannot be the same.")

    transfer_no = next_document_number(
        document_type='stock_transfer',
        company=company,
        branch=source_warehouse.branch,
        prefix='TRF',
        format_pattern='{prefix}-{branch_code}-{year}{month:02d}-{seq:04d}',
    )

    ledger_entries = []

    for item in items_data:
        product = item['product']
        quantity = Decimal(str(item['quantity'])).quantize(Decimal('0.0001'))
        batch = item.get('batch_number', '')

        if quantity <= Decimal('0.0000'):
            raise ValidationError(f"Transfer quantity for {product.name} must be greater than zero.")

        # Check source valuation & availability
        source_bal = get_stock_balance(company, source_warehouse, product)
        unit_cost = source_bal['valuation_rate']

        # 1. Outbound from Source Warehouse
        out_entry = post_stock_movement(
            company=company,
            warehouse=source_warehouse,
            product=product,
            voucher_type=StockLedgerEntry.VOUCHER_TRANSFER_OUT,
            voucher_no=transfer_no,
            quantity=-quantity,
            unit_cost=unit_cost,
            batch_number=batch,
            narration=f"Transfer to {target_warehouse.code}: {narration}",
            created_by=user,
        )
        ledger_entries.append(out_entry)

        # 2. Inbound to Target Warehouse
        in_entry = post_stock_movement(
            company=company,
            warehouse=target_warehouse,
            product=product,
            voucher_type=StockLedgerEntry.VOUCHER_TRANSFER_IN,
            voucher_no=transfer_no,
            quantity=quantity,
            unit_cost=unit_cost,
            batch_number=batch,
            narration=f"Transfer from {source_warehouse.code}: {narration}",
            created_by=user,
        )
        ledger_entries.append(in_entry)

    return transfer_no, ledger_entries
