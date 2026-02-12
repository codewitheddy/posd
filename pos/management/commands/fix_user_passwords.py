"""
Management command to reset passwords for users who can't login
This is a one-time fix for users created before the password fix
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Reset passwords for users who cannot login (one-time fix)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            help='Reset password for specific username',
        )
        parser.add_argument(
            '--password',
            type=str,
            default='changeme123',
            help='New password to set (default: changeme123)',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Reset passwords for all non-superuser users',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        password = options.get('password')
        reset_all = options.get('all')

        if username:
            # Reset specific user
            try:
                user = User.objects.get(username=username)
                user.set_password(password)
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Password reset for user: {username}\n'
                        f'  New password: {password}\n'
                        f'  Email: {user.email}'
                    )
                )
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'✗ User not found: {username}')
                )

        elif reset_all:
            # Reset all non-superuser users
            users = User.objects.filter(is_superuser=False)
            count = 0
            
            self.stdout.write(
                self.style.WARNING(
                    f'\nResetting passwords for {users.count()} users...\n'
                )
            )
            
            for user in users:
                user.set_password(password)
                user.save()
                count += 1
                self.stdout.write(
                    f'  ✓ {user.username} ({user.email})'
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Reset {count} passwords\n'
                    f'  New password for all: {password}\n'
                    f'  Users should change their password after login'
                )
            )

        else:
            # Show usage
            self.stdout.write(
                self.style.WARNING(
                    'Usage:\n'
                    '  python manage.py fix_user_passwords --username <username> --password <new_password>\n'
                    '  python manage.py fix_user_passwords --all --password <new_password>\n\n'
                    'Examples:\n'
                    '  python manage.py fix_user_passwords --username john --password newpass123\n'
                    '  python manage.py fix_user_passwords --all --password changeme123\n'
                )
            )
