"""
Business-specific data backup command
"""
from django.core.management.base import BaseCommand
from django.core import serializers
from pos.models import Business
import json
import os
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backup specific business data to JSON file'

    def add_arguments(self, parser):
        parser.add_argument('business_id', type=int, help='Business ID to backup')
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (optional)',
        )

    def handle(self, *args, **options):
        business_id = options['business_id']

        try:
            business = Business.objects.get(id=business_id)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Business {business_id} not found'))
            return

        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        
        # Determine output file
        if options['output']:
            backup_file = options['output']
        else:
            backup_dir = os.path.join('backups', 'businesses', business.slug)
            os.makedirs(backup_dir, exist_ok=True)
            backup_file = os.path.join(
                backup_dir,
                f'{business.slug}_backup_{timestamp}.json'
            )

        self.stdout.write(f'📦 Backing up business: {business.name}')

        # Collect all related data
        backup_data = {
            'metadata': {
                'business_name': business.name,
                'business_slug': business.slug,
                'backup_date': timestamp,
                'version': '1.0'
            },
            'business': self.serialize_single(business),
            'products': self.serialize_queryset(business.products.all()),
            'categories': self.serialize_queryset(business.categories.all()),
            'customers': self.serialize_queryset(business.customers.all()),
            'suppliers': self.serialize_queryset(business.suppliers.all()),
            'sales': self.serialize_queryset(business.sales.all()[:1000]),  # Last 1000 sales
            'purchases': self.serialize_queryset(business.purchases.all()[:500]),  # Last 500 purchases
            'payment_methods': self.serialize_queryset(business.payment_methods.all()),
        }

        # Write to file
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)

        file_size = os.path.getsize(backup_file) / 1024 / 1024  # MB
        
        self.stdout.write(self.style.SUCCESS(
            f'✅ Backup completed: {backup_file} ({file_size:.2f} MB)'
        ))
        
        # Print summary
        self.stdout.write('\n📊 Backup Summary:')
        self.stdout.write(f'  Products: {business.products.count()}')
        self.stdout.write(f'  Categories: {business.categories.count()}')
        self.stdout.write(f'  Customers: {business.customers.count()}')
        self.stdout.write(f'  Suppliers: {business.suppliers.count()}')
        self.stdout.write(f'  Sales: {min(business.sales.count(), 1000)}')
        self.stdout.write(f'  Purchases: {min(business.purchases.count(), 500)}')

        return backup_file

    def serialize_single(self, obj):
        """Serialize single object"""
        return json.loads(serializers.serialize('json', [obj]))[0]

    def serialize_queryset(self, queryset):
        """Serialize queryset"""
        return json.loads(serializers.serialize('json', queryset))
