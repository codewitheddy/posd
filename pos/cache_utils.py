"""
Caching utilities for frequently accessed data.

Cache keys follow the pattern: pos:{business_id}:{resource}
TTLs are defined in settings.CACHE_TTL.
"""

from django.core.cache import cache
from django.conf import settings

# Default TTLs (seconds) — overridden by settings.CACHE_TTL
_TTL = {
    'products': 1800,       # 30 min — product catalog
    'categories': 3600,     # 1 hr  — rarely changes
    'business_settings': 3600,
    'payment_methods': 3600,
    'dashboard': 300,       # 5 min — dashboard stats
    'reports': 600,         # 10 min
    'customers': 900,       # 15 min
    'loyalty_rewards': 3600,
}


def _ttl(key):
    return getattr(settings, 'CACHE_TTL', {}).get(key, _TTL.get(key, 300))


def _key(business_id, resource, suffix=''):
    return f'pos:{business_id}:{resource}{":" + suffix if suffix else ""}'


def get_cache_key(resource, business_id, *args):
    """Generic cache key builder. Extra args are joined as suffix."""
    suffix = ':'.join(str(a) for a in args) if args else ''
    return _key(business_id, resource, suffix)


# ── Product catalog ──────────────────────────────────────────────────────────

def get_active_products(business_id):
    """Return cached active product queryset (evaluated list)."""
    from .models import Product
    k = _key(business_id, 'products', 'active')
    data = cache.get(k)
    if data is None:
        data = list(
            Product.objects.filter(business_id=business_id, is_active=True)
            .select_related('category')
            .order_by('name')
        )
        cache.set(k, data, _ttl('products'))
    return data


def invalidate_products(business_id):
    cache.delete_pattern(f'pos:{business_id}:products:*') if hasattr(cache, 'delete_pattern') \
        else cache.delete(_key(business_id, 'products', 'active'))


# ── Categories ───────────────────────────────────────────────────────────────

def get_categories(business_id):
    from .models import Category
    k = _key(business_id, 'categories')
    data = cache.get(k)
    if data is None:
        data = list(Category.objects.filter(business_id=business_id).order_by('name'))
        cache.set(k, data, _ttl('categories'))
    return data


def invalidate_categories(business_id):
    cache.delete(_key(business_id, 'categories'))


# ── Business settings ────────────────────────────────────────────────────────

def get_business_settings(business_id):
    from .models import BusinessSettings
    k = _key(business_id, 'business_settings')
    data = cache.get(k)
    if data is None:
        try:
            data = BusinessSettings.objects.get(business_id=business_id)
        except BusinessSettings.DoesNotExist:
            return None
        cache.set(k, data, _ttl('business_settings'))
    return data


def invalidate_business_settings(business_id):
    cache.delete(_key(business_id, 'business_settings'))


# ── Payment methods ──────────────────────────────────────────────────────────

def get_payment_methods(business_id):
    from .models import PaymentMethod
    k = _key(business_id, 'payment_methods')
    data = cache.get(k)
    if data is None:
        data = list(PaymentMethod.objects.filter(business_id=business_id, is_active=True))
        cache.set(k, data, _ttl('payment_methods'))
    return data


def invalidate_payment_methods(business_id):
    cache.delete(_key(business_id, 'payment_methods'))


# ── Loyalty rewards ──────────────────────────────────────────────────────────

def get_loyalty_rewards(business_id):
    from .models import LoyaltyReward
    k = _key(business_id, 'loyalty_rewards')
    data = cache.get(k)
    if data is None:
        data = list(LoyaltyReward.objects.filter(business_id=business_id, is_active=True))
        cache.set(k, data, _ttl('loyalty_rewards'))
    return data


def invalidate_loyalty_rewards(business_id):
    cache.delete(_key(business_id, 'loyalty_rewards'))


# ── Dashboard stats ──────────────────────────────────────────────────────────

def get_dashboard_stats(business_id, date_str):
    """Cache dashboard aggregate stats per business per day."""
    k = _key(business_id, 'dashboard', date_str)
    return cache.get(k)


def set_dashboard_stats(business_id, date_str, data):
    cache.set(_key(business_id, 'dashboard', date_str), data, _ttl('dashboard'))


def invalidate_dashboard(business_id):
    """Call after any sale is created/voided."""
    from django.utils import timezone
    today = timezone.now().date().isoformat()
    cache.delete(_key(business_id, 'dashboard', today))


# ── Generic helpers ──────────────────────────────────────────────────────────

def invalidate_business_cache(business_id):
    """Nuke all cached data for a business (e.g. after settings change)."""
    invalidate_products(business_id)
    invalidate_categories(business_id)
    invalidate_business_settings(business_id)
    invalidate_payment_methods(business_id)
    invalidate_loyalty_rewards(business_id)
    invalidate_dashboard(business_id)
