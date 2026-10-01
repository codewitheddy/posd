"""
Stock Adjustment Service
Handles creation, approval, and ledger posting of stock count discrepancies, shrinkage, and write-offs.
"""
from decimal import Decimal
from typing import List, Dict, Any
from django.db import transaction
from django.core.exceptions import ValidationError
from inventory.models import (
    Warehouse,
    StockAdjustmentDocument,
    StockAdjustmentLine,
    StockLedgerEntry,
)
from inventory.services.stock_ledger_service import post_stock_movement
from inventory.services.valuation_service import get_stock_balance
from core.numbering.service import next_document_number
from core.models.organization import Company


@transaction.atomic
def create_stock_adjustment(
    company: Company,
    warehouse: Warehouse,
    reason: str,
    lines_data: List[Dict[str, Any]],
    notes: str = '',
    created_by=None,
    adjustment_date=None,
) -> StockAdjustmentDocument:
    """
    Create a new StockAdjustmentDocument in draft status.
    lines_data format: [{'product': product_obj, 'counted_quantity': Decimal('15'), 'batch_number': ''}]
    """
    adj_number = next_document_number(
        document_type='stock_adjustment',
        company=company,
        branch=warehouse.branch,
        prefix='ADJ',
        format_pattern='{prefix}-{branch_code}-{year}{month:02d}-{seq:04d}',
    )

    create_kwargs = {
        'company': company,
        'warehouse': warehouse,
        'adjustment_number': adj_number,
        'reason': reason,
        'status': StockAdjustmentDocument.STATUS_DRAFT,
        'notes': notes,
        'created_by': created_by,
    }
    if adjustment_date:
        create_kwargs['adjustment_date'] = adjustment_date

    doc = StockAdjustmentDocument.objects.create(**create_kwargs)

    total_var_cost = Decimal('0.00')
    for item in lines_data:
        prod = item['product']
        counted_qty = Decimal(str(item['counted_quantity'])).quantize(Decimal('0.0001'))
        batch = item.get('batch_number', '')

        # Fetch current system balance
        bal_info = get_stock_balance(company, warehouse, prod)
        sys_qty = bal_info['balance_quantity']
        unit_cost = bal_info['valuation_rate']

        var_qty = counted_qty - sys_qty
        var_cost = (var_qty * unit_cost).quantize(Decimal('0.01'))
        total_var_cost += var_cost

        StockAdjustmentLine.objects.create(
            document=doc,
            product=prod,
            system_quantity=sys_qty,
            counted_quantity=counted_qty,
            variance_quantity=var_qty,
            unit_cost=unit_cost,
            total_variance_cost=var_cost,
            batch_number=batch,
        )

    doc.total_variance_value = total_var_cost
    doc.save(update_fields=['total_variance_value'])
    return doc


@transaction.atomic
def post_stock_adjustment(doc: StockAdjustmentDocument, user=None) -> StockAdjustmentDocument:
    """
    Post a StockAdjustmentDocument to the immutable StockLedgerEntry and post
    balanced double-entry General Ledger journals to Accounting.
    """
    if doc.status == StockAdjustmentDocument.STATUS_POSTED:
        raise ValidationError("Adjustment document is already posted.")

    total_variance_cost = Decimal('0.00')

    for line in doc.lines.all():
        if line.variance_quantity == Decimal('0.0000'):
            continue  # No variance to adjust

        post_stock_movement(
            company=doc.company,
            warehouse=doc.warehouse,
            product=line.product,
            voucher_type=StockLedgerEntry.VOUCHER_ADJUSTMENT,
            voucher_no=doc.adjustment_number,
            voucher_line_id=str(line.id),
            quantity=line.variance_quantity,
            unit_cost=line.unit_cost,
            batch_number=line.batch_number,
            narration=f"Adjustment ({doc.get_reason_display()}): System {line.system_quantity} -> Counted {line.counted_quantity}",
            created_by=user,
        )
        total_variance_cost += line.total_variance_cost

    # Post balanced General Ledger Journal Entry to Accounting
    try:
        from accounting import api as accounting_api
        if total_variance_cost != Decimal('0.00'):
            gl_lines = []
            if total_variance_cost < Decimal('0.00'):
                # Net Deficit / Shrinkage / Loss
                loss_amt = abs(total_variance_cost)
                gl_lines.append({
                    'account_code': '5100',
                    'debit': loss_amt,
                    'credit': Decimal('0.00'),
                    'description': f"Stock shrinkage/loss ({doc.get_reason_display()}) - {doc.adjustment_number}",
                })
                gl_lines.append({
                    'account_code': '1200',
                    'debit': Decimal('0.00'),
                    'credit': loss_amt,
                    'description': f"Inventory reduction - {doc.adjustment_number}",
                })
            else:
                # Net Surplus / Found Stock
                surplus_amt = total_variance_cost
                gl_lines.append({
                    'account_code': '1200',
                    'debit': surplus_amt,
                    'credit': Decimal('0.00'),
                    'description': f"Inventory surplus - {doc.adjustment_number}",
                })
                gl_lines.append({
                    'account_code': '5100',
                    'debit': Decimal('0.00'),
                    'credit': surplus_amt,
                    'description': f"Stock count surplus ({doc.get_reason_display()}) - {doc.adjustment_number}",
                })

            accounting_api.post_journal(
                company=doc.company,
                source_module='inventory',
                source_ref=doc.adjustment_number,
                date_val=doc.adjustment_date,
                lines=gl_lines,
                narration=f"Stock Adjustment {doc.adjustment_number} ({doc.get_reason_display()})",
                posted_by=user,
                branch=doc.warehouse.branch if doc.warehouse else None,
                entry_type='manual',
            )
    except Exception as gl_err:
        import logging
        logging.getLogger(__name__).warning("Could not auto-post GL journal for Stock Adjustment %s: %s", doc.adjustment_number, gl_err)

    doc.status = StockAdjustmentDocument.STATUS_POSTED
    doc.save(update_fields=['status', 'updated_at'])
    return doc
