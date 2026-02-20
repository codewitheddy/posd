"""
Management command to set test expiry dates on products
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pos.models import Product, Business


class Command(BaseCommand):
    help = 'Set test expiry dates on products for testing expiry alerts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business',
            type=str,
            default='default',
            help='Business slug (default: default)',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=3,
            help='Number of products to set expiry dates on (default: 3)',
        )

    def handle(self, *args, **options):
        business_slug = options['business']
        count = options['count']
        
        try:
            business = Business.objects.get(slug=business_slug)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business "{business_slug}" not found'))
            return
        
        # Get products with stock
        products = Product.objects.filter(
            business=business,
            stock_quantity__gt=0,
            expiry_date__isnull=True
        )[:count]
        
        if not products.exists():
            self.stdout.write(self.style.WARNING('No products with stock found (or all already have expiry dates)'))
            return
        
        today = timezone.now().date()
        updated_count = 0
        
        for i, product in enumerate(products):
            # Set different expiry dates for testing
            if i == 0:
                # Already expired (5 days ago)
                product.expiry_date = today - timedelta(days=5)
                status = 'EXPIRED 5 days ago'
            elif i == 1:
                # Expiring in 3 days
                product.expiry_date = today + timedelta(days=3)
                status = 'Expires in 3 days'
            else:
                # Expiring in 15 days (good)
                product.expiry_date = today + timedelta(days=15)
                status = 'Expires in 15 days'
            
            product.expiry_alert_days = 7
            product.save(update_fields=['expiry_date', 'expiry_alert_days'])
            updated_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'✓ {product.name}: {product.expiry_date} ({status})')
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Set expiry dates on {updated_count} product(s)')
        )
        self.stdout.write('Now visit the Expiry Alerts page to see the results')
