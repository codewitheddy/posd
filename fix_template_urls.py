#!/usr/bin/env python3
"""
Script to automatically fix Django template URL tags for multi-tenancy.
Adds slug=request.business.slug parameter to all tenant-scoped URLs.
"""

import os
import re
from pathlib import Path

# URLs that don't need slug parameter (public URLs)
EXCLUDE_URLS = {
    'login', 'logout', 'landing', 'register_business', 
    'business_list', 'business_setup', 'switch_business',
    'static', 'media'
}

def should_fix_url(url_name, full_match):
    """Determine if a URL tag needs fixing"""
    # Skip if it's an excluded URL
    if url_name in EXCLUDE_URLS:
        return False
    
    # Skip if it already has slug parameter
    if 'slug=' in full_match:
        return False
    
    # Skip admin URLs
    if url_name.startswith('admin:'):
        return False
    
    return True

def fix_url_tag(match):
    """Fix a single URL tag by adding slug parameter"""
    full_match = match.group(0)
    url_name = match.group(1)
    
    if not should_fix_url(url_name, full_match):
        return full_match
    
    # Extract components
    # Pattern: {% url 'name' param1 param2 %}
    parts = full_match.split()
    
    if len(parts) == 3:
        # Simple case: {% url 'name' %}
        return f"{{% url '{url_name}' slug=request.business.slug %}}"
    else:
        # Has parameters: {% url 'name' param1 param2 %}
        # Insert slug after the URL name
        tag_parts = full_match[2:-2].strip().split(None, 2)  # Remove {% %} and split
        if len(tag_parts) >= 2:
            url_part = tag_parts[0] + ' ' + tag_parts[1]  # 'url' and 'name'
            rest = tag_parts[2] if len(tag_parts) > 2 else ''
            return f"{{% {url_part} slug=request.business.slug {rest} %}}"
    
    return full_match

def fix_template_file(filepath):
    """Fix all URL tags in a template file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  ✗ Error reading {filepath.name}: {e}")
        return False
    
    # Pattern to match {% url 'name' ... %}
    # Matches both single and double quotes
    pattern = r"{%\s*url\s+['\"]([^'\"]+)['\"][^}]*%}"
    
    original_content = content
    content = re.sub(pattern, fix_url_tag, content)
    
    if content != original_content:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"  ✗ Error writing {filepath.name}: {e}")
            return False
    
    return False

def main():
    """Fix all template files in the POS templates directory"""
    templates_dir = Path('posd/pos/templates/pos')
    
    if not templates_dir.exists():
        print(f"❌ Templates directory not found: {templates_dir}")
        print("   Make sure you're running this script from the project root.")
        return
    
    # Skip these templates (they're multi-tenant specific or already fixed)
    skip_templates = {
        'landing.html', 
        'register_business.html', 
        'business_list.html', 
        'business_setup.html',
        'business_members.html',
        'business_settings_tenant.html',
        'dashboard.html',  # Already fixed
        'pos_screen.html',  # Already fixed
        'product_list.html',  # Already fixed
        'analytics_modal.html',  # Already fixed
    }
    
    print("🔧 Fixing template URL tags for multi-tenancy...\n")
    
    fixed_count = 0
    skipped_count = 0
    unchanged_count = 0
    
    template_files = sorted(templates_dir.glob('*.html'))
    
    for template_file in template_files:
        if template_file.name in skip_templates:
            print(f"  ⊘ Skipped: {template_file.name} (excluded)")
            skipped_count += 1
            continue
        
        if fix_template_file(template_file):
            print(f"  ✓ Fixed: {template_file.name}")
            fixed_count += 1
        else:
            print(f"  - Unchanged: {template_file.name}")
            unchanged_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Summary:")
    print(f"   Fixed: {fixed_count} files")
    print(f"   Unchanged: {unchanged_count} files")
    print(f"   Skipped: {skipped_count} files")
    print(f"   Total processed: {len(template_files)} files")
    print(f"{'='*60}")
    
    if fixed_count > 0:
        print("\n⚠️  Important: Review the changes and test your application!")
        print("   Some URLs may need manual adjustment if they have complex parameters.")

if __name__ == '__main__':
    main()
