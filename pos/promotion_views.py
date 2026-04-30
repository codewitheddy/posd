"""
Promotion management views — list, create, edit, toggle, delete, validate code.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from decimal import Decimal, InvalidOperation

from .models import Promotion, Product, Category, ActivityLog
from .decorators import business_required, business_admin_required


# Use business_admin_required as the manager-level gate for promotions
manager_required = business_admin_required


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_datetime(value, default=None):
    from datetime import datetime
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return timezone.make_aware(datetime.strptime(value.strip(), fmt))
        except (ValueError, AttributeError):
            continue
    return default


def _parse_time(value):
    from datetime import datetime
    try:
        return datetime.strptime(value.strip(), '%H:%M').time()
    except (ValueError, AttributeError):
        return None


def _save_promo_from_post(promo, post, business, user):
    """Populate a Promotion instance from POST data. Returns (ok, error_msg)."""
    promo.business = business
    promo.name = post.get('name', '').strip()
    if not promo.name:
        return False, 'Name is required.'

    promo.code = post.get('code', '').strip().upper()
    promo.description = post.get('description', '').strip()
    promo.promo_type = post.get('promo_type', 'percentage')
    promo.applies_to = post.get('applies_to', 'cart')

    try:
        promo.discount_value = Decimal(post.get('discount_value', '0'))
    except InvalidOperation:
        return False, 'Invalid discount value.'

    try:
        promo.buy_quantity = int(post.get('buy_quantity', 1))
        promo.get_quantity = int(post.get('get_quantity', 1))
    except ValueError:
        return False, 'Invalid buy/get quantities.'

    promo.start_date = _parse_datetime(post.get('start_date', ''))
    promo.end_date = _parse_datetime(post.get('end_date', ''))
    if not promo.start_date or not promo.end_date:
        return False, 'Valid start and end dates are required.'
    if promo.end_date <= promo.start_date:
        return False, 'End date must be after start date.'

    try:
        promo.min_purchase_amount = Decimal(post.get('min_purchase_amount', '0') or '0')
        promo.max_uses = int(post.get('max_uses', '0') or '0')
    except (ValueError, InvalidOperation):
        return False, 'Invalid min purchase or max uses.'

    # Happy hour times
    promo.happy_hour_start = _parse_time(post.get('happy_hour_start', ''))
    promo.happy_hour_end = _parse_time(post.get('happy_hour_end', ''))

    promo.is_active = post.get('is_active') == 'on'
    promo.created_by = promo.created_by or user
    return True, ''


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
@business_required
@manager_required
def promotion_list(request, slug=None):
    """List all promotions for this business."""
    promos = Promotion.objects.filter(
        business=request.business
    ).prefetch_related('applicable_products', 'applicable_categories').order_by('-created_at')

    now = timezone.now()
    active_count = sum(1 for p in promos if p.is_valid(now))

    context = {
        'promos': promos,
        'active_count': active_count,
        'now': now,
    }
    return render(request, 'pos/promotions/list.html', context)


@login_required
@business_required
@manager_required
def promotion_create(request, slug=None):
    """Create a new promotion."""
    products = Product.objects.filter(business=request.business, is_active=True).order_by('name')
    categories = Category.objects.filter(business=request.business).order_by('name')

    if request.method == 'POST':
        promo = Promotion(business=request.business, created_by=request.user)
        ok, err = _save_promo_from_post(promo, request.POST, request.business, request.user)
        if not ok:
            messages.error(request, err)
        else:
            try:
                promo.save()
                # M2M
                promo.applicable_products.set(
                    request.POST.getlist('applicable_products')
                )
                promo.applicable_categories.set(
                    request.POST.getlist('applicable_categories')
                )
                ActivityLog.log_activity(
                    user=request.user, action_type='create',
                    model_name='Promotion', object_id=promo.pk,
                    description=f'Created promotion: {promo.name}',
                    request=request, business=request.business,
                )
                messages.success(request, f'Promotion "{promo.name}" created.')
                return redirect('promotion_list', slug=request.business.slug)
            except Exception as e:
                messages.error(request, f'Error: {e}')

    context = {
        'products': products,
        'categories': categories,
        'promo_types': Promotion.PROMO_TYPES,
        'applies_to_choices': Promotion.APPLIES_TO,
        'now': timezone.now(),
    }
    return render(request, 'pos/promotions/form.html', context)


@login_required
@business_required
@manager_required
def promotion_edit(request, slug=None, pk=None):
    """Edit an existing promotion."""
    promo = get_object_or_404(Promotion, pk=pk, business=request.business)
    products = Product.objects.filter(business=request.business, is_active=True).order_by('name')
    categories = Category.objects.filter(business=request.business).order_by('name')

    if request.method == 'POST':
        ok, err = _save_promo_from_post(promo, request.POST, request.business, request.user)
        if not ok:
            messages.error(request, err)
        else:
            try:
                promo.save()
                promo.applicable_products.set(
                    request.POST.getlist('applicable_products')
                )
                promo.applicable_categories.set(
                    request.POST.getlist('applicable_categories')
                )
                ActivityLog.log_activity(
                    user=request.user, action_type='update',
                    model_name='Promotion', object_id=promo.pk,
                    description=f'Updated promotion: {promo.name}',
                    request=request, business=request.business,
                )
                messages.success(request, f'Promotion "{promo.name}" updated.')
                return redirect('promotion_list', slug=request.business.slug)
            except Exception as e:
                messages.error(request, f'Error: {e}')

    context = {
        'promo': promo,
        'products': products,
        'categories': categories,
        'promo_types': Promotion.PROMO_TYPES,
        'applies_to_choices': Promotion.APPLIES_TO,
        'selected_products': list(promo.applicable_products.values_list('id', flat=True)),
        'selected_categories': list(promo.applicable_categories.values_list('id', flat=True)),
        'now': timezone.now(),
    }
    return render(request, 'pos/promotions/form.html', context)


@login_required
@business_required
@manager_required
@require_POST
def promotion_toggle(request, slug=None, pk=None):
    """Toggle is_active on a promotion."""
    promo = get_object_or_404(Promotion, pk=pk, business=request.business)
    promo.is_active = not promo.is_active
    promo.save(update_fields=['is_active'])
    state = 'enabled' if promo.is_active else 'disabled'
    messages.success(request, f'Promotion "{promo.name}" {state}.')
    ActivityLog.log_activity(
        user=request.user, action_type='update',
        model_name='Promotion', object_id=promo.pk,
        description=f'Promotion {state}: {promo.name}',
        request=request, business=request.business,
    )
    return redirect('promotion_list', slug=request.business.slug)


@login_required
@business_required
@manager_required
@require_POST
def promotion_delete(request, slug=None, pk=None):
    """Delete a promotion."""
    promo = get_object_or_404(Promotion, pk=pk, business=request.business)
    name = promo.name
    promo.delete()
    ActivityLog.log_activity(
        user=request.user, action_type='delete',
        model_name='Promotion', object_id=pk,
        description=f'Deleted promotion: {name}',
        request=request, business=request.business,
    )
    messages.success(request, f'Promotion "{name}" deleted.')
    return redirect('promotion_list', slug=request.business.slug)


# ── AJAX: validate promo code from POS screen ─────────────────────────────────

@login_required
@business_required
def validate_promo_code(request, slug=None):
    """
    AJAX endpoint called from POS screen when cashier enters a promo code.
    POST: { code, cart_total, items: [{product_id, quantity, unit_price, total_price, category_id}] }
    Returns: { ok, discount_amount, description, promo_type, free_items, error }
    """
    import json
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    code = data.get('code', '').strip()
    try:
        cart_total = Decimal(str(data.get('cart_total', 0)))
    except InvalidOperation:
        return JsonResponse({'ok': False, 'error': 'Invalid cart total'}, status=400)

    raw_items = data.get('items', [])
    cart_items = []
    for it in raw_items:
        try:
            cart_items.append({
                'product_id': int(it['product_id']),
                'product_name': it.get('product_name', ''),
                'quantity': Decimal(str(it['quantity'])),
                'unit_price': Decimal(str(it['unit_price'])),
                'total_price': Decimal(str(it['total_price'])),
                'category_id': it.get('category_id'),
            })
        except (KeyError, ValueError, InvalidOperation):
            continue

    from .promotion_service import PromotionService
    result = PromotionService.apply(
        request.business, cart_items, cart_total, promo_code=code
    )

    if result.error:
        return JsonResponse({'ok': False, 'error': result.error})

    if not result.promotion:
        return JsonResponse({'ok': False, 'error': 'No applicable promotion found.'})

    return JsonResponse({
        'ok': True,
        'discount_amount': str(result.discount_amount),
        'description': result.description,
        'promo_type': result.promotion.promo_type,
        'free_items': result.free_items,
        'promo_id': result.promotion.pk,
    })
