"""
Management command to reset user password
Usage: python manage.py reset_user_password <username_or_email> <new_password>
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Reset password for a user (properly hashes the password)'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username or email address')
        parser.add_argument('password', type=str, help='New password')

    def handle(self, *args, **options):
        username_or_email = options['username']
        new_password = options['password']
        
        # Try to find user by username first
        user = None
        try:
            user = User.objects.get(username=username_or_email)
        except User.DoesNotExist:
            # Try by email
            try:
                user = User.objects.get(email=username_or_email)
            except User.DoesNotExist:
                raise CommandError(f'User "{username_or_email}" not found')
        
        # Set password (this properly hashes it)
        user.set_password(new_password)
        user.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✅ Password successfully updated for user: {user.username} ({user.email})'
            )
        )
        self.stdout.write(f'   You can now login with:')
        self.stdout.write(f'   Username: {user.username}')
        self.stdout.write(f'   Email: {user.email}')
        self.stdout.write(f'   Password: {new_password}')
