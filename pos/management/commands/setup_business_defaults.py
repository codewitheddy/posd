"""
Management command to set up default data for a business
Creates default payment method (CASH), unit (Pieces), and category (GENERAL)
"""
from django.core.management.base import BaseCommand
from pos.models import Business, PaymentMethod, UnitOfMeasurement, Category


class Command(BaseCommand):
    help = 'Set up default payment method, unit, and category for a business'

    def add_arguments(self, parser):
        parser.add_argument('business_id', type=int, help='Business ID')

    def handle(self, *args, **options):
        business_id = options['business_id']
        
        try:
            business = Business.objects.get(id=business_id)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business with ID {business_id} does not exist'))
            return
        
        # Create default payment method: CASH
        cash_method, created = PaymentMethod.objects.get_or_create(
            business=business,
            name='CASH',
            defaults={
                'is_active': True,
                'requires_reference': False,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Created default payment method: CASH'))
        else:
            self.stdout.write(self.style.WARNING(f'Payment method CASH already exists'))
        
        # Create default unit: Pieces
        pieces_unit, created = UnitOfMeasurement.objects.get_or_create(
            business=business,
            name='Pieces',
            defaults={
                'abbreviation': 'pcs',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Created default unit: Pieces'))
        else:
            self.stdout.write(self.style.WARNING(f'Unit Pieces already exists'))
        
        # Create default category: GENERAL
        general_category, created = Category.objects.get_or_create(
            business=business,
            name='GENERAL',
            defaults={
                'description': 'General products',
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'✓ Created default category: GENERAL'))
        else:
            self.stdout.write(self.style.WARNING(f'Category GENERAL already exists'))
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ Default setup complete for {business.name}'))
