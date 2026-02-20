"""
Management command to diagnose expiry alert issues
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pos.models import Product, Business


class Command(BaseCommand):
    help = 'Check expiry alert configuration and products'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business',
            type=str,
            help='Business slug to check (default: all businesses)',
        )

    def handle(self, *args, **options):
        business_slug = options.get('business')
        
        if business_slug:
            businesses = Business.objects.filter(slug=business_slug)
            if not businesses.exists():
                self.stdout.write(self.style.ERROR(f'Business "{business_slug}" not found'))
                return
        else:
            businesses = Business.objects.all()
        
        today = timezone.now().date()
        
        for business in businesses:
            self.stdout.write(self.style.SUCCESS(f'\n=== Business: {business.name} ({business.slug}) ==='))
            
            # Check business settings
            if hasattr(business, 'settings'):
                settings = business.settings
                self.stdout.write(f'Default Expiry Alert Days: {settings.default_expiry_alert_days}')
                self.stdout.write(f'Expiry Alerts Enabled: {settings.enable_expiry_alerts}')
            else:
                self.stdout.write(self.style.WARNING('No business settings found'))
            
            # Get all products with expiry dates
            products_with_expiry = Product.objects.filter(
                business=business,
                expiry_date__isnull=False
            ).order_by('expiry_date')
            
            self.stdout.write(f'\nTotal products with expiry dates: {products_with_expiry.count()}')
            
            if products_with_expiry.count() == 0:
                self.stdout.write(self.style.WARNING('No products have expiry dates set'))
                continue
            
            # Check products with stock
            products_with_stock = products_with_expiry.filter(stock_quantity__gt=0)
            self.stdout.write(f'Products with expiry dates AND stock: {products_with_stock.count()}')
            
            # Check expired products
            expired = products_with_expiry.filter(
                expiry_date__lt=today,
                stock_quantity__gt=0
            )
            self.stdout.write(f'\n{self.style.ERROR("EXPIRED")} products (with stock): {expired.count()}')
            for product in expired[:5]:
                days_overdue = (today - product.expiry_date).days
                self.stdout.write(f'  - {product.name}: Expired {days_overdue} days ago (Stock: {product.stock_quantity}, Alert Days: {product.expiry_alert_days})')
            
            # Check expiring soon products
            self.stdout.write(f'\n{self.style.WARNING("EXPIRING SOON")} products:')
            expiring_count = 0
            for product in products_with_stock.filter(expiry_date__gte=today):
                if product.is_expiring_soon():
                    expiring_count += 1
                    days_until = (product.expiry_date - today).days
                    self.stdout.write(f'  - {product.name}: Expires in {days_until} days (Stock: {product.stock_quantity}, Alert Days: {product.expiry_alert_days})')
                    if expiring_count >= 5:
                        break
            
            if expiring_count == 0:
                self.stdout.write('  None found')
            else:
                self.stdout.write(f'\nTotal expiring soon: {expiring_count}')
            
            # Show all products with expiry dates for debugging
            self.stdout.write(f'\n{self.style.HTTP_INFO("ALL PRODUCTS")} with expiry dates:')
            for product in products_with_expiry[:10]:
                days_until = (product.expiry_date - today).days
                status = 'EXPIRED' if days_until < 0 else f'{days_until} days'
                self.stdout.write(
                    f'  - {product.name}: {product.expiry_date} ({status}) | '
                    f'Stock: {product.stock_quantity} | Alert Days: {product.expiry_alert_days}'
                )
            
            if products_with_expiry.count() > 10:
                self.stdout.write(f'  ... and {products_with_expiry.count() - 10} more')
        
        self.stdout.write(self.style.SUCCESS('\n✓ Diagnostic complete'))
