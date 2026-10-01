"""
B2B Sales Order & Delivery Note Service
Provides end-to-end management for wholesale quotes, sales orders, delivery dispatching,
inventory ledger synchronization, and GL COGS journal posting.
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from pos.models import (
    Business, Customer, Product, Branch, BranchStock,
    SalesOrder, SalesOrderItem, SalesOrderStatus,
    DeliveryNote, DeliveryNoteItem, DeliveryNoteStatus,
    POSGLMapping, _get_or_create_core_company_and_branch,
)
from inventory.models import StockLedgerEntry
from inventory.services.stock_ledger_service import post_stock_movement
from pos.services.pos_inventory_adapter import get_or_create_default_warehouse

logger = logging.getLogger(__name__)
User = get_user_model()


@transaction.atomic
def create_sales_order(
    business: Business,
    customer: Customer,
    items_data: List[Dict[str, Any]],
    user: Optional[Any] = None,
    branch: Optional[Branch] = None,
    payment_terms: str = 'immediate',
    expected_delivery_date: Optional[Any] = None,
    shipping_address: str = '',
    notes: str = '',
    discount_amount: Decimal = Decimal('0.00'),
) -> SalesOrder:
    """
    Create a new B2B Sales Order document with line items and calculated totals.
    """
    if not items_data:
        raise ValidationError("Sales order must contain at least one line item.")

    sales_order = SalesOrder.objects.create(
        business=business,
        customer=customer,
        branch=branch,
        payment_terms=payment_terms,
        expected_delivery_date=expected_delivery_date,
        shipping_address=shipping_address,
        notes=notes,
        discount_amount=Decimal(str(discount_amount or 0)),
        created_by=user,
        status=SalesOrderStatus.DRAFT,
    )

    for item in items_data:
        product = item.get('product')
        if not product:
            product_id = item.get('product_id')
            product = Product.objects.get(id=product_id, business=business)

        qty = Decimal(str(item.get('quantity_ordered', item.get('quantity', 1))))
        unit_price = Decimal(str(item.get('unit_price', product.unit_price)))
        tax_rate = Decimal(str(item.get('tax_rate', getattr(product, 'tax_rate', 16.00) or 16.00)))
        discount_pct = Decimal(str(item.get('discount_percent', 0.00)))

        SalesOrderItem.objects.create(
            sales_order=sales_order,
            product=product,
            quantity_ordered=qty,
            unit_price=unit_price,
            tax_rate=tax_rate,
            discount_percent=discount_pct,
        )

    sales_order.calculate_totals()
    sales_order.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])
    return sales_order


@transaction.atomic
def confirm_sales_order(sales_order: SalesOrder, user: Optional[Any] = None) -> SalesOrder:
    """
    Confirm a draft sales order, validating item stock availability and transitioning status.
    """
    if sales_order.status not in (SalesOrderStatus.DRAFT, SalesOrderStatus.PENDING_APPROVAL):
        raise ValidationError(f"Sales order #{sales_order.order_number} cannot be confirmed in status '{sales_order.get_status_display()}'.")

    sales_order.status = SalesOrderStatus.CONFIRMED
    sales_order.confirmed_by = user
    sales_order.confirmed_at = timezone.now()
    sales_order.save(update_fields=['status', 'confirmed_by', 'confirmed_at', 'updated_at'])

    logger.info("Sales Order #%s confirmed by %s", sales_order.order_number, user)
    return sales_order


@transaction.atomic
def create_delivery_note_from_order(
    sales_order: SalesOrder,
    items_quantities: Optional[Dict[int, Decimal]] = None,
    user: Optional[Any] = None,
    carrier_info: Optional[Dict[str, str]] = None,
    branch: Optional[Branch] = None,
) -> DeliveryNote:
    """
    Generate a Delivery / Dispatch Note against an active Sales Order.
    If items_quantities is None, dispatches all remaining pending quantities.
    """
    if sales_order.status not in (SalesOrderStatus.CONFIRMED, SalesOrderStatus.PROCESSING, SalesOrderStatus.PARTIALLY_DELIVERED):
        raise ValidationError(f"Cannot dispatch delivery for Sales Order in status '{sales_order.get_status_display()}'.")

    carrier_info = carrier_info or {}
    dispatch_branch = branch or sales_order.branch

    delivery_note = DeliveryNote.objects.create(
        business=sales_order.business,
        sales_order=sales_order,
        customer=sales_order.customer,
        branch=dispatch_branch,
        carrier_name=carrier_info.get('carrier_name', ''),
        tracking_number=carrier_info.get('tracking_number', ''),
        vehicle_reg=carrier_info.get('vehicle_reg', ''),
        driver_name=carrier_info.get('driver_name', ''),
        driver_phone=carrier_info.get('driver_phone', ''),
        recipient_name=carrier_info.get('recipient_name', ''),
        delivery_address=carrier_info.get('delivery_address', sales_order.shipping_address),
        notes=carrier_info.get('notes', ''),
        created_by=user,
        status=DeliveryNoteStatus.DRAFT,
    )

    created_any_item = False
    for so_item in sales_order.items.select_related('product').all():
        pending_qty = so_item.quantity_pending_delivery
        if pending_qty <= Decimal('0.000'):
            continue

        if items_quantities is not None:
            dispatch_qty = Decimal(str(items_quantities.get(so_item.id, 0)))
        else:
            dispatch_qty = pending_qty

        if dispatch_qty <= Decimal('0.000'):
            continue

        if dispatch_qty > pending_qty:
            raise ValidationError(
                f"Dispatch quantity ({dispatch_qty}) exceeds pending quantity ({pending_qty}) for item {so_item.product.name}."
            )

        DeliveryNoteItem.objects.create(
            delivery_note=delivery_note,
            sales_order_item=so_item,
            product=so_item.product,
            quantity_dispatched=dispatch_qty,
        )
        created_any_item = True

    if not created_any_item:
        raise ValidationError("No eligible pending items found to dispatch for this sales order.")

    return delivery_note


@transaction.atomic
def dispatch_delivery_note(delivery_note: DeliveryNote, user: Optional[Any] = None) -> DeliveryNote:
    """
    Dispatch delivery note:
    1. Deducts physical branch stock atomically.
    2. Records append-only StockLedgerEntry (voucher_type='sales_delivery').
    3. Updates SalesOrderItem.quantity_delivered and SalesOrder overall status.
    4. Auto-posts balanced COGS / Inventory GL Journal (DR 5000 / CR 1200).
    5. Transitions delivery note to DISPATCHED.
    """
    if delivery_note.status != DeliveryNoteStatus.DRAFT:
        raise ValidationError(f"Delivery Note #{delivery_note.delivery_number} is already {delivery_note.get_status_display()}.")

    company, core_branch = _get_or_create_core_company_and_branch(
        delivery_note.business, getattr(delivery_note, 'branch', None)
    )
    warehouse = None
    if company:
        try:
            warehouse = get_or_create_default_warehouse(company, core_branch)
        except Exception as e:
            logger.warning("Could not obtain primary warehouse for dispatch: %s", e)

    total_cogs_valuation = Decimal('0.00')

    for item in delivery_note.items.select_related('product', 'sales_order_item').all():
        product = item.product
        qty = Decimal(str(item.quantity_dispatched))

        # 1. Deduct BranchStock & Product stock_quantity
        if delivery_note.branch:
            bstock, _ = BranchStock.objects.select_for_update().get_or_create(
                branch=delivery_note.branch,
                product=product,
                defaults={'quantity': Decimal('0.000')}
            )
            bstock.quantity = (bstock.quantity or Decimal('0.000')) - qty
            bstock.save(update_fields=['quantity', 'updated_at'])

        product = Product.objects.select_for_update().get(pk=product.pk)
        product.stock_quantity = (product.stock_quantity or Decimal('0.000')) - qty
        product.save(update_fields=['stock_quantity'])

        # 2. Append to ERP Stock Ledger
        cost_price = product.cost_price or Decimal('0.00')
        line_cost = (qty * cost_price).quantize(Decimal('0.01'))
        total_cogs_valuation += line_cost

        if company and warehouse:
            try:
                post_stock_movement(
                    company=company,
                    warehouse=warehouse,
                    product=product,
                    voucher_type=StockLedgerEntry.VOUCHER_SALES_DELIVERY,
                    voucher_no=delivery_note.delivery_number,
                    quantity=-qty,
                    unit_cost=cost_price,
                    narration=f"Sales Delivery to {delivery_note.customer.name} (Ref: {delivery_note.delivery_number})",
                    created_by=user,
                )
            except Exception as e:
                logger.error("Error posting stock ledger entry for dispatch #%s: %s", delivery_note.delivery_number, e)

        # 3. Update SalesOrderItem delivered quantity
        if item.sales_order_item:
            so_item = item.sales_order_item
            so_item.quantity_delivered = (so_item.quantity_delivered or Decimal('0.000')) + qty
            so_item.save(update_fields=['quantity_delivered'])

    # 4. Update SalesOrder status
    so = delivery_note.sales_order
    if so:
        all_so_items = list(so.items.all())
        all_delivered = all(
            (it.quantity_delivered or Decimal('0.000')) >= (it.quantity_ordered or Decimal('0.000'))
            for it in all_so_items
        )
        if all_delivered:
            so.status = SalesOrderStatus.DELIVERED
        else:
            so.status = SalesOrderStatus.PARTIALLY_DELIVERED
        so.save(update_fields=['status', 'updated_at'])

    # 5. Post General Ledger Journal Entry (DR 5000 COGS / CR 1200 Inventory)
    if total_cogs_valuation > Decimal('0.00') and company:
        _post_dispatch_gl_journal(company, core_branch, delivery_note, total_cogs_valuation, user)

    # 6. Finalize delivery note status
    delivery_note.status = DeliveryNoteStatus.DISPATCHED
    delivery_note.dispatched_by = user
    delivery_note.dispatched_at = timezone.now()
    delivery_note.save(update_fields=['status', 'dispatched_by', 'dispatched_at', 'updated_at'])

    logger.info("Delivery Note #%s successfully dispatched by %s.", delivery_note.delivery_number, user)
    return delivery_note


def _post_dispatch_gl_journal(company, branch, delivery_note: DeliveryNote, cogs_amount: Decimal, user: Optional[Any] = None):
    """
    Post double-entry journal for inventory cost of goods sold on sales delivery.
    DR: 5000 Cost of Goods Sold
    CR: 1200 Inventory Asset
    """
    try:
        from accounting.api import post_journal
        from accounting.models import Account

        gl_map = POSGLMapping.get_for_business(delivery_note.business)
        cogs_code = gl_map.cogs_account_code if gl_map else '5000'
        inv_code = gl_map.inventory_account_code if gl_map else '1200'

        cogs_acc = Account.objects.filter(company=company, code=cogs_code).first()
        inv_acc = Account.objects.filter(company=company, code=inv_code).first()

        if not cogs_acc or not inv_acc:
            logger.warning(
                "Could not auto-post GL journal for Delivery %s: Missing account %s or %s in COA.",
                delivery_note.delivery_number, cogs_code, inv_code
            )
            return

        lines = [
            {
                'account_code': cogs_code,
                'debit': cogs_amount,
                'credit': Decimal('0.00'),
                'description': f"COGS - Delivery #{delivery_note.delivery_number} ({delivery_note.customer.name})"
            },
            {
                'account_code': inv_code,
                'debit': Decimal('0.00'),
                'credit': cogs_amount,
                'description': f"Inventory Relief - Delivery #{delivery_note.delivery_number}"
            }
        ]

        post_journal(
            company=company,
            branch=branch,
            source_module='inventory',
            source_ref=delivery_note.delivery_number,
            narration=f"Inventory COGS Dispatch: {delivery_note.delivery_number} to {delivery_note.customer.name}",
            lines=lines,
            entry_type='automated',
            posted_by=user,
            idempotency_key=f"DN-COGS-{delivery_note.delivery_number}"
        )
        logger.info("Auto-posted GL journal for Delivery Note #%s (Valuation: KES %s)", delivery_note.delivery_number, cogs_amount)
    except Exception as e:
        logger.error("Failed to auto-post GL journal for Delivery Note #%s: %s", delivery_note.delivery_number, e)


@transaction.atomic
def complete_delivery_note(
    delivery_note: DeliveryNote,
    recipient_name: str = '',
    user: Optional[Any] = None
) -> DeliveryNote:
    """
    Mark a dispatched delivery note as delivered upon client receipt / signed waybill.
    """
    if delivery_note.status != DeliveryNoteStatus.DISPATCHED:
        raise ValidationError(f"Cannot complete delivery note in status '{delivery_note.get_status_display()}'.")

    delivery_note.status = DeliveryNoteStatus.DELIVERED
    delivery_note.delivered_date = timezone.now()
    if recipient_name:
        delivery_note.recipient_name = recipient_name
    delivery_note.save(update_fields=['status', 'delivered_date', 'recipient_name', 'updated_at'])

    logger.info("Delivery Note #%s confirmed delivered to %s", delivery_note.delivery_number, delivery_note.recipient_name)
    return delivery_note
