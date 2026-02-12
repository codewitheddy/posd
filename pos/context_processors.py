"""
Context processors for multi-tenant POS system
"""

def business_context(request):
    """
    Add business context to all templates
    """
    context = {
        'has_business': hasattr(request, 'business') and request.business is not None,
    }
    
    if context['has_business']:
        context['business_slug'] = request.business.slug
    
    return context
