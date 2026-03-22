"""
Management command to check email configuration
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.mail import send_mail


class Command(BaseCommand):
    help = 'Check email configuration and test sending'

    def handle(self, *args, **options):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("EMAIL CONFIGURATION CHECK")
        self.stdout.write("=" * 60 + "\n")
        
        # Check settings
        self.stdout.write("Current Email Settings:")
        self.stdout.write(f"  EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
        self.stdout.write(f"  EMAIL_HOST: {settings.EMAIL_HOST}")
        self.stdout.write(f"  EMAIL_PORT: {settings.EMAIL_PORT}")
        self.stdout.write(f"  EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"  EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
        self.stdout.write(f"  EMAIL_HOST_PASSWORD: {'*' * len(settings.EMAIL_HOST_PASSWORD) if settings.EMAIL_HOST_PASSWORD else '(not set)'}")
        self.stdout.write(f"  DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
        self.stdout.write(f"  SITE_URL: {settings.SITE_URL}")
        
        self.stdout.write("\n" + "=" * 60)
        
        # Check if using console backend
        if 'console' in settings.EMAIL_BACKEND.lower():
            self.stdout.write(self.style.WARNING(
                "\n⚠️  WARNING: Using console email backend!"
            ))
            self.stdout.write("Emails will be printed to console, not sent via SMTP.")
            self.stdout.write("\nTo fix this:")
            self.stdout.write("1. Make sure python-dotenv is installed: pip install python-dotenv")
            self.stdout.write("2. Check your .env file has correct settings")
            self.stdout.write("3. Restart Django server")
        else:
            self.stdout.write(self.style.SUCCESS(
                "\n✓ Using SMTP email backend"
            ))
            
            # Check if credentials are set
            if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
                self.stdout.write(self.style.ERROR(
                    "\n✗ EMAIL_HOST_USER or EMAIL_HOST_PASSWORD not set!"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "✓ SMTP credentials are configured"
                ))
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("TESTING EMAIL SEND")
        self.stdout.write("=" * 60 + "\n")
        
        try:
            send_mail(
                'Test Email from POS System',
                'This is a test email to verify email configuration.',
                settings.DEFAULT_FROM_EMAIL,
                [settings.DEFAULT_FROM_EMAIL],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(
                "✓ Test email sent successfully!"
            ))
            self.stdout.write(f"Check inbox for: {settings.DEFAULT_FROM_EMAIL}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f"✗ Failed to send test email: {str(e)}"
            ))
            self.stdout.write("\nCommon issues:")
            self.stdout.write("1. Sender email not verified in Mailjet")
            self.stdout.write("2. Invalid SMTP credentials")
            self.stdout.write("3. Firewall blocking port 587")
            self.stdout.write("4. .env file not loaded (restart Django)")
