"""
Management command to check purchase amount details
"""
from django.core.management.base import BaseCommand
from pos.models import Purchase, PurchaseItem
from decimal import Decimal


class Command(BaseCommand):
    help = 'Check purchase amount calculation'

    def add_arguments(self, parser):
        parser.add_argument('purchase_number', type=str, help='Purchase number (e.g., PO-20260216-0001)')
        parser.add_argument('--business', type=str, help='Business slug')

    def handle(self, *args, **options):
        purchase_number = options['purchase_number']
        business_slug = options.get('business')

        try:
            if business_slug:
                from pos.models import Business
                business = Business.objects.get(slug=business_slug)
                purchase = Purchase.objects.get(purchase_number=purchase_number, business=business)
            else:
                purchase = Purchase.objects.get(purchase_number=purchase_number)

            self.stdout.write(f"\n{'='*70}")
            self.stdout.write(f"Purchase Amount Check: {purchase.purchase_number}")
            self.stdout.write(f"{'='*70}\n")

            # Purchase details
            self.stdout.write(f"📦 PURCHASE DETAILS:")
            self.stdout.write(f"{'─'*70}")
            self.stdout.write(f"  Purchase Number: {purchase.purchase_number}")
            self.stdout.write(f"  Supplier: {purchase.supplier.name}")
            self.stdout.write(f"  Date: {purchase.date}")
            self.stdout.write(f"  Status: {purchase.status}")
            self.stdout.write(f"  Subtotal: KES {purchase.subtotal:,.2f}")
            self.stdout.write(f"  Tax Amount: KES {purchase.tax_amount:,.2f}")
            self.stdout.write(f"  Total Amount: KES {purchase.total_amount:,.2f}")
            self.stdout.write(f"")

            # Items
            items = purchase.items.all()
            self.stdout.write(f"📋 PURCHASE ITEMS ({items.count()} items):")
            self.stdout.write(f"{'─'*70}")
            
            calculated_total = Decimal('0.00')
            for i, item in enumerate(items, 1):
                self.stdout.write(f"\n  Item {i}: {item.product.name}")
                self.stdout.write(f"    Quantity Ordered: {item.quantity}")
                self.stdout.write(f"    Unit Cost: KES {item.unit_cost:,.2f}")
                self.stdout.write(f"    Total Cost: KES {item.total_cost:,.2f}")
                self.stdout.write(f"    Quantity Received: {item.quantity_received}")
                self.stdout.write(f"    Quantity Damaged: {item.quantity_damaged}")
                calculated_total += item.total_cost

            self.stdout.write(f"\n{'─'*70}")
            self.stdout.write(f"  Calculated Total (sum of items): KES {calculated_total:,.2f}")
            self.stdout.write(f"  Stored Total Amount: KES {purchase.total_amount:,.2f}")
            
            if calculated_total != purchase.total_amount:
                difference = calculated_total - purchase.total_amount
                self.stdout.write(self.style.ERROR(f"  ⚠️  MISMATCH! Difference: KES {difference:,.2f}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Amounts match!"))

            # Check if total_amount field can store the value
            self.stdout.write(f"\n📊 FIELD CAPACITY CHECK:")
            self.stdout.write(f"{'─'*70}")
            self.stdout.write(f"  Field: total_amount")
            self.stdout.write(f"  Type: DecimalField(max_digits=10, decimal_places=2)")
            self.stdout.write(f"  Max Value: 99,999,999.99")
            self.stdout.write(f"  Current Value: {purchase.total_amount:,.2f}")
            
            if purchase.total_amount > Decimal('99999999.99'):
                self.stdout.write(self.style.ERROR(f"  ⚠️  Value exceeds field capacity!"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Value within field capacity"))

            # Recommendations
            self.stdout.write(f"\n💡 RECOMMENDATIONS:")
            self.stdout.write(f"{'─'*70}")
            
            if calculated_total != purchase.total_amount:
                self.stdout.write(f"  1. Recalculate purchase total:")
                self.stdout.write(f"     python manage.py shell")
                self.stdout.write(f"     >>> from pos.models import Purchase")
                self.stdout.write(f"     >>> p = Purchase.objects.get(purchase_number='{purchase.purchase_number}')")
                self.stdout.write(f"     >>> p.total_amount = sum(item.total_cost for item in p.items.all())")
                self.stdout.write(f"     >>> p.save()")
                self.stdout.write(f"")
                self.stdout.write(f"  2. Or use the fix command:")
                self.stdout.write(f"     python manage.py fix_purchase_amounts {purchase.purchase_number}")

            self.stdout.write(f"\n{'='*70}")
            self.stdout.write(self.style.SUCCESS('✓ Check complete'))

        except Purchase.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'✗ Purchase {purchase_number} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error: {str(e)}'))
            import traceback
            traceback.print_exc()
