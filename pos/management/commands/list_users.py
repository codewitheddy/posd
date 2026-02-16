"""
Management command to list all users with their login credentials
Usage: python manage.py list_users
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pos.models import Business, BusinessMembership


class Command(BaseCommand):
    help = 'List all users with their usernames, emails, and businesses'

    def handle(self, *args, **options):
        users = User.objects.all().order_by('-date_joined')
        
        if not users.exists():
            self.stdout.write(self.style.WARNING('No users found in the database.'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\n{"="*80}'))
        self.stdout.write(self.style.SUCCESS(f'  ALL USERS ({users.count()} total)'))
        self.stdout.write(self.style.SUCCESS(f'{"="*80}\n'))
        
        for user in users:
            # Get user's businesses
            memberships = BusinessMembership.objects.filter(user=user).select_related('business')
            businesses = [f"{m.business.name} ({m.role})" for m in memberships]
            
            self.stdout.write(self.style.SUCCESS(f'👤 {user.get_full_name() or "No name"}'))
            self.stdout.write(f'   Username:  {user.username}')
            self.stdout.write(f'   Email:     {user.email}')
            self.stdout.write(f'   Superuser: {"Yes" if user.is_superuser else "No"}')
            self.stdout.write(f'   Active:    {"Yes" if user.is_active else "No"}')
            self.stdout.write(f'   Joined:    {user.date_joined.strftime("%Y-%m-%d %H:%M")}')
            
            if businesses:
                self.stdout.write(f'   Businesses: {", ".join(businesses)}')
            else:
                self.stdout.write(self.style.WARNING(f'   Businesses: None'))
            
            self.stdout.write('')  # Empty line
        
        self.stdout.write(self.style.SUCCESS(f'{"="*80}'))
        self.stdout.write(self.style.SUCCESS(f'  LOGIN INSTRUCTIONS'))
        self.stdout.write(self.style.SUCCESS(f'{"="*80}'))
        self.stdout.write('  You can login with EITHER:')
        self.stdout.write('  • Username (shown above)')
        self.stdout.write('  • Email address')
        self.stdout.write('')
        self.stdout.write('  Example:')
        self.stdout.write('    Username: john')
        self.stdout.write('    OR')
        self.stdout.write('    Email: john@example.com')
        self.stdout.write('')
