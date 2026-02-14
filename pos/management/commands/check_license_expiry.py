"""
Management command to check license expiry and send reminders
Run this daily via cron job or task scheduler
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pos.models import Business
from pos.email_service import EmailService


class Command(BaseCommand):
    help = 'Check license expiry and send reminders (30, 15, 7 days before)'

    def handle(self, *args, **options):
        today = timezone.now().date()
        
        self.stdout.write('Checking license expiry for all businesses...\n')
        
        # Check for licenses expiring in 30, 15, 7, 3, 1 days
        reminder_days = [30, 15, 7, 3, 1]
        total_sent = 0
        
        for days in reminder_days:
            expiry_date = today + timedelta(days=days)
            businesses = Business.objects.filter(
                license_expiry_date=expiry_date,
                is_active=True
            )
            
            for business in businesses:
                self.stdout.write(f'  {business.name}: License expires in {days} days ({expiry_date})')
                
                success = EmailService.send_license_expiry_reminder(business, days)
                
                if success:
                    self.stdout.write(self.style.SUCCESS(f'    ✅ Reminder sent'))
                    total_sent += 1
                else:
                    self.stdout.write(self.style.WARNING(f'    ⚠️  Failed to send reminder (check email settings)'))
        
        # Check for expired licenses
        expired_businesses = Business.objects.filter(
            license_expiry_date__lt=today,
            is_active=True
        )
        
        if expired_businesses.exists():
            self.stdout.write(self.style.ERROR(f'\n⚠️  {expired_businesses.count()} business(es) have expired licenses:'))
            for business in expired_businesses:
                days_expired = (today - business.license_expiry_date).days
                self.stdout.write(self.style.ERROR(f'  - {business.name}: Expired {days_expired} days ago'))
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ License check complete. Sent {total_sent} reminder(s).'))
