"""
Cache utility functions for POS system
Provides easy-to-use caching decorators and functions
"""

from django.core.cache import cache
from django.conf import settings
from functools import wraps
import hashlib
import json


def get_cache_key(prefix, *args, **kwargs):
    """
    Generate a unique cache key from prefix and arguments
    
    Args:
        prefix: String prefix for the cache key
        *args: Positional arguments to include in key
        **kwargs: Keyword arguments to include in key
    
    Returns:
        String cache key
    """
    # Create a string from all arguments
    key_parts = [str(prefix)]
    key_parts.extend([str(arg) for arg in args])
    key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
    
    # Join and hash if too long
    key_string = ":".join(key_parts)
    if len(key_string) > 200:
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        return f"{prefix}:{key_hash}"
    
    return key_string


def cache_view(timeout=None, key_prefix=None):
    """
    Decorator to cache view results
    
    Usage:
        @cache_view(timeout=300, key_prefix='dashboard')
        def my_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Generate cache key
            if key_prefix:
                cache_key = get_cache_key(
                    key_prefix,
                    request.user.id if request.user.is_authenticated else 'anon',
                    getattr(request, 'business', None).id if hasattr(request, 'business') and request.business else 'no_business',
                    *args,
                    **kwargs
                )
            else:
                cache_key = get_cache_key(
                    view_func.__name__,
                    request.user.id if request.user.is_authenticated else 'anon',
                    *args,
                    **kwargs
                )
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Call view and cache result
            result = view_func(request, *args, **kwargs)
            
            # Determine timeout
            cache_timeout = timeout
            if cache_timeout is None:
                cache_timeout = getattr(settings, 'CACHE_TTL', {}).get('default', 300)
            
            cache.set(cache_key, result, cache_timeout)
            return result
        
        return wrapper
    return decorator


def cache_function(timeout=None, key_prefix=None):
    """
    Decorator to cache function results
    
    Usage:
        @cache_function(timeout=600, key_prefix='product_stats')
        def get_product_stats(business_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            if key_prefix:
                cache_key = get_cache_key(key_prefix, *args, **kwargs)
            else:
                cache_key = get_cache_key(func.__name__, *args, **kwargs)
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Call function and cache result
            result = func(*args, **kwargs)
            
            # Determine timeout
            cache_timeout = timeout
            if cache_timeout is None:
                cache_timeout = getattr(settings, 'CACHE_TTL', {}).get('default', 300)
            
            cache.set(cache_key, result, cache_timeout)
            return result
        
        return wrapper
    return decorator


def invalidate_cache(pattern):
    """
    Invalidate cache keys matching a pattern
    
    Args:
        pattern: String pattern to match (e.g., 'dashboard:*')
    """
    try:
        # Try Redis-specific delete pattern
        cache.delete_pattern(pattern)
    except AttributeError:
        # Fallback for non-Redis backends
        pass


def invalidate_business_cache(business_id):
    """
    Invalidate all cache for a specific business
    
    Args:
        business_id: ID of the business
    """
    patterns = [
        f'dashboard:*:{business_id}:*',
        f'products:*:{business_id}:*',
        f'reports:*:{business_id}:*',
        f'customers:*:{business_id}:*',
    ]
    
    for pattern in patterns:
        invalidate_cache(pattern)


def get_or_set_cache(key, callable_func, timeout=None):
    """
    Get value from cache or set it by calling a function
    
    Args:
        key: Cache key
        callable_func: Function to call if cache miss
        timeout: Cache timeout in seconds
    
    Returns:
        Cached or computed value
    """
    result = cache.get(key)
    if result is not None:
        return result
    
    result = callable_func()
    
    if timeout is None:
        timeout = getattr(settings, 'CACHE_TTL', {}).get('default', 300)
    
    cache.set(key, result, timeout)
    return result


# Convenience functions for common cache operations

def cache_dashboard_data(business_id, date, data, timeout=None):
    """Cache dashboard data for a specific business and date"""
    key = get_cache_key('dashboard', business_id, date)
    if timeout is None:
        timeout = getattr(settings, 'CACHE_TTL', {}).get('dashboard', 300)
    cache.set(key, data, timeout)


def get_cached_dashboard_data(business_id, date):
    """Get cached dashboard data"""
    key = get_cache_key('dashboard', business_id, date)
    return cache.get(key)


def cache_report_data(report_type, business_id, params, data, timeout=None):
    """Cache report data"""
    key = get_cache_key('report', report_type, business_id, **params)
    if timeout is None:
        timeout = getattr(settings, 'CACHE_TTL', {}).get('reports', 600)
    cache.set(key, data, timeout)


def get_cached_report_data(report_type, business_id, params):
    """Get cached report data"""
    key = get_cache_key('report', report_type, business_id, **params)
    return cache.get(key)


def clear_cache():
    """Clear all cache (use with caution!)"""
    cache.clear()
