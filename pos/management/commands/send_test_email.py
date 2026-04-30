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
            self.stdout.write(f'SMTP Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}')
            self.stdout.write(f'From: {settings.DEFAULT_FROM_EMAIL}')
        
        try:
            send_mail(
                subject='Test Email from POS System',
                message='This is a test email to verify your email configuration is working correctly.',
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
            self.stdout.write('1. Check your EMAIL_HOST_USER and EMAIL_HOST_PASSWORD')
            self.stdout.write('2. For Mailjet, use API key as EMAIL_HOST_USER and secret key as EMAIL_HOST_PASSWORD')
            self.stdout.write('3. Verify EMAIL_HOST is in-v3.mailjet.com and EMAIL_PORT is correct')
            self.stdout.write('4. Confirm sender email/domain is verified in Mailjet')
