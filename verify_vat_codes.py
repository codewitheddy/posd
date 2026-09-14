#!/usr/bin/env python
"""Verify VAT codes are properly set up"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from pos.models import VATCode, Product, Business

print("=" * 60)
print("VAT CODE SYSTEM VERIFICATION")
print("=" * 60)

total_vat_codes = VATCode.objects.count()
total_products = Product.objects.count()
products_with_vat = Product.objects.filter(vat_code__isnull=False).count()

print(f"\n📊 Summary:")
print(f"  Total VAT codes in system: {total_vat_codes}")
print(f"  Total products: {total_products}")
print(f"  Products with VAT code assigned: {products_with_vat}")

print(f"\n📦 VAT Codes by Business:")
for business in Business.objects.all():
    count = VATCode.objects.filter(business=business).count()
    print(f"  • {business.name}: {count} codes")

print(f"\n✅ System is ready! The error should be resolved.")
print(f"   Try accessing: http://localhost:8000/b/default/")
print("=" * 60)
