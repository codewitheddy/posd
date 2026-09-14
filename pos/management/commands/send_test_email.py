"""
Management command to send test email
"""
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = 'Send test email to verify email configuration'

    def add_arguments(self, parser):
        parser.add_argument('recipient', type=str, help='Email address to send test email to')

    def handle(self, *args, **options):
        recipient = options['recipient']

        self.stdout.write(f'Sending test email to {recipient}...')
        self.stdout.write(f'Using backend: {settings.EMAIL_BACKEND}')

        if settings.EMAIL_HOST_USER:
            ssl = getattr(settings, 'EMAIL_USE_SSL', False)
            tls = getattr(settings, 'EMAIL_USE_TLS', False)
            self.stdout.write(f'SMTP Host:    {settings.EMAIL_HOST}:{settings.EMAIL_PORT}')
            self.stdout.write(f'Encryption:   {"SSL" if ssl else "STARTTLS" if tls else "None"}')
            self.stdout.write(f'From:         {settings.DEFAULT_FROM_EMAIL}')

        try:
            send_mail(
                subject='Test Email from POS System',
                message='This is a test email to verify your cPanel email configuration is working correctly.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )

            self.stdout.write(self.style.SUCCESS(f'✅ Test email sent successfully to {recipient}'))

            if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
                self.stdout.write(self.style.WARNING(
                    '\n⚠️  You are using console backend. Email was printed above, not actually sent.'
                ))
                self.stdout.write(self.style.WARNING(
                    'To send real emails, configure SMTP settings in your .env file.'
                ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to send test email: {str(e)}'))
            self.stdout.write(self.style.ERROR('\nTroubleshooting:'))
            self.stdout.write('1. Check EMAIL_HOST_USER (full email address) and EMAIL_HOST_PASSWORD')
            self.stdout.write('2. Verify EMAIL_HOST matches your cPanel mail hostname (e.g. mail.marid.co.ke)')
            self.stdout.write('3. Port 465 requires EMAIL_USE_SSL=True and EMAIL_USE_TLS=False')
            self.stdout.write('4. Port 587 requires EMAIL_USE_TLS=True and EMAIL_USE_SSL=False')
            self.stdout.write('5. "Invalid HELO name" → set EMAIL_HELO_NAME=marid.co.ke in your .env')
            self.stdout.write('6. Confirm the email account exists in cPanel → Email Accounts')
