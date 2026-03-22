"""
Management command to resend verification email for pending registrations
"""

from django.core.management.base import BaseCommand
from pos.models import BusinessRegistration
from pos.services.registration_service import RegistrationService


class Command(BaseCommand):
    help = 'Resend verification email for a pending registration'

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            type=str,
            help='Email address of the registration'
        )

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        
        try:
            registration = BusinessRegistration.objects.get(
                email=email,
                status='pending'
            )
            
            self.stdout.write(f"Found pending registration for: {email}")
            self.stdout.write(f"Business: {registration.business_name}")
            self.stdout.write(f"Name: {registration.first_name} {registration.last_name}")
            
            # Regenerate token if needed
            if not registration.email_verification_token:
                registration.generate_verification_token()
                self.stdout.write(self.style.SUCCESS("Generated new verification token"))
            
            # Send verification email
            success = RegistrationService.send_verification_email(registration)
            
            if success:
                self.stdout.write(self.style.SUCCESS(
                    f"✓ Verification email sent to {email}"
                ))
                self.stdout.write(f"\nVerification link:")
                from django.conf import settings
                verification_url = f"{settings.SITE_URL}/verify-email/{registration.email_verification_token}/"
                self.stdout.write(verification_url)
            else:
                self.stdout.write(self.style.ERROR(
                    "✗ Failed to send email. Check your email configuration."
                ))
                self.stdout.write("\nYou can manually verify using this link:")
                from django.conf import settings
                verification_url = f"{settings.SITE_URL}/verify-email/{registration.email_verification_token}/"
                self.stdout.write(verification_url)
                
        except BusinessRegistration.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"✗ No pending registration found for: {email}"
            ))
            
            # Check if registration exists in other states
            other_registrations = BusinessRegistration.objects.filter(email=email)
            if other_registrations.exists():
                self.stdout.write("\nFound registrations in other states:")
                for reg in other_registrations:
                    self.stdout.write(f"  - Status: {reg.get_status_display()}")
                    if reg.status == 'completed':
                        self.stdout.write(f"    User: {reg.user.username if reg.user else 'N/A'}")
            else:
                self.stdout.write("\nNo registrations found for this email.")
