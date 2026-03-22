"""
Management command to get user credentials from registration
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pos.models import BusinessRegistration


class Command(BaseCommand):
    help = 'Get user credentials from registration email'

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            type=str,
            help='Email address of the registration'
        )

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        
        try:
            # Find the user
            user = User.objects.get(email=email)
            
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write("USER CREDENTIALS")
            self.stdout.write("=" * 60 + "\n")
            
            self.stdout.write(f"Email: {user.email}")
            self.stdout.write(f"Username: {user.username}")
            self.stdout.write(f"First Name: {user.first_name}")
            self.stdout.write(f"Last Name: {user.last_name}")
            self.stdout.write(f"Is Active: {user.is_active}")
            self.stdout.write(f"Date Joined: {user.date_joined}")
            
            # Find registration
            try:
                registration = BusinessRegistration.objects.get(email=email, user=user)
                self.stdout.write(f"\nBusiness: {registration.business_name}")
                if registration.business:
                    self.stdout.write(f"Business ID: {registration.business.id}")
                    self.stdout.write(f"Business Slug: {registration.business.slug}")
            except BusinessRegistration.DoesNotExist:
                pass
            
            self.stdout.write("\n" + "=" * 60)
            self.stdout.write("PASSWORD RESET")
            self.stdout.write("=" * 60 + "\n")
            
            self.stdout.write("The original password was sent via email (printed to console).")
            self.stdout.write("If you can't find it, reset the password:\n")
            self.stdout.write(f"  python manage.py reset_user_password {user.username}\n")
            
            self.stdout.write("Or set a new password now? (y/n): ", ending='')
            
            import sys
            if sys.stdin.isatty():
                response = input()
                if response.lower() == 'y':
                    from getpass import getpass
                    password = getpass("Enter new password: ")
                    password_confirm = getpass("Confirm password: ")
                    
                    if password == password_confirm:
                        user.set_password(password)
                        user.save()
                        self.stdout.write(self.style.SUCCESS(
                            f"\n✓ Password updated for {user.username}"
                        ))
                        self.stdout.write(f"\nLogin at: http://localhost:8000/login/")
                        self.stdout.write(f"Username: {user.username}")
                    else:
                        self.stdout.write(self.style.ERROR(
                            "\n✗ Passwords don't match"
                        ))
            
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"✗ No user found with email: {email}"
            ))
            
            # Check if registration exists
            try:
                registration = BusinessRegistration.objects.get(email=email)
                self.stdout.write(f"\nRegistration found but user not created:")
                self.stdout.write(f"  Status: {registration.get_status_display()}")
                self.stdout.write(f"  Business: {registration.business_name}")
                
                if registration.status != 'completed':
                    self.stdout.write("\nRegistration is not completed. Complete it first:")
                    if registration.status == 'pending':
                        self.stdout.write(f"  python manage.py resend_verification_email {email}")
            except BusinessRegistration.DoesNotExist:
                self.stdout.write("\nNo registration found for this email either.")
