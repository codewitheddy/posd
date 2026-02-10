from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Reset admin password to "admin123"'

    def handle(self, *args, **kwargs):
        try:
            admin = User.objects.get(username='admin')
            admin.set_password('admin123')
            admin.save()
            self.stdout.write(self.style.SUCCESS('Admin password reset to: admin123'))
            self.stdout.write(self.style.WARNING('Please change this password after login!'))
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('Admin user does not exist. Create one with: python manage.py createsuperuser'))
