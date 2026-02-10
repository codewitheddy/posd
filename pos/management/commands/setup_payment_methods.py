from django.core.management.base import BaseCommand
from pos.models import PaymentMethod


class Command(BaseCommand):
    help = 'Setup default payment methods'

    def handle(self, *args, **options):
        payment_methods = [
            {'name': 'Cash', 'code': 'CASH', 'requires_reference': False, 'icon': 'bi-cash'},
            {'name': 'M-Pesa', 'code': 'MPESA', 'requires_reference': True, 'icon': 'bi-phone'},
            {'name': 'Credit Card', 'code': 'CARD', 'requires_reference': True, 'icon': 'bi-credit-card'},
            {'name': 'Bank Transfer', 'code': 'BANK', 'requires_reference': True, 'icon': 'bi-bank'},
            {'name': 'Cheque', 'code': 'CHEQUE', 'requires_reference': True, 'icon': 'bi-file-text'},
        ]
        
        created_count = 0
        for pm_data in payment_methods:
            pm, created = PaymentMethod.objects.get_or_create(
                code=pm_data['code'],
                defaults=pm_data
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Created payment method: {pm.name}'))
            else:
                self.stdout.write(f'  Payment method already exists: {pm.name}')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Setup complete! Created {created_count} new payment methods.'))
