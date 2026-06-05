"""
Calculator Integration Example
This shows how to integrate the calculator widget into your POS templates.
"""

# Example 1: Add to base template (pos/templates/pos/base.html)
# =====================================================

EXAMPLE_BASE_TEMPLATE = """
{% extends "admin/base_site.html" %}
{% load static %}
{% load calculator_tags %}

{% block extrahead %}
    {{ block.super }}
    <!-- Calculator CSS -->
    <link rel="stylesheet" href="{% static 'css/calculator.css' %}">
{% endblock %}

{% block content %}
    <div id="main-content">
        <!-- Your main content here -->
        {{ block.super }}
    </div>
    
    <!-- Calculator Widget (appears floating in bottom-right) -->
    {% calculator_widget %}
{% endblock %}

{% block extrajs %}
    {{ block.super }}
    <!-- Calculator JS -->
    <script src="{% static 'js/calculator.js' %}"></script>
{% endblock %}
"""

# Example 2: Add to POS Dashboard (pos/templates/pos/dashboard.html)
# ==================================================================

EXAMPLE_POS_DASHBOARD = """
{% extends "pos/base.html" %}
{% load static %}

{% block title %}POS Dashboard{% endblock %}

{% block content %}
    <div class="dashboard-container">
        <h1>POS Dashboard</h1>
        
        <!-- Dashboard content -->
        <div class="dashboard-grid">
            <!-- Sales summary, stats, etc. -->
        </div>
    </div>
    
    <!-- Calculator automatically available via base template -->
{% endblock %}
"""

# Example 3: Add to Sales/Checkout page (pos/templates/pos/sales/new_sale.html)
# =============================================================================

EXAMPLE_SALES_PAGE = """
{% extends "pos/base.html" %}
{% load static %}

{% block title %}New Sale{% endblock %}

{% block content %}
    <div class="sales-container">
        <form method="post" id="sale-form">
            {% csrf_token %}
            
            <div class="sale-items">
                <!-- Sale items form -->
            </div>
            
            <div class="sale-totals">
                <label>Subtotal: <span id="subtotal">0.00</span></label>
                <label>Tax: <span id="tax">0.00</span></label>
                <label>Total: <span id="total">0.00</span></label>
                <label>Amount Paid: <input type="number" id="amount-paid" step="0.01"></label>
            </div>
            
            <button type="submit" class="btn-primary">Complete Sale</button>
        </form>
    </div>
    
    <!-- Calculator widget automatically available -->
    <!-- Cashier can use it to calculate discounts, verify totals, etc. -->
{% endblock %}
"""

# Example 4: How to use calculator from JavaScript
# ================================================

EXAMPLE_JS_USAGE = """
// After calculator is initialized, you can access it globally
if (window.calculator) {
    // Get current display value
    const value = window.calculator.display;
    console.log('Current calculator value:', value);
    
    // Access memory
    console.log('Memory value:', window.calculator.memory);
    
    // Access history
    console.log('Calculation history:', window.calculator.history);
    
    // Programmatically set display (for integrations)
    window.calculator.display = '100.50';
    window.calculator.updateDisplay();
    
    // Listen for changes (extend AdvancedCalculator if needed)
    // You could add callbacks to handle results
}
"""

# Example 5: Django view integration
# ===================================

EXAMPLE_DJANGO_VIEW = """
from django.shortcuts import render
from django.views.generic import TemplateView

class POSBaseView(TemplateView):
    '''Base view for all POS pages - calculator available on all pages'''
    template_name = 'pos/base.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['calculator_enabled'] = True
        return context

class SalesView(POSBaseView):
    '''Sales page - calculator available for cashiers'''
    template_name = 'pos/sales/new_sale.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'New Sale'
        return context

# In urls.py
from django.urls import path
from .views import SalesView, POSBaseView

urlpatterns = [
    path('pos/sales/new/', SalesView.as_view(), name='new_sale'),
    path('pos/', POSBaseView.as_view(), name='pos_dashboard'),
]
"""

# Example 6: Extending calculator with callbacks
# ===============================================

EXAMPLE_EXTENSION = """
<!-- In your template or JavaScript file -->

<script>
// Wait for calculator to be initialized
document.addEventListener('DOMContentLoaded', () => {
    if (window.calculator) {
        // Store original updateDisplay
        const originalUpdateDisplay = window.calculator.updateDisplay.bind(window.calculator);
        
        // Override to add custom behavior
        window.calculator.updateDisplay = function() {
            originalUpdateDisplay();
            
            // Your custom code here
            // E.g., sync with a sales form field
            const display = document.getElementById('calc-display');
            const amountField = document.getElementById('amount-paid');
            
            if (amountField && display) {
                // You could auto-populate forms if needed
                console.log('Calculator updated to:', display.value);
            }
        };
        
        // Store original addToHistory
        const originalAddToHistory = window.calculator.addToHistory.bind(window.calculator);
        window.calculator.addToHistory = function(entry) {
            originalAddToHistory(entry);
            
            // Send calculation to server for audit logging
            fetch('/api/calculator/log/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({calculation: entry})
            }).catch(e => console.log('Note: Could not log to server'));
        };
    }
});
</script>
"""

# Example 7: Settings configuration
# ==================================

EXAMPLE_SETTINGS = """
# In settings.py or settings_production.py

# Calculator Widget Settings
CALCULATOR_WIDGET = {
    'ENABLED': True,
    'POSITION': {
        'bottom': 20,  # pixels from bottom
        'right': 20,   # pixels from right
    },
    'MAX_HISTORY': 50,
    'ENABLE_CONVERSIONS': True,
    'ENABLE_SCIENTIFIC': True,
}

# Template configuration
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'pos/templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                # ... existing context processors ...
                'pos.context_processors.calculator_settings',  # Custom context processor
            ],
        },
    },
]
"""

# Example 8: Context processor for dynamic settings
# ==================================================

EXAMPLE_CONTEXT_PROCESSOR = """
# In pos/context_processors.py

from django.conf import settings

def calculator_settings(request):
    '''Make calculator settings available in all templates'''
    return {
        'calculator_enabled': getattr(settings, 'CALCULATOR_WIDGET', {}).get('ENABLED', True),
        'calculator_position': getattr(settings, 'CALCULATOR_WIDGET', {}).get('POSITION', {}),
    }
"""

# Example 9: URL patterns for future API endpoints
# ==================================================

EXAMPLE_API_URLS = """
# In pos/api_urls.py or new calculator_api.py

from django.urls import path
from . import views

urlpatterns = [
    # Calculator history endpoints (if you want server-side logging)
    path('api/calculator/history/', views.CalculatorHistoryAPI.as_view(), name='calculator_history'),
    path('api/calculator/clear-history/', views.ClearCalculatorHistory.as_view(), name='clear_calculator_history'),
]
"""

# INTEGRATION CHECKLIST
# ======================

CHECKLIST = """
✓ Integration Checklist:

1. Static Files
   [ ] calculator.js exists at pos/static/js/calculator.js
   [ ] calculator.css exists at pos/static/css/calculator.css
   [ ] collectstatic has been run: python manage.py collectstatic

2. Templates
   [ ] Template tag created: pos/templatetags/calculator_tags.py
   [ ] Widget template exists: pos/templates/calculator_widget.html
   [ ] Base template loads the widget: {% load calculator_tags %}
   [ ] {% calculator_widget %} tag used in base template

3. Testing
   [ ] Visit POS page and verify calculator appears bottom-right
   [ ] Test basic calculations (1 + 1 = 2)
   [ ] Test keyboard input
   [ ] Test history functionality
   [ ] Test memory functions
   [ ] Test advanced functions toggle
   [ ] Test mobile responsiveness
   [ ] Check browser console for JavaScript errors

4. Optional
   [ ] Configure custom position in calculator.css
   [ ] Configure custom colors/theme
   [ ] Add API logging endpoint for history
   [ ] Add custom extension logic

5. Documentation
   [ ] Show docs/CALCULATOR_WIDGET.md to team
   [ ] Train cashiers on keyboard shortcuts
   [ ] Document any customizations made
"""

print("Calculator Integration Guide")
print("=" * 50)
print(CHECKLIST)
