"""
Management command to setup multi-tenancy
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from pos.models import Business, BusinessMembership


class Command(BaseCommand):
    help = 'Setup multi-tenancy for existing installation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business-name',
            type=str,
            default='Default Business',
            help='Name for the default business'
        )
        parser.add_argument(
            '--owner-username',
            type=str,
            help='Username of the business owner (defaults to first superuser)'
        )

    def handle(self, *args, **options):
        business_name = options['business_name']
        owner_username = options.get('owner_username')

        self.stdout.write(self.style.SUCCESS('🚀 Setting up multi-tenancy...'))

        try:
            with transaction.atomic():
                # Get or create owner
                if owner_username:
                    owner = User.objects.get(username=owner_username)
                else:
                    owner = User.objects.filter(is_superuser=True).first()
                    if not owner:
                        self.stdout.write(self.style.WARNING('No superuser found, creating one...'))
                        owner = User.objects.create_superuser(
                            username='admin',
                            email='admin@example.com',
                            password='admin123',
                            first_name='System',
                            last_name='Administrator'
                        )
                        self.stdout.write(self.style.SUCCESS(f'✅ Created superuser: {owner.username}'))
                        self.stdout.write(self.style.WARNING('⚠️  Default password: admin123 - CHANGE THIS!'))

                # Check if default business exists
                business = Business.objects.filter(slug='default').first()
                
                if business:
                    self.stdout.write(self.style.WARNING(f'Business already exists: {business.name}'))
                else:
                    # Create default business
                    business = Business.objects.create(
                        name=business_name,
                        slug='default',
                        owner=owner,
                        is_active=True,
                        is_trial=False,
                        subscription_plan='free'
                    )
                    self.stdout.write(self.style.SUCCESS(f'✅ Created business: {business.name}'))

                # Create or update owner membership
                membership, created = BusinessMembership.objects.get_or_create(
                    user=owner,
                    business=business,
                    defaults={
                        'role': 'owner',
                        'is_active': True
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f'✅ Added {owner.username} as owner'))
                else:
                    self.stdout.write(self.style.WARNING(f'Owner membership already exists'))

                # Summary
                self.stdout.write(self.style.SUCCESS('\n' + '='*50))
                self.stdout.write(self.style.SUCCESS('✅ Multi-tenancy setup complete!'))
                self.stdout.write(self.style.SUCCESS('='*50))
                self.stdout.write(f'\nBusiness Name: {business.name}')
                self.stdout.write(f'Business Slug: {business.slug}')
                self.stdout.write(f'Owner: {owner.username}')
                self.stdout.write(f'\nAccess URL: /b/{business.slug}/')
                self.stdout.write(f'Dashboard: /b/{business.slug}/')
                self.stdout.write(f'\nNew businesses can register at: /register/')
                self.stdout.write(f'Business list: /businesses/')
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {str(e)}'))
            raise
