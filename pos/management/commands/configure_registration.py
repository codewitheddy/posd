"""
Management command to configure registration settings
"""

from django.core.management.base import BaseCommand
from pos.models import RegistrationSettings


class Command(BaseCommand):
    help = 'Configure registration control settings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--enable',
            action='store_true',
            help='Enable registrations'
        )
        parser.add_argument(
            '--disable',
            action='store_true',
            help='Disable registrations'
        )
        parser.add_argument(
            '--require-invitation',
            action='store_true',
            help='Require invitation code for registration'
        )
        parser.add_argument(
            '--no-invitation',
            action='store_true',
            help='Do not require invitation code'
        )
        parser.add_argument(
            '--require-approval',
            action='store_true',
            help='Require admin approval for registrations'
        )
        parser.add_argument(
            '--no-approval',
            action='store_true',
            help='Do not require admin approval'
        )
        parser.add_argument(
            '--require-email-verification',
            action='store_true',
            help='Require email verification for registrations'
        )
        parser.add_argument(
            '--no-email-verification',
            action='store_true',
            help='Do not require email verification (instant registration)'
        )
        parser.add_argument(
            '--block-domains',
            type=str,
            help='Comma-separated list of domains to block'
        )
        parser.add_argument(
            '--allow-domains',
            type=str,
            help='Comma-separated list of domains to allow (whitelist)'
        )
        parser.add_argument(
            '--admin-emails',
            type=str,
            help='Comma-separated list of admin notification emails'
        )
        parser.add_argument(
            '--show',
            action='store_true',
            help='Show current settings'
        )

    def handle(self, *args, **options):
        settings = RegistrationSettings.get_settings()
        
        # Show current settings
        if options['show']:
            self.show_settings(settings)
            return
        
        # Update settings
        updated = False
        
        if options['enable']:
            settings.registration_enabled = True
            updated = True
            self.stdout.write(self.style.SUCCESS('✅ Registrations enabled'))
        
        if options['disable']:
            settings.registration_enabled = False
            updated = True
            self.stdout.write(self.style.WARNING('⚠️  Registrations disabled'))
        
        if options['require_invitation']:
            settings.require_invitation_code = True
            updated = True
            self.stdout.write(self.style.SUCCESS('✅ Invitation code required'))
        
        if options['no_invitation']:
            settings.require_invitation_code = False
            updated = True
            self.stdout.write(self.style.SUCCESS('✅ Invitation code not required'))
        
        if options['require_approval']:
            settings.require_admin_approval = True
            updated = True
            self.stdout.write(self.style.SUCCESS('✅ Admin approval required'))
        
        if options['no_approval']:
            settings.require_admin_approval = False
            updated = True
            self.stdout.write(self.style.SUCCESS('✅ Admin approval not required'))
        
        if options['require_email_verification']:
            settings.require_email_verification = True
            updated = True
            self.stdout.write(self.style.SUCCESS('✅ Email verification required'))
        
        if options['no_email_verification']:
            settings.require_email_verification = False
            updated = True
            self.stdout.write(self.style.SUCCESS('✅ Email verification not required (instant registration)'))
        
        if options['block_domains']:
            settings.blocked_email_domains = options['block_domains']
            updated = True
            self.stdout.write(self.style.SUCCESS(f'✅ Blocked domains: {options["block_domains"]}'))
        
        if options['allow_domains']:
            settings.allowed_email_domains = options['allow_domains']
            updated = True
            self.stdout.write(self.style.SUCCESS(f'✅ Allowed domains: {options["allow_domains"]}'))
        
        if options['admin_emails']:
            settings.admin_notification_emails = options['admin_emails']
            updated = True
            self.stdout.write(self.style.SUCCESS(f'✅ Admin emails: {options["admin_emails"]}'))
        
        if updated:
            settings.save()
            self.stdout.write(self.style.SUCCESS('\n✅ Settings saved successfully\n'))
            self.show_settings(settings)
        else:
            self.stdout.write(self.style.WARNING('No changes made. Use --show to see current settings.'))
    
    def show_settings(self, settings):
        """Display current registration settings"""
        self.stdout.write(self.style.SUCCESS('\n📋 Current Registration Settings:\n'))
        
        # Status
        status = '🟢 ENABLED' if settings.registration_enabled else '🔴 DISABLED'
        self.stdout.write(f'  Registration Status: {status}')
        
        # Requirements
        self.stdout.write('\n  Requirements:')
        self.stdout.write(f'    Invitation Code: {"✅ Required" if settings.require_invitation_code else "❌ Not Required"}')
        self.stdout.write(f'    Email Verification: {"✅ Required" if settings.require_email_verification else "❌ Not Required"}')
        self.stdout.write(f'    Admin Approval: {"✅ Required" if settings.require_admin_approval else "❌ Not Required"}')
        self.stdout.write(f'    KRA PIN: {"✅ Required" if settings.require_kra_pin else "❌ Not Required"}')
        
        # Rate Limits
        self.stdout.write('\n  Rate Limits:')
        self.stdout.write(f'    Per IP per day: {settings.max_registrations_per_ip_per_day}')
        self.stdout.write(f'    Per domain per day: {settings.max_registrations_per_email_domain_per_day}')
        
        # Domain Controls
        self.stdout.write('\n  Domain Controls:')
        if settings.blocked_email_domains:
            self.stdout.write(f'    Blocked: {settings.blocked_email_domains}')
        else:
            self.stdout.write(f'    Blocked: None')
        
        if settings.allowed_email_domains:
            self.stdout.write(f'    Allowed (whitelist): {settings.allowed_email_domains}')
        else:
            self.stdout.write(f'    Allowed: All (no whitelist)')
        
        # Notifications
        self.stdout.write('\n  Notifications:')
        self.stdout.write(f'    Notify admins: {"✅ Yes" if settings.notify_admin_on_registration else "❌ No"}')
        if settings.admin_notification_emails:
            self.stdout.write(f'    Admin emails: {settings.admin_notification_emails}')
        
        self.stdout.write('')
