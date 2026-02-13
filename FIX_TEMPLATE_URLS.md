# Template URL Fixes for Multi-Tenancy

## Problem
All Django template URL tags need to include the `slug` parameter for multi-tenant routing.

## Pattern to Fix

### Before (Broken):
```django
{% url 'view_name' %}
{% url 'view_name' object.pk %}
{% url 'view_name' arg1 arg2 %}
```

### After (Fixed):
```django
{% url 'view_name' slug=request.business.slug %}
{% url 'view_name' slug=request.business.slug pk=object.pk %}
{% url 'view_name' slug=request.business.slug arg1 arg2 %}
```

## URLs That DON'T Need slug Parameter
These are public/non-tenant URLs:
- `login`
- `logout`
- `landing`
- `register_business`
- `business_list`
- `business_setup`
- `admin:*` (Django admin URLs)
- `static` (static files)

## Quick Fix Script

Save this as `fix_template_urls.py` in your project root:

```python
import os
import re
from pathlib import Path

# URLs that don't need slug parameter (public URLs)
EXCLUDE_URLS = {
    'login', 'logout', 'landing', 'register_business', 
    'business_list', 'business_setup', 'switch_business'
}

def fix_url_tag(match):
    """Fix a single URL tag"""
    full_match = match.group(0)
    url_name = match.group(1)
    
    # Skip if it's an excluded URL
    if url_name in EXCLUDE_URLS:
        return full_match
    
    # Skip if it already has slug parameter
    if 'slug=' in full_match:
        return full_match
    
    # Skip admin URLs
    if url_name.startswith('admin:'):
        return full_match
    
    # Extract the URL name and any existing parameters
    if ' ' in url_name:
        # Has parameters
        parts = full_match.split(None, 2)  # Split into {% url 'name' params %}
        if len(parts) >= 3:
            tag_start = parts[0] + ' ' + parts[1]  # {% url 'name'
            params = parts[2].rstrip('%}').strip()
            return f"{tag_start} slug=request.business.slug {params} %}}"
    
    # No parameters, just add slug
    return full_match.replace(f"'{url_name}'", f"'{url_name}' slug=request.business.slug")

def fix_template_file(filepath):
    """Fix all URL tags in a template file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match {% url 'name' ... %}
    pattern = r"{%\s*url\s+['\"]([^'\"]+)['\"][^}]*%}"
    
    original_content = content
    content = re.sub(pattern, fix_url_tag, content)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    """Fix all template files"""
    templates_dir = Path('posd/pos/templates/pos')
    
    if not templates_dir.exists():
        print(f"Templates directory not found: {templates_dir}")
        return
    
    fixed_count = 0
    for template_file in templates_dir.glob('*.html'):
        # Skip multi-tenant specific templates
        if template_file.name in ['landing.html', 'register_business.html', 
                                   'business_list.html', 'business_setup.html']:
            continue
        
        if fix_template_file(template_file):
            print(f"✓ Fixed: {template_file.name}")
            fixed_count += 1
        else:
            print(f"  Skipped: {template_file.name} (no changes needed)")
    
    print(f"\n✅ Fixed {fixed_count} template files")

if __name__ == '__main__':
    main()
```

## Manual Fix Checklist

For templates that need manual review:

### 1. Dashboard & Navigation
- [x] dashboard.html - Already fixed
- [ ] base.html - Check navigation links

### 2. Products
- [x] product_list.html - Fixed
- [x] pos_screen.html - Fixed
- [ ] product_form.html
- [ ] product_confirm_delete.html

### 3. Sales & Reports
- [ ] sales_report.html
- [ ] z_report.html
- [ ] invoice.html
- [ ] thermal_receipt.html

### 4. Stock Management
- [ ] stock_list.html
- [ ] stock_adjust.html
- [ ] stock_history.html
- [ ] low_stock_alert.html
- [ ] expiry_alert.html
- [ ] update_expiry.html
- [ ] writeoff_report.html

### 5. Suppliers & Purchases
- [ ] supplier_list.html
- [ ] supplier_form.html
- [ ] supplier_confirm_delete.html
- [ ] supplier_statement.html
- [ ] supplier_payments.html
- [ ] purchase_list.html
- [ ] purchase_form.html
- [ ] purchase_detail.html

### 6. Customers
- [ ] customer_list.html
- [ ] customer_form.html
- [ ] customer_detail.html
- [ ] customer_confirm_delete.html

### 7. Users & Settings
- [ ] user_list.html
- [ ] user_form.html
- [ ] user_confirm_delete.html
- [ ] user_profile.html
- [ ] business_settings.html

### 8. Payments
- [ ] payment_form.html
- [ ] payment_detail.html
- [ ] payment_transactions_report.html

## Common URL Patterns to Fix

### Simple URLs (no parameters)
```django
<!-- Before -->
<a href="{% url 'product_list' %}">Products</a>

<!-- After -->
<a href="{% url 'product_list' slug=request.business.slug %}">Products</a>
```

### URLs with PK parameter
```django
<!-- Before -->
<a href="{% url 'product_edit' product.pk %}">Edit</a>

<!-- After -->
<a href="{% url 'product_edit' slug=request.business.slug pk=product.pk %}">Edit</a>
```

### URLs with multiple parameters
```django
<!-- Before -->
<a href="{% url 'supplier_statement' supplier.pk %}">Statement</a>

<!-- After -->
<a href="{% url 'supplier_statement' slug=request.business.slug pk=supplier.pk %}">Statement</a>
```

### Form actions
```django
<!-- Before -->
<form method="POST" action="{% url 'product_create' %}">

<!-- After -->
<form method="POST" action="{% url 'product_create' slug=request.business.slug %}">
```

## Testing After Fixes

1. Navigate through all pages in the application
2. Click all links and buttons
3. Submit all forms
4. Check that you stay within your business context
5. Verify no NoReverseMatch errors

## Automated Testing Command

```bash
# Run Django's template check
python manage.py check --deploy

# Test URL resolution
python manage.py shell
>>> from django.urls import reverse
>>> reverse('product_list', kwargs={'slug': 'test-business'})
```

## Notes

- The `slug` parameter should ALWAYS come first in the URL tag
- Use named parameters for clarity: `slug=request.business.slug pk=object.pk`
- Test each page after fixing to ensure links work
- Some templates may have JavaScript that generates URLs - those need separate fixes
