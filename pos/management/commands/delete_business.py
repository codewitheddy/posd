"""
Management command to safely delete a business and all its data
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from pos.models import Business


class Command(BaseCommand):
    help = 'Safely delete a business and all its related data'

    def add_arguments(self, parser):
        parser.add_argument('slug', type=str, help='Business slug to delete')
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion without prompting',
        )

    def handle(self, *args, **options):
        slug = options['slug']
        confirm = options['confirm']

        try:
            business = Business.objects.get(slug=slug)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business with slug "{slug}" not found'))
            return

        # Show business details
        self.stdout.write(self.style.WARNING('\n' + '='*60))
        self.stdout.write(self.style.WARNING('BUSINESS DELETION'))
        self.stdout.write(self.style.WARNING('='*60))
        self.stdout.write(f'Business Name: {business.name}')
        self.stdout.write(f'Slug: {business.slug}')
        self.stdout.write(f'Owner: {business.owner.username} ({business.owner.email})')
        self.stdout.write(f'Created: {business.created_at}')
        self.stdout.write(f'Status: {"Active" if business.is_active else "Inactive"}')
        self.stdout.write(f'Subscription: {business.subscription_plan}')

        # Count related data
        self.stdout.write(self.style.WARNING('\nRelated Data (will be deleted):'))
        self.stdout.write(f'  - Members: {business.memberships.count()}')
        self.stdout.write(f'  - Products: {business.products.count()}')
        self.stdout.write(f'  - Categories: {business.categories.count()}')
        self.stdout.write(f'  - Sales: {business.sales.count()}')
        self.stdout.write(f'  - Customers: {business.customers.count()}')
        self.stdout.write(f'  - Suppliers: {business.suppliers.count()}')
        self.stdout.write(f'  - Purchases: {business.purchases.count()}')
        self.stdout.write(f'  - Payment Methods: {business.payment_methods.count()}')
        self.stdout.write(f'  - Shifts: {business.shifts.count()}')
        self.stdout.write(f'  - Expenses: {business.expenses.count()}')
        
        # Check for settings
        try:
            settings = business.settings
            self.stdout.write(f'  - Business Settings: Yes')
        except:
            self.stdout.write(f'  - Business Settings: No')

        # Warning
        self.stdout.write(self.style.ERROR('\n⚠️  WARNING: This action CANNOT be undone!'))
        self.stdout.write(self.style.ERROR('All business data will be permanently deleted.'))

        # Confirm deletion
        if not confirm:
            self.stdout.write('\nType the business name to confirm deletion:')
            confirmation = input(f'Enter "{business.name}" to proceed: ')
            
            if confirmation != business.name:
                self.stdout.write(self.style.ERROR('\nDeletion cancelled - name did not match'))
                return

        # Perform deletion
        self.stdout.write('\nDeleting business...')
        
        try:
            with transaction.atomic():
                business_name = business.name
                business.delete()
                
            self.stdout.write(self.style.SUCCESS(f'\n✓ Business "{business_name}" has been successfully deleted'))
            self.stdout.write(self.style.SUCCESS('All related data has been removed'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Error deleting business: {str(e)}'))
            self.stdout.write(self.style.ERROR('Deletion rolled back - no data was deleted'))
