"""
Management command to fix cash payment method codes and settings
"""
from django.core.management.base import BaseCommand
from pos.models import PaymentMethod


class Command(BaseCommand):
    help = 'Fix cash payment method codes and reference requirements'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n=== DRY RUN MODE - No changes will be made ===\n'))
        else:
            self.stdout.write(self.style.SUCCESS('\n=== Fixing Cash Payment Methods ===\n'))
        
        fixed_count = 0
        
        # Find all payment methods that look like cash
        cash_methods = PaymentMethod.objects.filter(
            name__icontains='cash',
            is_active=True
        )
        
        self.stdout.write(f'Found {cash_methods.count()} cash payment methods\n')
        
        for method in cash_methods:
            changes = []
            
            # Fix code if not exactly "CASH"
            if method.code != 'CASH':
                changes.append(f'Code: "{method.code}" → "CASH"')
                if not dry_run:
                    method.code = 'CASH'
            
            # Fix requires_reference if True
            if method.requires_reference:
                changes.append(f'requires_reference: True → False')
                if not dry_run:
                    method.requires_reference = False
            
            if changes:
                self.stdout.write(f'\nBusiness: {method.business.name}')
                self.stdout.write(f'  Payment Method: {method.name}')
                for change in changes:
                    self.stdout.write(f'    • {change}')
                
                if not dry_run:
                    method.save()
                    self.stdout.write(self.style.SUCCESS('    ✓ Fixed'))
                else:
                    self.stdout.write(self.style.WARNING('    (Would fix in real run)'))
                
                fixed_count += 1
        
        if fixed_count == 0:
            self.stdout.write(self.style.SUCCESS('\n✓ All cash payment methods are correctly configured!'))
        else:
            if dry_run:
                self.stdout.write(self.style.WARNING(f'\n{fixed_count} payment method(s) would be fixed'))
                self.stdout.write(self.style.WARNING('Run without --dry-run to apply fixes'))
            else:
                self.stdout.write(self.style.SUCCESS(f'\n✓ Fixed {fixed_count} payment method(s)'))
        
        self.stdout.write('')
