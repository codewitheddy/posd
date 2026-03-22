"""
Management command to set trial expiry date for testing
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pos.models import Business


class Command(BaseCommand):
    help = 'Set trial expiry date for a business (for testing)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business-id',
            type=int,
            help='Business ID to update'
        )
        parser.add_argument(
            '--business-slug',
            type=str,
            help='Business slug to update'
        )
        parser.add_argument(
            '--days',
            type=int,
            required=True,
            help='Number of days until expiry (use negative for expired)'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Apply to all businesses'
        )

    def handle(self, *args, **options):
        days = options['days']
        expiry_date = timezone.now() + timedelta(days=days)
        
        # Get businesses to update
        if options['all']:
            businesses = Business.objects.all()
            self.stdout.write(f'Updating all {businesses.count()} businesses...\n')
        elif options['business_id']:
            businesses = Business.objects.filter(id=options['business_id'])
            if not businesses.exists():
                self.stdout.write(self.style.ERROR(f'Business with ID {options["business_id"]} not found'))
                return
        elif options['business_slug']:
            businesses = Business.objects.filter(slug=options['business_slug'])
            if not businesses.exists():
                self.stdout.write(self.style.ERROR(f'Business with slug {options["business_slug"]} not found'))
                return
        else:
            self.stdout.write(self.style.ERROR('Please specify --business-id, --business-slug, or --all'))
            return
        
        # Update businesses
        for business in businesses:
            business.is_trial = True
            business.trial_ends_at = expiry_date
            business.save()
            
            status = "EXPIRED" if days < 0 else f"{days} days remaining"
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ {business.name} (ID: {business.id}): Trial set to {expiry_date.strftime("%Y-%m-%d %H:%M")} ({status})'
                )
            )
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Updated {businesses.count()} business(es)'))
        
        # Show testing instructions
        self.stdout.write('\n' + '='*60)
        self.stdout.write('TESTING INSTRUCTIONS:')
        self.stdout.write('='*60)
        self.stdout.write('\n1. Visit the dashboard to see the trial banner')
        self.stdout.write('2. Different warning levels:')
        self.stdout.write('   - 14+ days: Info banner (purple)')
        self.stdout.write('   - 7-13 days: Warning banner (pink)')
        self.stdout.write('   - 1-6 days: Danger banner (orange)')
        self.stdout.write('   - 0 days: Expires today (orange)')
        self.stdout.write('   - Negative: Expired (orange)')
        self.stdout.write('\n3. Test different scenarios:')
        self.stdout.write(f'   python manage.py set_trial_expiry --business-id {businesses.first().id if businesses.exists() else "1"} --days 15  # Info')
        self.stdout.write(f'   python manage.py set_trial_expiry --business-id {businesses.first().id if businesses.exists() else "1"} --days 7   # Warning')
        self.stdout.write(f'   python manage.py set_trial_expiry --business-id {businesses.first().id if businesses.exists() else "1"} --days 3   # Danger')
        self.stdout.write(f'   python manage.py set_trial_expiry --business-id {businesses.first().id if businesses.exists() else "1"} --days 0   # Expires today')
        self.stdout.write(f'   python manage.py set_trial_expiry --business-id {businesses.first().id if businesses.exists() else "1"} --days -5  # Expired')
        self.stdout.write('\n4. Reset to 30 days:')
        self.stdout.write(f'   python manage.py set_trial_expiry --business-id {businesses.first().id if businesses.exists() else "1"} --days 30')
        self.stdout.write('')
