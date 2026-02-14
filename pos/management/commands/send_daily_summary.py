"""
Management command to send daily sales summary
Run this daily at end of day via cron job or task scheduler
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from pos.models import Business
from pos.email_service import EmailService


class Command(BaseCommand):
    help = 'Send daily sales summary to business admins'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business',
            type=str,
            help='Business slug to send summary for (optional, sends to all if not specified)',
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Date to send summary for (YYYY-MM-DD format, defaults to today)',
        )

    def handle(self, *args, **options):
        business_slug = options.get('business')
        date_str = options.get('date')
        
        # Parse date
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
                return
        else:
            date = timezone.now().date()
        
        # Get businesses
        if business_slug:
            businesses = Business.objects.filter(slug=business_slug, is_active=True)
        else:
            businesses = Business.objects.filter(is_active=True)
        
        self.stdout.write(f'Sending daily summary for {date.strftime("%d/%m/%Y")}...\n')
        
        total_sent = 0
        
        for business in businesses:
            self.stdout.write(f'  {business.name}...')
            
            success = EmailService.send_daily_summary(business, date)
            
            if success:
                self.stdout.write(self.style.SUCCESS(f'    ✅ Summary sent'))
                total_sent += 1
            else:
                self.stdout.write(self.style.WARNING(f'    ⚠️  Failed to send (check email settings or daily summaries disabled)'))
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Daily summary complete. Sent {total_sent} summary/summaries.'))
