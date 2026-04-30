"""
events/signals.py — Django post_save signals that create immutable EventLog
records for every POS operation.

Signal-to-EventLog mapping (from design doc):
  Sale        post_save (create)  → sale_created
  Sale        post_save (refund)  → sale_refunded   (handled via SaleReturn)
  Product     post_save           → product_changed
  StockAdjustment post_save       → inventory_updated
  SalePayment post_save (create)  → payment_recorded
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_device_id(instance):
    """Best-effort device ID from the audit request thread-local."""
    try:
        from pos.models import get_audit_request
        request = get_audit_request()
        if request:
            return request.META.get('HTTP_X_DEVICE_ID', request.META.get('REMOTE_ADDR', 'unknown'))
    except Exception:
        pass
    return 'server'


def _get_tenant(instance):
    """Extract the Business (tenant) from a model instance."""
    return getattr(instance, 'business', None)


def _log_event(event_type, payload, instance):
    """Create an EventLog record, swallowing errors so POS ops are never blocked."""
    from events.models import EventLog
    tenant = _get_tenant(instance)
    if tenant is None:
        return
    try:
        EventLog.objects.create(
            tenant=tenant,
            event_type=event_type,
            payload=payload,
            device_id=_get_device_id(instance),
        )
    except Exception as exc:
        logger.error("EventLog creation failed for %s: %s", event_type, exc)


# ── Sale ─────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='pos.Sale')
def on_sale_saved(sender, instance, created, **kwargs):
    if not created:
        return
    _log_event(
        'sale_created',
        {
            'sale_id':     instance.pk,
            'invoice':     instance.invoice_number,
            'total':       str(instance.total),
            'customer_id': instance.customer_id,
            'items': [
                {
                    'product_id': item.product_id,
                    'quantity':   str(item.quantity),
                    'unit_price': str(item.unit_price),
                }
                for item in instance.items.all()
            ],
        },
        instance,
    )


# ── SaleReturn (refund) ───────────────────────────────────────────────────────

@receiver(post_save, sender='pos.SaleReturn')
def on_sale_return_saved(sender, instance, created, **kwargs):
    if not created:
        return
    _log_event(
        'sale_refunded',
        {
            'return_id':    instance.pk,
            'sale_id':      instance.original_sale_id,
            'total_refund': str(instance.total_refund),
            'reason':       instance.reason,
        },
        instance.original_sale if instance.original_sale else instance,
    )


# ── Product ───────────────────────────────────────────────────────────────────

@receiver(post_save, sender='pos.Product')
def on_product_saved(sender, instance, created, **kwargs):
    _log_event(
        'product_changed',
        {
            'product_id':   instance.pk,
            'name':         instance.name,
            'unit_price':   str(instance.unit_price),
            'cost_price':   str(instance.cost_price),
            'is_active':    instance.is_active,
            'action':       'created' if created else 'updated',
        },
        instance,
    )


# ── StockAdjustment ───────────────────────────────────────────────────────────

@receiver(post_save, sender='pos.StockAdjustment')
def on_stock_adjustment_saved(sender, instance, created, **kwargs):
    if not created:
        return
    _log_event(
        'inventory_updated',
        {
            'product_id':    instance.product_id,
            'delta':         str(instance.quantity_change),
            'new_quantity':  str(instance.new_quantity),
            'adjustment_type': instance.adjustment_type,
            'reason':        instance.reason,
        },
        instance,
    )


# ── SalePayment ───────────────────────────────────────────────────────────────

@receiver(post_save, sender='pos.SalePayment')
def on_sale_payment_saved(sender, instance, created, **kwargs):
    if not created:
        return
    _log_event(
        'payment_recorded',
        {
            'sale_id':        instance.sale_id,
            'method':         instance.payment_method.name if instance.payment_method else '',
            'amount':         str(instance.amount),
            'reference':      instance.reference_number,
        },
        instance,
    )
