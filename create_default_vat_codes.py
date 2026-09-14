#!/usr/bin/env python
"""
Create default VAT codes for the POS system
Run: python manage.py shell < create_default_vat_codes.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from pos.models import VATCode, Business
from decimal import Decimal

def create_default_vat_codes():
    """Create default VAT codes for all businesses"""
    
    businesses = Business.objects.all()
    
    if not businesses.exists():
        print("❌ No businesses found!")
        return
    
    for business in businesses:
        print(f"\n📦 Creating VAT codes for: {business.name}")
        
        # Standard Rate
        vat_std, created = VATCode.objects.get_or_create(
            business=business,
            code='VAT-STD',
            defaults={
                'name': 'Standard Rated (16%)',
                'vat_rate': Decimal('16.00'),
                'description': 'Standard VAT rate for regular products and services',
                'is_active': True
            }
        )
        status = '✓ Created' if created else '✓ Already exists'
        print(f"  {status}: {vat_std.code} - {vat_std.name}")
        
        # Zero Rated
        vat_zero, created = VATCode.objects.get_or_create(
            business=business,
            code='VAT-ZERO',
            defaults={
                'name': 'Zero Rated (0%)',
                'vat_rate': Decimal('0.00'),
                'description': 'Zero-rated products like unprocessed food items',
                'hs_code_chapter': '04',
                'is_active': True
            }
        )
        status = '✓ Created' if created else '✓ Already exists'
        print(f"  {status}: {vat_zero.code} - {vat_zero.name}")
        
        # Exempt
        vat_exempt, created = VATCode.objects.get_or_create(
            business=business,
            code='VAT-EXEMPT',
            defaults={
                'name': 'Exempt (0%)',
                'vat_rate': Decimal('0.00'),
                'description': 'VAT exempt products and services',
                'is_active': True
            }
        )
        status = '✓ Created' if created else '✓ Already exists'
        print(f"  {status}: {vat_exempt.code} - {vat_exempt.name}")
        
        # Excisable
        vat_excise, created = VATCode.objects.get_or_create(
            business=business,
            code='VAT-EXCISE',
            defaults={
                'name': 'Excisable Products (36%)',
                'vat_rate': Decimal('16.00'),
                'excise_rate': Decimal('20.00'),
                'is_excisable': True,
                'description': 'Products subject to VAT and excise duty (alcohol, tobacco)',
                'hs_code_chapter': '22',
                'is_active': True
            }
        )
        status = '✓ Created' if created else '✓ Already exists'
        print(f"  {status}: {vat_excise.code} - {vat_excise.name}")
        
        total = VATCode.objects.filter(business=business).count()
        print(f"  📊 Total VAT codes: {total}")
    
    print("\n✅ VAT code setup complete!")

if __name__ == '__main__':
    create_default_vat_codes()
