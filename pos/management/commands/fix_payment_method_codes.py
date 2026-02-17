"""
Management command to fix payment method codes
Sets code='CASH' for payment methods with name='CASH' but missing code
"""
from django.core.management.base import BaseCommand
from pos.models import PaymentMethod


class Command(BaseCommand):
    help = 'Fix payment method codes for existing CASH payment methods'

    def handle(self, *args, **options):
        # Find CASH payment methods without code
        cash_methods = PaymentMethod.objects.filter(
            name__iexact='CASH'
        ).filter(
            code__isnull=True
        ) | PaymentMethod.objects.filter(
            name__iexact='CASH',
            code=''
        )
        
        updated_count = 0
        for method in cash_methods:
            method.code = 'CASH'
            method.save()
            updated_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Updated payment method "{method.name}" (ID: {method.id}) for business "{method.business.name}"'
                )
            )
        
        if updated_count == 0:
            self.stdout.write(self.style.WARNING('No payment methods needed updating'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\n✓ Updated {updated_count} payment method(s)')
            )
