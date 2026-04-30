"""
Promotion Service — evaluates which promotions apply to a cart and computes discounts.

Usage in complete_sale:
    from .promotion_service import PromotionService
    result = PromotionService.apply(business, cart_items, cart_total, promo_code=code)
    # result.discount_amount, result.free_items, result.promotion, result.description
"""
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class PromoResult:
    """Result of applying a promotion to a cart."""
    promotion: Optional[object] = None          # Promotion instance or None
    discount_amount: Decimal = Decimal('0')     # KES amount to deduct from cart total
    free_items: List[Dict] = field(default_factory=list)  # [{product_id, qty}] for BOGO
    description: str = ''                       # Human-readable summary
    error: str = ''                             # Non-empty if promo code was invalid


class PromotionService:

    @staticmethod
    def apply(business, cart_items: list, cart_total: Decimal,
              promo_code: str = '') -> PromoResult:
        """
        Evaluate promotions for a cart.

        cart_items: list of dicts with keys: product_id, product, quantity, unit_price, total_price
        cart_total: tax-inclusive total before any promotion discount
        promo_code: optional code entered by cashier

        Returns the best applicable PromoResult (highest discount wins for auto-apply).
        If a promo_code is given, only that promotion is evaluated.
        """
        from .models import Promotion
        from django.utils import timezone

        now = timezone.now()

        if promo_code:
            # Code-based lookup
            try:
                promo = Promotion.objects.prefetch_related(
                    'applicable_products', 'applicable_categories'
                ).get(business=business, code__iexact=promo_code.strip())
            except Promotion.DoesNotExist:
                return PromoResult(error=f'Promo code "{promo_code}" not found.')

            if not promo.is_valid(now):
                return PromoResult(error=f'Promo code "{promo_code}" is not currently valid.')

            if not promo.can_apply_to_cart(cart_total):
                return PromoResult(
                    error=f'Minimum purchase of KES {promo.min_purchase_amount} required.'
                )

            return PromotionService._compute(promo, cart_items, cart_total)

        else:
            # Auto-apply: find all active promotions with no code required
            promos = Promotion.objects.filter(
                business=business,
                is_active=True,
                code='',          # only auto-apply promos (no code)
                start_date__lte=now,
                end_date__gte=now,
            ).prefetch_related('applicable_products', 'applicable_categories')

            best = PromoResult()
            for promo in promos:
                if not promo.is_valid(now):
                    continue
                if not promo.can_apply_to_cart(cart_total):
                    continue
                result = PromotionService._compute(promo, cart_items, cart_total)
                if result.discount_amount > best.discount_amount:
                    best = result

            return best

    @staticmethod
    def _compute(promo, cart_items: list, cart_total: Decimal) -> PromoResult:
        """Compute the discount for a single promotion."""
        pt = promo.promo_type

        # Determine qualifying items
        qualifying = PromotionService._qualifying_items(promo, cart_items)

        if pt == 'percentage':
            base = PromotionService._qualifying_total(promo, cart_items, cart_total)
            discount = (base * promo.discount_value / 100).quantize(Decimal('0.01'))
            return PromoResult(
                promotion=promo,
                discount_amount=discount,
                description=f'{promo.discount_value}% off — {promo.name}',
            )

        elif pt == 'fixed':
            discount = min(promo.discount_value, cart_total).quantize(Decimal('0.01'))
            return PromoResult(
                promotion=promo,
                discount_amount=discount,
                description=f'KES {promo.discount_value} off — {promo.name}',
            )

        elif pt == 'buy_x_get_y':
            # For each qualifying product, calculate how many free units the customer gets
            free_items = []
            total_free_value = Decimal('0')
            for item in qualifying:
                sets = int(item['quantity']) // promo.buy_quantity
                free_qty = sets * promo.get_quantity
                if free_qty > 0:
                    free_value = (item['unit_price'] * free_qty).quantize(Decimal('0.01'))
                    free_items.append({
                        'product_id': item['product_id'],
                        'product_name': item.get('product_name', ''),
                        'qty': free_qty,
                        'value': free_value,
                    })
                    total_free_value += free_value
            label = f'Buy {promo.buy_quantity} Get {promo.get_quantity} Free — {promo.name}'
            return PromoResult(
                promotion=promo,
                discount_amount=total_free_value,
                free_items=free_items,
                description=label,
            )

        elif pt == 'price_cut':
            # Replace unit price with discount_value for qualifying items
            discount = Decimal('0')
            for item in qualifying:
                if item['unit_price'] > promo.discount_value:
                    saving = (item['unit_price'] - promo.discount_value) * item['quantity']
                    discount += saving
            discount = discount.quantize(Decimal('0.01'))
            return PromoResult(
                promotion=promo,
                discount_amount=discount,
                description=f'Price cut to KES {promo.discount_value} — {promo.name}',
            )

        elif pt == 'bundle':
            # Check if all applicable products are in the cart
            required_ids = set(
                promo.applicable_products.values_list('id', flat=True)
            )
            cart_ids = {item['product_id'] for item in cart_items}
            if required_ids and required_ids.issubset(cart_ids):
                bundle_total = sum(
                    item['total_price']
                    for item in cart_items
                    if item['product_id'] in required_ids
                )
                discount = max(Decimal('0'), bundle_total - promo.discount_value)
                discount = discount.quantize(Decimal('0.01'))
                return PromoResult(
                    promotion=promo,
                    discount_amount=discount,
                    description=f'Bundle deal — {promo.name}',
                )
            return PromoResult()

        elif pt == 'happy_hour':
            # Happy hour uses percentage or fixed discount_value
            # (validity already checked in is_valid)
            base = PromotionService._qualifying_total(promo, cart_items, cart_total)
            # Treat discount_value as percentage for happy hour
            discount = (base * promo.discount_value / 100).quantize(Decimal('0.01'))
            return PromoResult(
                promotion=promo,
                discount_amount=discount,
                description=f'Happy Hour {promo.discount_value}% off — {promo.name}',
            )

        return PromoResult()

    @staticmethod
    def _qualifying_items(promo, cart_items: list) -> list:
        """Return cart items that qualify for this promotion's scope."""
        if promo.applies_to == 'cart':
            return cart_items

        product_ids = set(promo.applicable_products.values_list('id', flat=True))
        category_ids = set(promo.applicable_categories.values_list('id', flat=True))

        result = []
        for item in cart_items:
            if promo.applies_to == 'products' and item['product_id'] in product_ids:
                result.append(item)
            elif promo.applies_to == 'category':
                # item must carry category_id for this to work
                if item.get('category_id') in category_ids:
                    result.append(item)
        return result

    @staticmethod
    def _qualifying_total(promo, cart_items: list, cart_total: Decimal) -> Decimal:
        """Return the total value of qualifying items (or full cart if applies_to=cart)."""
        if promo.applies_to == 'cart':
            return cart_total
        qualifying = PromotionService._qualifying_items(promo, cart_items)
        return sum(item['total_price'] for item in qualifying) or Decimal('0')
