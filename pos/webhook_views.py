"""
Webhook management views + Integration export endpoints.
"""
import csv
import json
import secrets
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .decorators import business_required
from .models import (
    Business, BusinessMembership, Customer, Product, Purchase,
    Sale, SaleItem, Webhook, WebhookDelivery, APIKey, WEBHOOK_EVENTS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_owner_or_admin(request, business):
    if request.user.is_superuser:
        return True
    return BusinessMembership.objects.filter(
        user=request.user, business=business,
        is_active=True, role__in=['owner', 'admin']
    ).exists()


# ── Webhook CRUD ──────────────────────────────────────────────────────────────

@login_required
@business_required
def webhook_list(request, slug=None):
    business = request.business
    if not _require_owner_or_admin(request, business):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=business.slug)

    hooks = Webhook.objects.filter(business=business).prefetch_related('deliveries')
    for h in hooks:
        h.last_delivery = h.deliveries.first()
        h.success_count = h.deliveries.filter(success=True).count()
        h.fail_count = h.deliveries.filter(success=False).count()

    return render(request, 'pos/webhooks/list.html', {
        'business': business,
        'hooks': hooks,
        'event_choices': WEBHOOK_EVENTS,
    })


@login_required
@business_required
def webhook_create(request, slug=None):
    business = request.business
    if not _require_owner_or_admin(request, business):
        messages.error(request, 'Permission denied.')
        return redirect('webhook_list', slug=business.slug)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        url = request.POST.get('url', '').strip()
        selected_events = request.POST.getlist('events')
        auto_secret = request.POST.get('auto_secret') == '1'
        secret = secrets.token_hex(32) if auto_secret else request.POST.get('secret', '').strip()

        if not name or not url or not selected_events:
            messages.error(request, 'Name, URL and at least one event are required.')
        else:
            Webhook.objects.create(
                business=business, name=name, url=url,
                events=selected_events, secret=secret, is_active=True,
            )
            messages.success(request, f'Webhook "{name}" created.')
            return redirect('webhook_list', slug=business.slug)

    return render(request, 'pos/webhooks/form.html', {
        'business': business,
        'event_choices': WEBHOOK_EVENTS,
        'generated_secret': secrets.token_hex(32),
    })


@login_required
@business_required
def webhook_edit(request, slug=None, pk=None):
    business = request.business
    hook = get_object_or_404(Webhook, pk=pk, business=business)
    if not _require_owner_or_admin(request, business):
        messages.error(request, 'Permission denied.')
        return redirect('webhook_list', slug=business.slug)

    if request.method == 'POST':
        hook.name = request.POST.get('name', hook.name).strip()
        hook.url = request.POST.get('url', hook.url).strip()
        hook.events = request.POST.getlist('events')
        hook.is_active = request.POST.get('is_active') == '1'
        new_secret = request.POST.get('secret', '').strip()
        if new_secret:
            hook.secret = new_secret
        hook.save()
        messages.success(request, 'Webhook updated.')
        return redirect('webhook_list', slug=business.slug)

    return render(request, 'pos/webhooks/form.html', {
        'business': business,
        'hook': hook,
        'event_choices': WEBHOOK_EVENTS,
    })


@login_required
@business_required
@require_POST
def webhook_delete(request, slug=None, pk=None):
    business = request.business
    hook = get_object_or_404(Webhook, pk=pk, business=business)
    if not _require_owner_or_admin(request, business):
        messages.error(request, 'Permission denied.')
        return redirect('webhook_list', slug=business.slug)
    hook.delete()
    messages.success(request, 'Webhook deleted.')
    return redirect('webhook_list', slug=business.slug)


@login_required
@business_required
@require_POST
def webhook_test(request, slug=None, pk=None):
    """Send a test ping payload to the webhook URL."""
    business = request.business
    hook = get_object_or_404(Webhook, pk=pk, business=business)
    if not _require_owner_or_admin(request, business):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    from .webhook_service import _deliver_inline
    _deliver_inline(hook, 'test.ping', {
        'message': 'This is a test ping from Marid POS',
        'timestamp': timezone.now().isoformat(),
    })
    last = hook.deliveries.first()
    return JsonResponse({
        'success': last.success if last else False,
        'status': last.response_status if last else None,
        'body': last.response_body[:500] if last else '',
    })


@login_required
@business_required
def webhook_deliveries(request, slug=None, pk=None):
    business = request.business
    hook = get_object_or_404(Webhook, pk=pk, business=business)
    deliveries = hook.deliveries.all()[:50]
    return render(request, 'pos/webhooks/deliveries.html', {
        'business': business,
        'hook': hook,
        'deliveries': deliveries,
    })


# ── Integration Export Endpoints ──────────────────────────────────────────────

@login_required
@business_required
def integration_hub(request, slug=None):
    """Landing page for all integration options."""
    business = request.business
    if not _require_owner_or_admin(request, business):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=business.slug)

    accounting_apps = [
        ('QuickBooks', 'bi-calculator', 'Import sales CSV via QuickBooks Desktop or Online import wizard.'),
        ('Xero', 'bi-bar-chart-line', 'Use the sales CSV to create invoices via Xero import.'),
        ('Sage', 'bi-journal-text', 'Import product and sales data using the CSV export format.'),
    ]
    api_keys = APIKey.objects.filter(business=business, is_active=True)
    active_webhook_count = Webhook.objects.filter(business=business, is_active=True).count()

    return render(request, 'pos/integrations/hub.html', {
        'business': business,
        'accounting_apps': accounting_apps,
        'api_keys': api_keys,
        'active_webhook_count': active_webhook_count,
    })


@login_required
@business_required
def export_sales_csv(request, slug=None):
    """
    Export sales as CSV — compatible with QuickBooks / Xero import.
    Query params: start_date, end_date (YYYY-MM-DD)
    """
    business = request.business
    start = request.GET.get('start_date')
    end = request.GET.get('end_date')

    qs = Sale.objects.filter(business=business).select_related(
        'customer', 'cashier'
    ).prefetch_related('items__product', 'payments__payment_method').order_by('date')

    if start:
        qs = qs.filter(date__date__gte=start)
    if end:
        qs = qs.filter(date__date__lte=end)

    response = HttpResponse(content_type='text/csv')
    fname = f"{business.slug}_sales_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'

    writer = csv.writer(response)
    writer.writerow([
        'Date', 'Invoice No', 'Customer', 'Cashier',
        'Subtotal', 'VAT', 'Discount', 'Total',
        'Payment Method', 'Payment Reference', 'Notes',
    ])

    for sale in qs:
        payment_names = ', '.join(p.payment_method.name for p in sale.payments.all() if p.payment_method)
        payment_refs = ', '.join(p.reference_number or '' for p in sale.payments.all())
        writer.writerow([
            sale.date.strftime('%Y-%m-%d %H:%M') if sale.date else '',
            sale.invoice_number or sale.id,
            sale.customer.name if sale.customer else '',
            sale.cashier.get_full_name() or sale.cashier.username if sale.cashier else '',
            sale.subtotal,
            sale.vat_amount,
            sale.discount_amount,
            sale.total,
            payment_names,
            payment_refs,
            '',  # Notes column — Sale model has no notes field
        ])

    return response


@login_required
@business_required
def export_sales_json(request, slug=None):
    """
    Export sales as JSON — generic integration format.
    """
    business = request.business
    start = request.GET.get('start_date')
    end = request.GET.get('end_date')

    qs = Sale.objects.filter(business=business).select_related(
        'customer', 'cashier'
    ).prefetch_related('items__product', 'payments__payment_method').order_by('date')

    if start:
        qs = qs.filter(date__date__gte=start)
    if end:
        qs = qs.filter(date__date__lte=end)

    data = []
    for sale in qs:
        data.append({
            'id': sale.id,
            'sale_number': sale.invoice_number,
            'date': sale.date.isoformat() if sale.date else None,
            'customer': sale.customer.name if sale.customer else None,
            'cashier': sale.cashier.username if sale.cashier else None,
            'subtotal': str(sale.subtotal),
            'vat': str(sale.vat_amount),
            'discount': str(sale.discount_amount),
            'total': str(sale.total),
            'payments': [
                {
                    'method': p.payment_method.name if p.payment_method else None,
                    'amount': str(p.amount),
                    'reference': p.reference_number or '',
                }
                for p in sale.payments.all()
            ],
            'items': [
                {
                    'product': i.product.name if i.product else None,
                    'product_code': i.product.product_code if i.product else None,
                    'quantity': str(i.quantity),
                    'unit_price': str(i.unit_price),
                    'subtotal': str(i.subtotal),
                }
                for i in sale.items.all()
            ],
        })

    return JsonResponse({'business': business.name, 'sales': data, 'count': len(data)})


@login_required
@business_required
def export_products_csv(request, slug=None):
    """Export product catalogue as CSV."""
    business = request.business
    products = Product.objects.filter(business=business).select_related('category').order_by('name')

    response = HttpResponse(content_type='text/csv')
    fname = f"{business.slug}_products_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'

    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Product Code', 'Barcode', 'Category',
        'Unit Price', 'Cost Price', 'Stock Qty', 'Low Stock Threshold',
        'Unit', 'Is Active',
    ])
    for p in products:
        writer.writerow([
            p.name, p.product_code or '', p.barcode or '',
            p.category.name if p.category else '',
            p.unit_price, p.cost_price or '',
            p.stock_quantity, p.low_stock_threshold,
            p.unit.abbreviation if p.unit else '', 'Yes' if p.is_active else 'No',
        ])

    return response


@login_required
@business_required
def export_customers_csv(request, slug=None):
    """Export customer list as CSV."""
    business = request.business
    customers = Customer.objects.filter(business=business).order_by('name')

    response = HttpResponse(content_type='text/csv')
    fname = f"{business.slug}_customers_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{fname}"'

    writer = csv.writer(response)
    writer.writerow([
        'Name', 'Email', 'Phone', 'Tier', 'Loyalty Points',
        'Total Purchases', 'Created',
    ])
    for c in customers:
        writer.writerow([
            c.name, c.email or '', c.phone or '',
            c.tier, c.loyalty_points, c.total_purchases,
            c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
        ])

    return response
