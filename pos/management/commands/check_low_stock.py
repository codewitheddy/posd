"""
Management command to check low stock and send alerts
Run this daily or multiple times per day via cron job or task scheduler
"""
from django.core.management.base import BaseCommand
from django.db.models import Q, F
from pos.models import Business, Product
from pos.email_service import EmailService


class Command(BaseCommand):
    help = 'Check low stock products and send alerts to managers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business',
            type=str,
            help='Business slug to check (optional, checks all if not specified)',
        )

    def handle(self, *args, **options):
        business_slug = options.get('business')
        
        if business_slug:
            businesses = Business.objects.filter(slug=business_slug, is_active=True)
        else:
            businesses = Business.objects.filter(is_active=True)
        
        self.stdout.write('Checking low stock for all businesses...\n')
        
        total_alerts = 0
        
        for business in businesses:
            # Get products below threshold or out of stock
            low_stock_products = Product.objects.filter(
                business=business,
                stock_quantity__lte=F('low_stock_threshold')
            ).select_related('category').order_by('stock_quantity')
            
            if low_stock_products.exists():
                self.stdout.write(f'  {business.name}: {low_stock_products.count()} low stock product(s)')
                
                # Send alert
                success = EmailService.send_low_stock_alert(business, list(low_stock_products))
                
                if success:
                    self.stdout.write(self.style.SUCCESS(f'    ✅ Alert sent'))
                    total_alerts += 1
                else:
                    self.stdout.write(self.style.WARNING(f'    ⚠️  Failed to send alert (check email settings)'))
                
                # List products
                for product in low_stock_products[:5]:  # Show first 5
                    status = 'OUT OF STOCK' if product.stock_quantity == 0 else f'{product.stock_quantity} left'
                    self.stdout.write(f'      - {product.name}: {status}')
                
                if low_stock_products.count() > 5:
                    self.stdout.write(f'      ... and {low_stock_products.count() - 5} more')
            else:
                self.stdout.write(f'  {business.name}: All products in stock ✓')
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Low stock check complete. Sent {total_alerts} alert(s).'))
