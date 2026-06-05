"""
Example: Adding Calculator to Django Admin Dashboard

This example shows how to add the calculator widget to the Django admin
so it's available to cashiers working in the POS module.
"""

# File: pos/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import *  # Your models

# Add this to your admin base
class CalculatorAdminMixin:
    """Mixin to add calculator widget to admin pages"""
    
    class Media:
        css = {
            'all': ('css/calculator.css',)
        }
        js = ('js/calculator.js',)
    
    def get_template_list(self):
        """Override to add calculator to change_list templates"""
        templates = super().get_template_list()
        # Calculator will be available automatically
        return templates


# Example: Add to a model admin
@admin.register(Sale)
class SaleAdmin(CalculatorAdminMixin, admin.ModelAdmin):
    """Sale admin with calculator widget"""
    list_display = ('id', 'customer', 'total', 'created_at')
    
    class Media:
        css = {
            'all': ('css/calculator.css',)
        }
        js = ('js/calculator.js',)


# Alternative: Add to all admin pages globally

# File: pos/admin_template_override.html
# Override django's admin base template to include calculator

ADMIN_BASE_TEMPLATE = """
{% extends "admin/base.html" %}
{% load static %}

{% block extrahead %}
    {{ block.super }}
    <link rel="stylesheet" href="{% static 'css/calculator.css' %}">
{% endblock %}

{% block footer %}
    {{ block.super }}
    <script src="{% static 'js/calculator.js' %}"></script>
{% endblock %}
"""


# File: pos/templates/admin/base.html
# To make this work globally:
# 1. Create pos/templates/admin/base.html
# 2. Add the above template content
# 3. This will automatically override Django's admin base


# Alternative approach using context processor

# File: pos/context_processors.py

from django.conf import settings

def calculator_widget(request):
    """Make calculator available in admin context"""
    return {
        'show_calculator': True,
        'calculator_enabled': getattr(settings, 'CALCULATOR_ENABLED', True),
    }


# File: settings.py
# Add to TEMPLATES > context_processors:

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'pos.context_processors.calculator_widget',  # Add this
            ],
        },
    },
]


# File: pos/templates/admin/change_list.html
# Override the change_list template to include calculator

CHANGE_LIST_TEMPLATE = """
{% extends "admin/change_list.html" %}
{% load static %}

{% block extrahead %}
    {{ block.super }}
    {% if show_calculator %}
        <link rel="stylesheet" href="{% static 'css/calculator.css' %}">
    {% endif %}
{% endblock %}

{% block submit_buttons %}
    {{ block.super }}
    {% if show_calculator %}
        <script src="{% static 'js/calculator.js' %}"></script>
    {% endif %}
{% endblock %}
"""


# ============================================================
# SIMPLEST APPROACH: Just add to your main admin templates
# ============================================================

# In your admin template (if you have one), add:

SIMPLE_ADDITION = """
{% load static %}

<!-- At the end of your admin base template or change_list template -->
<link rel="stylesheet" href="{% static 'css/calculator.css' %}">
<script src="{% static 'js/calculator.js' %}"></script>
"""


# Example: Custom POS Admin Class

class POSAdminSite(admin.AdminSite):
    """Custom admin site for POS with calculator"""
    
    site_header = "POS Administration"
    
    class Media:
        css = {
            'all': (
                'admin/css/base.css',
                'css/calculator.css',
            )
        }
        js = (
            'js/calculator.js',
        )
    
    def each_context(self, request):
        context = super().each_context(request)
        context['calculator_enabled'] = True
        return context


# Usage:
# pos_admin = POSAdminSite(name='pos_admin')
# pos_admin.register(Sale, SaleAdmin)
# pos_admin.register(Product, ProductAdmin)
# etc...


# ============================================================
# BEST PRACTICE: Conditional Display
# ============================================================

# Only show calculator for specific user groups

class CashierAdminMixin:
    """Mixin that adds calculator only for cashier users"""
    
    class Media:
        pass  # Start empty
    
    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        # Will be set dynamically in get_context
    
    def get_context(self, request):
        context = super().get_context(request)
        
        # Show calculator only for cashiers and managers
        allowed_groups = ['Cashier', 'Manager', 'Admin']
        user_groups = [g.name for g in request.user.groups.all()]
        
        if any(g in allowed_groups for g in user_groups):
            context['show_calculator'] = True
        
        return context


# Usage:
@admin.register(Sale)
class SaleAdminWithCalculator(CashierAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'customer', 'total')


print("""
To use the calculator in Django Admin:

1. Add static files to your admin class:
   
   class MyAdmin(admin.ModelAdmin):
       class Media:
           css = {'all': ('css/calculator.css',)}
           js = ('js/calculator.js',)

2. Or add to your admin base template:
   <link rel="stylesheet" href="{% static 'css/calculator.css' %}">
   <script src="{% static 'js/calculator.js' %}"></script>

3. Don't forget to run:
   python manage.py collectstatic

4. The calculator will appear on all pages where you include it!
""")
