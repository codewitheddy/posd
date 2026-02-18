"""
Management command to check payment method codes
"""
from django.core.management.base import BaseCommand
from pos.models import PaymentMethod, Business


class Command(BaseCommand):
    help = 'Check payment method codes for all businesses'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n=== Payment Methods Check ===\n'))
        
        businesses = Business.objects.all()
        
        for business in businesses:
            self.stdout.write(f'\nBusiness: {business.name} ({business.slug})')
            self.stdout.write('-' * 50)
            
            methods = PaymentMethod.objects.filter(business=business, is_active=True)
            
            if not methods.exists():
                self.stdout.write(self.style.WARNING('  No payment methods found!'))
                continue
            
            for method in methods:
                cash_indicator = '💵 CASH' if method.code and method.code.upper() == 'CASH' else ''
                ref_required = '🔒 Ref Required' if method.requires_reference else '✓ No Ref'
                
                self.stdout.write(
                    f'  • {method.name:20} | Code: {method.code:10} | {ref_required} {cash_indicator}'
                )
        
        self.stdout.write(self.style.SUCCESS('\n=== Check Complete ===\n'))
        
        # Check for potential issues
        self.stdout.write(self.style.WARNING('\n=== Potential Issues ===\n'))
        
        # Find cash methods without proper code
        cash_methods = PaymentMethod.objects.filter(
            name__icontains='cash',
            is_active=True
        ).exclude(code__iexact='CASH')
        
        if cash_methods.exists():
            self.stdout.write(self.style.ERROR('Found cash methods with incorrect code:'))
            for method in cash_methods:
                self.stdout.write(f'  • Business: {method.business.name} | Name: {method.name} | Code: "{method.code}"')
                self.stdout.write(f'    Fix: Update code to "CASH"')
        else:
            self.stdout.write(self.style.SUCCESS('✓ All cash methods have correct code'))
        
        # Find methods requiring reference that might be cash
        ref_required_cash = PaymentMethod.objects.filter(
            name__icontains='cash',
            requires_reference=True,
            is_active=True
        )
        
        if ref_required_cash.exists():
            self.stdout.write(self.style.ERROR('\nFound cash methods requiring reference:'))
            for method in ref_required_cash:
                self.stdout.write(f'  • Business: {method.business.name} | Name: {method.name}')
                self.stdout.write(f'    Fix: Set requires_reference=False')
        else:
            self.stdout.write(self.style.SUCCESS('✓ No cash methods requiring reference'))
