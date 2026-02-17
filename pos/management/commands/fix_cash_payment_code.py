"""
Management command to fix CASH payment method codes
Updates any payment method with name='CASH' to have code='CASH'
"""
from django.core.management.base import BaseCommand
from pos.models import PaymentMethod


class Command(BaseCommand):
    help = 'Fix CASH payment method codes to be "CASH" instead of other codes'

    def handle(self, *args, **options):
        # Find all payment methods with name CASH but code != CASH
        cash_methods = PaymentMethod.objects.filter(
            name__iexact='CASH'
        ).exclude(code='CASH')
        
        if not cash_methods.exists():
            self.stdout.write(self.style.SUCCESS('✓ All CASH payment methods already have correct code'))
            return
        
        self.stdout.write(f'\nFound {cash_methods.count()} CASH payment method(s) with incorrect code:\n')
        
        for method in cash_methods:
            old_code = method.code
            self.stdout.write(
                f'  Business: {method.business.name}, '
                f'Name: "{method.name}", '
                f'Old Code: "{old_code}"'
            )
            
            # Update code to CASH
            method.code = 'CASH'
            method.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'  ✓ Updated to code="CASH"'
                )
            )
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ Updated {cash_methods.count()} payment method(s)'))
        self.stdout.write('\nNote: This ensures cash calculations work correctly in reports.')
