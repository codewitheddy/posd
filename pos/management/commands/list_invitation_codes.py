"""
Management command to list invitation codes
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import F
from pos.models import InvitationCode


class Command(BaseCommand):
    help = 'List all invitation codes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--active-only',
            action='store_true',
            help='Show only active codes',
        )
        parser.add_argument(
            '--unused-only',
            action='store_true',
            help='Show only unused codes',
        )

    def handle(self, *args, **options):
        codes = InvitationCode.objects.all()
        
        if options['active_only']:
            codes = codes.filter(is_active=True)
        
        if options['unused_only']:
            codes = codes.filter(uses_count=0)
        
        if not codes.exists():
            self.stdout.write(self.style.WARNING('No invitation codes found.'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\n📋 Found {codes.count()} invitation code(s):\n'))
        
        now = timezone.now()
        
        for code in codes:
            # Determine status
            is_valid, message = code.is_valid()
            
            if is_valid:
                status = self.style.SUCCESS('✅ ACTIVE')
            elif code.uses_count >= code.max_uses:
                status = self.style.WARNING('⚠️  USED UP')
            elif not code.is_active:
                status = self.style.ERROR('❌ INACTIVE')
            elif code.valid_until and now > code.valid_until:
                status = self.style.WARNING('⏰ EXPIRED')
            else:
                status = self.style.WARNING('⚠️  INVALID')
            
            self.stdout.write(f'  Code: {self.style.HTTP_INFO(code.code)}')
            self.stdout.write(f'    Status: {status}')
            self.stdout.write(f'    Usage: {code.uses_count}/{code.max_uses}')
            
            if code.valid_until:
                if now > code.valid_until:
                    self.stdout.write(f'    Expired: {code.valid_until.strftime("%Y-%m-%d %H:%M")}')
                else:
                    self.stdout.write(f'    Valid Until: {code.valid_until.strftime("%Y-%m-%d %H:%M")}')
            else:
                self.stdout.write(f'    Valid Until: No expiry')
            
            if code.allowed_email_domains:
                self.stdout.write(f'    Allowed Domains: {code.allowed_email_domains}')
            
            if code.notes:
                self.stdout.write(f'    Notes: {code.notes}')
            
            self.stdout.write('')  # Blank line
        
        # Summary
        active_count = codes.filter(is_active=True, uses_count__lt=F('max_uses')).count()
        self.stdout.write(self.style.SUCCESS(f'📊 Summary: {active_count} active, {codes.count() - active_count} inactive/used'))
