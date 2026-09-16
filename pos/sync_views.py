"""
Real-Time Sync Engine for Front Office (POS) and Back Office Synchronization.
Provides Server-Sent Events (SSE) streaming, polling fallback, fast product catalog caching,
and offline checkout synchronization.
"""
import logging
import time
import json
import uuid
from decimal import Decimal

logger = logging.getLogger(__name__)


from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import (
    Business, Product, Category, Branch, POSSession,
    Sale, SaleItem, SalePayment, PaymentMethod, Customer, StockAdjustment
)


CACHE_SYNC_PREFIX = 'pos_sync_events_'
MAX_ROLLING_EVENTS = 100


def emit_sync_event(event_type, payload, business_id=None):
    """
    Broadcasts a synchronization event to the real-time event bus.
    Stores the event in the rolling cache buffer for active SSE listeners and polling clients.
    """
    if not business_id:
        biz = Business.objects.filter(is_active=True, owner__is_superuser=True).order_by('id').first() or Business.objects.filter(is_active=True).order_by('id').first()
        business_id = biz.id if biz else 1

    cache_key = f"{CACHE_SYNC_PREFIX}{business_id}"
    events = cache.get(cache_key, [])
    if not isinstance(events, list):
        events = []

    event_record = {
        'id': str(uuid.uuid4()),
        'type': event_type,
        'payload': payload,
        'timestamp': timezone.now().isoformat(),
    }

    events.append(event_record)
    if len(events) > MAX_ROLLING_EVENTS:
        events = events[-MAX_ROLLING_EVENTS:]

    cache.set(cache_key, events, timeout=86400)
    return event_record


def _get_business_from_request(request):
    """Helper to resolve business context safely"""
    biz = getattr(request, 'business', None)
    if not biz:
        biz = Business.objects.filter(is_active=True, owner__is_superuser=True).order_by('id').first() or Business.objects.filter(is_active=True).order_by('id').first() or Business.objects.first()
    return biz


@login_required
def sync_stream_view(request):
    """
    Server-Sent Events (SSE) stream endpoint.
    Keeps a persistent HTTP connection open, streaming real-time changes
    (price updates, inventory adjustments, sales ticker, drawer events) to active POS screens.
    """
    business = _get_business_from_request(request)
    business_id = business.id if business else 1
    cache_key = f"{CACHE_SYNC_PREFIX}{business_id}"

    last_event_id = request.headers.get('Last-Event-ID') or request.GET.get('last_event_id')

    def event_stream():
        handshake_data = json.dumps({
            'type': 'connected',
            'business_id': business_id,
            'server_time': timezone.now().isoformat(),
            'message': 'Real-Time Sync Connected'
        })
        yield f"event: connect\ndata: {handshake_data}\n\n"

        seen_ids = set()
        if last_event_id:
            seen_ids.add(last_event_id)

        initial_events = cache.get(cache_key, [])
        for ev in initial_events:
            if not last_event_id:
                seen_ids.add(ev.get('id'))

        iteration = 0
        while True:
            iteration += 1
            events = cache.get(cache_key, [])
            new_events = [ev for ev in events if ev.get('id') not in seen_ids]

            for ev in new_events:
                seen_ids.add(ev['id'])
                payload_str = json.dumps(ev)
                yield f"id: {ev['id']}\nevent: {ev['type']}\ndata: {payload_str}\n\n"

            if iteration % 15 == 0:
                yield f": heartbeat {timezone.now().isoformat()}\n\n"

            time.sleep(1.0)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache, no-transform'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
@require_GET
def sync_poll_view(request):
    """
    JSON Polling endpoint for clients without persistent SSE capabilities.
    Returns any events created since the provided 'since' ISO timestamp.
    """
    business = _get_business_from_request(request)
    business_id = business.id if business else 1
    cache_key = f"{CACHE_SYNC_PREFIX}{business_id}"

    since_str = request.GET.get('since', '').strip()
    events = cache.get(cache_key, [])

    if since_str:
        filtered = []
        for ev in events:
            if ev.get('timestamp', '') > since_str:
                filtered.append(ev)
        events = filtered

    return JsonResponse({
        'success': True,
        'events': events,
        'server_time': timezone.now().isoformat(),
        'count': len(events)
    })


@login_required
@require_GET
def sync_products_catalog_view(request):
    """
    High-performance JSON product catalog for Front Office caching.
    Delivers full product details, barcodes, and current stock in a compact format.
    """
    business = _get_business_from_request(request)

    products_qs = Product.objects.filter(is_active=True).select_related('category', 'brand')
    if business:
        products_qs = products_qs.filter(business=business)

    catalog = []
    for p in products_qs:
        tax_rate = 0.0
        if getattr(p, 'vat_code', None) and hasattr(p.vat_code, 'rate'):
            tax_rate = float(p.vat_code.rate)
        elif getattr(p, 'tax_class', '') == 'standard':
            tax_rate = 16.0

        catalog.append({
            'id': p.id,
            'name': p.name,
            'barcode': p.barcode or '',
            'product_code': p.product_code or '',
            'category_id': p.category_id,
            'category_name': p.category.name if p.category else 'General',
            'unit_price': float(p.unit_price or 0),
            'cost_price': float(p.cost_price or 0),
            'stock_quantity': float(p.stock_quantity or 0),
            'low_stock_threshold': float(p.low_stock_threshold or 5),
            'tax_rate': tax_rate,
            'is_featured': getattr(p, 'is_featured', False),
            'image_url': p.image.url if getattr(p, 'image', None) else None,
            'updated_at': p.updated_at.isoformat() if hasattr(p, 'updated_at') and p.updated_at else None,
        })

    categories_qs = Category.objects.filter(business=business) if business else Category.objects.all()
    categories = [{'id': c.id, 'name': c.name} for c in categories_qs]

    # Package store settings
    store_settings = {}
    if business:
        from .models import BusinessSettings
        try:
            b_settings = BusinessSettings.get_settings(business)
            logo_url = b_settings.logo.url if b_settings.logo else None
            store_settings = {
                'business_name': b_settings.get_business_name(),
                'business_address': b_settings.business_address or business.address,
                'business_phone': b_settings.business_phone or business.phone,
                'business_email': b_settings.business_email or business.email,
                'business_website': b_settings.business_website or business.website,
                'tax_id': b_settings.tax_id or business.tax_id,
                'logo_url': logo_url,
                'currency_symbol': b_settings.currency_symbol or 'KES',
                'currency_position': b_settings.currency_position or 'before',
                'vat_rate': float(b_settings.vat_rate) if b_settings.vat_rate is not None else 16.0,
                'vat_enabled': b_settings.vat_enabled,
                'receipt_header': b_settings.receipt_header or '',
                'receipt_footer': b_settings.receipt_footer or '',
                'mpesa_enabled': b_settings.mpesa_enabled,
                'mpesa_type': b_settings.mpesa_type or 'paybill',
                'mpesa_shortcode': b_settings.mpesa_shortcode or '',
                'mpesa_phone': b_settings.mpesa_phone or '',
                'mpesa_account_name': b_settings.mpesa_account_name or '',
                'mpesa_account_reference': b_settings.mpesa_account_reference or '',
                'theme_primary': b_settings.theme_primary or '#224195',
            }
        except Exception:
            store_settings = {
                'business_name': business.name,
                'currency_symbol': 'KES',
                'vat_rate': 16.0,
            }

    return JsonResponse({
        'success': True,
        'server_time': timezone.now().isoformat(),
        'count': len(catalog),
        'categories': categories,
        'products': catalog,
        'store_settings': store_settings,
    })


@csrf_exempt
@login_required
@require_POST
def sync_offline_sales_view(request):
    """
    Batch sync endpoint for offline-completed sales.
    Idempotently ingests transactions queued in Front Office IndexedDB during network outages.
    """
    business = _get_business_from_request(request)
    branch = getattr(request, 'branch', None)
    user = request.user
    
    # Check permission to create sales
    membership = getattr(request, 'business_membership', None)
    if not membership:
        from pos.models import BusinessMembership
        membership = BusinessMembership.objects.filter(user=user, business=business, is_active=True).first()
    
    if membership and not membership.has_permission('can_create_sale') and not user.is_superuser:
        return JsonResponse({'success': False, 'error': 'You do not have permission to create sales'}, status=403)

    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

    # Extract sales list from various payload formats
    sales_payload = []
    if isinstance(data, list):
        sales_payload = data
    elif isinstance(data, dict):
        if 'sales' in data and isinstance(data['sales'], list):
            sales_payload = data['sales']
        elif 'outbox' in data and isinstance(data['outbox'], list):
            sales_payload = data['outbox']
        elif 'sale_data' in data and isinstance(data['sale_data'], dict):
            sales_payload = [data['sale_data']]
        elif 'items' in data or 'total' in data:
            sales_payload = [data]

    if not sales_payload:
        return JsonResponse({'success': False, 'error': 'No sales payload provided'}, status=400)

    synced_ids = []
    errors = []

    default_cash = PaymentMethod.objects.filter(business=business, is_active=True).first() or PaymentMethod.objects.filter(is_active=True).first()

    for raw_item in sales_payload:
        item = raw_item.get('data', raw_item) if isinstance(raw_item, dict) else raw_item
        if not isinstance(item, dict):
            continue

        client_uuid = str(item.get('client_uuid') or item.get('idempotency_key') or raw_item.get('id') or uuid.uuid4())
        
        # Idempotency check: if sale already created with this key, acknowledge without re-deducting stock
        existing = Sale.objects.filter(business=business, idempotency_key=client_uuid).first()
        if not existing:
            existing = Sale.objects.filter(business=business, tims_invoice_number=f"OFFLINE-{client_uuid}").first()

        if existing:
            synced_ids.append({
                'client_uuid': client_uuid,
                'sale_id': existing.id,
                'invoice_number': existing.invoice_number,
                'status': 'already_synced'
            })
            continue

        try:
            with transaction.atomic():
                total_amount = Decimal(str(item.get('total', '0')))
                subtotal = Decimal(str(item.get('subtotal', total_amount)))
                tax_amount = Decimal(str(item.get('tax') or item.get('vat_amount') or '0'))
                discount_amount = Decimal(str(item.get('discount') or item.get('discount_amount') or '0'))
                discount_type = item.get('discount_type', 'percentage')
                discount_value = Decimal(str(item.get('discount_value', '0')))
                amount_paid = Decimal(str(item.get('amount_paid', total_amount)))
                change_given = Decimal(str(item.get('change_given', '0.00')))
                order_notes = item.get('notes') or item.get('order_notes') or ''

                # Resolve customer
                customer = None
                cust_data = item.get('customer')
                cust_id = item.get('customer_id') or (cust_data.get('id') if isinstance(cust_data, dict) else None)
                if cust_id:
                    customer = Customer.objects.filter(business=business, pk=cust_id).first()

                count = Sale.objects.filter(business=business).count() + 1
                invoice_number = f"INV-{timezone.now().strftime('%Y%m%d')}-{count:04d}"

                open_session = POSSession.objects.filter(
                    business=business, status='open'
                ).filter(
                    Q(cashier=user) | Q(opened_by=user)
                ).order_by('-opened_at').first()

                sale = Sale.objects.create(
                    business=business,
                    branch=branch,
                    session=open_session,
                    invoice_number=invoice_number,
                    idempotency_key=client_uuid,
                    is_offline_sync=True,
                    cashier=user,
                    customer=customer,
                    subtotal=subtotal,
                    vat_amount=tax_amount,
                    discount_type=discount_type,
                    discount_value=discount_value,
                    discount_amount=discount_amount,
                    total=total_amount,
                    amount_paid=amount_paid,
                    change_given=change_given,
                )

                # Line items
                for line in item.get('items', []):
                    prod_id = line.get('product_id') or line.get('id')
                    qty = Decimal(str(line.get('quantity', 1)))
                    unit_price = Decimal(str(line.get('unit_price') or line.get('price') or '0'))
                    item_total = Decimal(str(line.get('total', unit_price * qty)))
                    item_note = line.get('note', '')

                    prod = Product.objects.select_for_update().filter(pk=prod_id, business=business).first()
                    if prod:
                        SaleItem.objects.create(
                            business=business,
                            sale=sale,
                            product=prod,
                            quantity=qty,
                            unit_price=unit_price,
                            total_price=item_total,
                            cost_price_at_sale=prod.cost_price,
                            note=item_note,
                        )
                        prev_qty = prod.stock_quantity
                        prod.deduct_stock(qty)

                        if branch:
                            from .branch_services import BranchStockService
                            try:
                                BranchStockService.deduct(branch, prod, qty)
                            except Exception:
                                pass

                        StockAdjustment.objects.create(
                            business=business,
                            product=prod,
                            branch=branch,
                            adjustment_type='sale',
                            quantity_change=-int(qty),
                            previous_quantity=int(prev_qty),
                            new_quantity=int(prod.stock_quantity),
                            reason=f'Offline Sync Sale: {sale.invoice_number}'
                        )

                # Tender / Payment records
                payments_list = item.get('payments', [])
                if payments_list and isinstance(payments_list, list):
                    for pay in payments_list:
                        pm_id = pay.get('payment_method_id') or pay.get('id')
                        pay_amount = Decimal(str(pay.get('amount', total_amount)))
                        pay_ref = pay.get('reference', '')
                        pm = PaymentMethod.objects.filter(pk=pm_id, business=business).first() if pm_id else default_cash
                        if not pm:
                            pm = default_cash
                        if pm:
                            SalePayment.objects.create(
                                business=business,
                                sale=sale,
                                payment_method=pm,
                                amount=pay_amount,
                                reference=pay_ref,
                            )
                elif default_cash:
                    SalePayment.objects.create(
                        business=business,
                        sale=sale,
                        payment_method=default_cash,
                        amount=amount_paid,
                    )

                # Customer Loyalty points
                if customer and total_amount > 0:
                    try:
                        from .loyalty_service import LoyaltyService
                        LoyaltyService.award_points_for_sale(sale)
                    except Exception:
                        pass

                # Append to EventLog if app available
                try:
                    from events.models import EventLog
                    EventLog.objects.create(
                        uuid=uuid.uuid4(),
                        tenant=business,
                        event_type=EventLog.EVENT_TYPE_SALE_CREATED,
                        payload={
                            'sale_id': sale.id,
                            'invoice_number': sale.invoice_number,
                            'idempotency_key': client_uuid,
                            'total': str(sale.total),
                            'items_count': len(item.get('items', [])),
                        },
                        device_id='offline_sync',
                        sync_status=EventLog.SYNC_STATUS_SYNCED,
                    )
                except Exception:
                    pass

                emit_sync_event('sale_completed', {
                    'sale_id': sale.id,
                    'invoice_number': sale.invoice_number,
                    'total': str(sale.total),
                    'cashier': user.get_full_name() or user.username,
                    'items_count': len(item.get('items', [])),
                    'source': 'offline_sync',
                    'timestamp': timezone.now().isoformat(),
                }, business_id=business.id)

                synced_ids.append({
                    'client_uuid': client_uuid,
                    'sale_id': sale.id,
                    'invoice_number': sale.invoice_number,
                    'status': 'created',
                })

        except Exception as e:
            logger.error("Failed to sync offline sale %s: %s", client_uuid, e, exc_info=True)
            errors.append({'client_uuid': client_uuid, 'error': str(e)})

    return JsonResponse({
        'success': True,
        'synced_count': len(synced_ids),
        'synced': synced_ids,
        'results': synced_ids,
        'errors': errors,
    })


# Legacy route compatibility aliases
@csrf_exempt
def sync_sale(request):
    """Compatibility handler for /api/sales/sync/"""
    return sync_offline_sales_view(request)


@require_GET
def sync_status(request):
    """Compatibility handler for /api/sync/status/"""
    return sync_poll_view(request)

