"""
Management command to list all business registrations
"""

from django.core.management.base import BaseCommand
from pos.models import BusinessRegistration


class Command(BaseCommand):
    help = 'List all business registrations'

    def handle(self, *args, **options):
        registrations = BusinessRegistration.objects.all().order_by('-created_at')
        
        if not registrations.exists():
            self.stdout.write(self.style.WARNING("No registrations found in database."))
            return
        
        self.stdout.write(f"\nFound {registrations.count()} registration(s):\n")
        
        for reg in registrations:
            self.stdout.write("=" * 60)
            self.stdout.write(f"Email: {reg.email}")
            self.stdout.write(f"Business: {reg.business_name}")
            self.stdout.write(f"Name: {reg.first_name} {reg.last_name}")
            self.stdout.write(f"Phone: {reg.phone}")
            self.stdout.write(f"Status: {reg.get_status_display()}")
            self.stdout.write(f"Created: {reg.created_at}")
            
            if reg.email_verified_at:
                self.stdout.write(f"Email Verified: {reg.email_verified_at}")
            
            if reg.completed_at:
                self.stdout.write(f"Completed: {reg.completed_at}")
                if reg.user:
                    self.stdout.write(f"User: {reg.user.username}")
                if reg.business:
                    self.stdout.write(f"Business ID: {reg.business.id}")
            
            if reg.rejection_reason:
                self.stdout.write(f"Rejection Reason: {reg.rejection_reason}")
            
            self.stdout.write("")
