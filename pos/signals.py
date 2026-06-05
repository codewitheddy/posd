"""
Django signals that fire webhook events on model changes.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


def _sale_data(sale):
    return {
        'id': sale.id,
        'invoice_number': sale.invoice_number,
        'total': str(sale.total),
        'cashier': sale.cashier.username if sale.cashier else None,
        'customer': sale.customer.name if sale.customer else None,
        'date': sale.date.isoformat() if sale.date else None,
    }


def _product_data(product):
    return {
        'id': product.id,
        'name': product.name,
        'product_code': product.product_code,
        'stock_quantity': product.stock_quantity,
        'low_stock_threshold': product.low_stock_threshold,
    }


@receiver(post_save, sender='pos.Sale')
def on_sale_saved(sender, instance, created, **kwargs):
    if not created:
        return
    from .webhook_service import dispatch_event
    dispatch_event('sale.created', _sale_data(instance), instance.business)

    # Check stock levels for each item sold
    for item in instance.items.select_related('product'):
        p = item.product
        if p.stock_quantity == 0:
            dispatch_event('product.out_of_stock', _product_data(p), instance.business)
        elif p.stock_quantity <= p.low_stock_threshold:
            dispatch_event('product.low_stock', _product_data(p), instance.business)


@receiver(post_save, sender='pos.SaleReturn')
def on_sale_returned(sender, instance, created, **kwargs):
    """Fire sale.refunded when a SaleReturn record is created."""
    if not created:
        return
    if not instance.original_sale:
        return
    from .webhook_service import dispatch_event
    data = {
        'id': instance.id,
        'return_number': instance.return_number,
        'original_sale_id': instance.original_sale_id,
        'original_invoice_number': instance.original_sale.invoice_number,
        'total_refund': str(instance.total_refund),
        'refund_method': instance.refund_method.name if instance.refund_method else None,
    }
    dispatch_event('sale.refunded', data, instance.original_sale.business)


@receiver(post_save, sender='pos.SalePayment')
def on_payment_received(sender, instance, created, **kwargs):
    """Fire payment.received when a SalePayment record is created."""
    if not created:
        return
    from .webhook_service import dispatch_event
    data = {
        'id': instance.id,
        'sale_id': instance.sale_id,
        'invoice_number': instance.sale.invoice_number if instance.sale else None,
        'payment_method': instance.payment_method.name if instance.payment_method else None,
        'amount': str(instance.amount),
        'reference': instance.reference_number or '',
    }
    dispatch_event('payment.received', data, instance.business)


@receiver(post_save, sender='pos.StockAdjustment')
def on_stock_adjusted(sender, instance, created, **kwargs):
    if not created:
        return
    from .webhook_service import dispatch_event
    data = {
        'id': instance.id,
        'product': _product_data(instance.product),
        'adjustment_type': instance.adjustment_type,
        'quantity': instance.quantity_change,
        'reason': instance.reason,
    }
    dispatch_event('stock.adjusted', data, instance.business)


@receiver(post_save, sender='pos.Purchase')
def on_purchase_saved(sender, instance, created, **kwargs):
    from .webhook_service import dispatch_event
    if created:
        event = 'purchase.created'
    elif instance.status == 'received':
        # Only fire once — check if status just changed to 'received'
        # We use update_fields hint if available; otherwise fire conservatively
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'status' not in update_fields:
            return
        event = 'purchase.received'
    else:
        return
    data = {
        'id': instance.id,
        'purchase_number': instance.purchase_number,
        'supplier': instance.supplier.name if instance.supplier else None,
        'total_amount': str(instance.total_amount),
        'status': instance.status,
    }
    dispatch_event(event, data, instance.business)


@receiver(post_save, sender='pos.Customer')
def on_customer_created(sender, instance, created, **kwargs):
    if not created:
        return
    from .webhook_service import dispatch_event
    data = {
        'id': instance.id,
        'name': instance.name,
        'email': instance.email,
        'phone': instance.phone,
    }
    dispatch_event('customer.created', data, instance.business)
