"""
Management command to fix purchase amounts by recalculating from items
"""
from django.core.management.base import BaseCommand
from pos.models import Purchase
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fix purchase amounts by recalculating from items'

    def add_arguments(self, parser):
        parser.add_argument('--purchase', type=str, help='Specific purchase number to fix')
        parser.add_argument('--business', type=str, help='Business slug')
        parser.add_argument('--all', action='store_true', help='Fix all purchases')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')

    def handle(self, *args, **options):
        purchase_number = options.get('purchase')
        business_slug = options.get('business')
        fix_all = options.get('all')
        dry_run = options.get('dry_run')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made\n'))

        try:
            # Get purchases to fix
            if purchase_number:
                if business_slug:
                    from pos.models import Business
                    business = Business.objects.get(slug=business_slug)
                    purchases = Purchase.objects.filter(purchase_number=purchase_number, business=business)
                else:
                    purchases = Purchase.objects.filter(purchase_number=purchase_number)
            elif fix_all:
                if business_slug:
                    from pos.models import Business
                    business = Business.objects.get(slug=business_slug)
                    purchases = Purchase.objects.filter(business=business)
                else:
                    purchases = Purchase.objects.all()
            else:
                self.stdout.write(self.style.ERROR('Please specify --purchase or --all'))
                return

            self.stdout.write(f"Found {purchases.count()} purchase(s) to check\n")

            fixed_count = 0
            for purchase in purchases:
                # Calculate correct total from items
                calculated_total = sum(item.total_cost for item in purchase.items.all())
                
                if calculated_total != purchase.total_amount:
                    self.stdout.write(f"\n{purchase.purchase_number} - {purchase.supplier.name}")
                    self.stdout.write(f"  Current total: KES {purchase.total_amount:,.2f}")
                    self.stdout.write(f"  Calculated total: KES {calculated_total:,.2f}")
                    self.stdout.write(f"  Difference: KES {(calculated_total - purchase.total_amount):,.2f}")
                    
                    if not dry_run:
                        purchase.total_amount = calculated_total
                        purchase.subtotal = calculated_total  # Assuming no tax for now
                        purchase.save()
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Fixed!"))
                    else:
                        self.stdout.write(self.style.WARNING(f"  Would fix (dry run)"))
                    
                    fixed_count += 1

            self.stdout.write(f"\n{'='*70}")
            if dry_run:
                self.stdout.write(self.style.WARNING(f'Would fix {fixed_count} purchase(s) (dry run)'))
            else:
                self.stdout.write(self.style.SUCCESS(f'✓ Fixed {fixed_count} purchase(s)'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error: {str(e)}'))
            import traceback
            traceback.print_exc()
