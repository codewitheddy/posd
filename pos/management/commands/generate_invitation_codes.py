"""
Management command to generate invitation codes for controlled registration
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import secrets
import string
from pos.models import InvitationCode, User


class Command(BaseCommand):
    help = 'Generate invitation codes for controlled registration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=1,
            help='Number of codes to generate'
        )
        parser.add_argument(
            '--max-uses',
            type=int,
            default=1,
            help='Maximum number of times each code can be used'
        )
        parser.add_argument(
            '--valid-days',
            type=int,
            default=None,
            help='Number of days the code is valid (leave empty for no expiry)'
        )
        parser.add_argument(
            '--prefix',
            type=str,
            default='',
            help='Prefix for the codes (e.g., BETA, TRIAL)'
        )
        parser.add_argument(
            '--length',
            type=int,
            default=8,
            help='Length of the random part of the code'
        )
        parser.add_argument(
            '--allowed-domains',
            type=str,
            default='',
            help='Comma-separated list of allowed email domains'
        )
        parser.add_argument(
            '--notes',
            type=str,
            default='',
            help='Notes about these codes'
        )
        parser.add_argument(
            '--created-by',
            type=str,
            default=None,
            help='Username of the user creating these codes'
        )

    def handle(self, *args, **options):
        count = options['count']
        max_uses = options['max_uses']
        valid_days = options['valid_days']
        prefix = options['prefix']
        length = options['length']
        allowed_domains = options['allowed_domains']
        notes = options['notes']
        created_by_username = options['created_by']
        
        # Get creator user
        created_by = None
        if created_by_username:
            try:
                created_by = User.objects.get(username=created_by_username)
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(
                    f'User {created_by_username} not found. Codes will be created without creator.'
                ))
        
        # Calculate expiry
        valid_until = None
        if valid_days:
            valid_until = timezone.now() + timedelta(days=valid_days)
        
        # Generate codes
        generated_codes = []
        for i in range(count):
            # Generate random code
            random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))
            code = f"{prefix}{random_part}" if prefix else random_part
            
            # Ensure uniqueness
            while InvitationCode.objects.filter(code=code).exists():
                random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(length))
                code = f"{prefix}{random_part}" if prefix else random_part
            
            # Create invitation code
            invitation_code = InvitationCode.objects.create(
                code=code,
                created_by=created_by,
                max_uses=max_uses,
                valid_until=valid_until,
                allowed_email_domains=allowed_domains,
                notes=notes
            )
            
            generated_codes.append(invitation_code)
        
        # Display results
        self.stdout.write(self.style.SUCCESS(f'\n✅ Successfully generated {count} invitation code(s):\n'))
        
        for code in generated_codes:
            self.stdout.write(f'  Code: {self.style.SUCCESS(code.code)}')
            self.stdout.write(f'    Max Uses: {code.max_uses}')
            if code.valid_until:
                self.stdout.write(f'    Valid Until: {code.valid_until.strftime("%Y-%m-%d %H:%M")}')
            else:
                self.stdout.write(f'    Valid Until: No expiry')
            if code.allowed_email_domains:
                self.stdout.write(f'    Allowed Domains: {code.allowed_email_domains}')
            if code.notes:
                self.stdout.write(f'    Notes: {code.notes}')
            self.stdout.write('')
        
        # Usage instructions
        self.stdout.write(self.style.WARNING('\n📋 Usage Instructions:'))
        self.stdout.write('  1. Share these codes with users you want to invite')
        self.stdout.write('  2. Users will enter the code during registration')
        self.stdout.write('  3. Monitor code usage in the admin panel')
        self.stdout.write('  4. Deactivate codes if needed\n')
