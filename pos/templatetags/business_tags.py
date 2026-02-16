"""
Template tags for multi-tenant business URLs
"""

from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def business_url(context, url_name, *args, **kwargs):
    """
    Generate URL with business slug if business context exists.
    
    Usage:
        {% business_url 'dashboard' %}
        {% business_url 'product_edit' pk=product.id %}
    """
    request = context.get('request')
    
    # If business context exists, add slug to kwargs
    if request and hasattr(request, 'business') and request.business:
        kwargs['slug'] = request.business.slug
    
    try:
        return reverse(url_name, args=args, kwargs=kwargs)
    except:
        # Fallback to business list if URL fails
        return reverse('business_list')


@register.filter
def get_item(dictionary, key):
    """
    Get item from dictionary by key.
    
    Usage:
        {{ my_dict|get_item:key_variable }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def has_feature(business, feature_name):
    """
    Check if business has access to a specific feature.
    
    Usage:
        {% if business|has_feature:"loyalty" %}
        {% if business|has_feature:"grn" %}
    """
    if business is None:
        return False
    return business.has_feature(feature_name)
