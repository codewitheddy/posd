from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from pos.models import UserProfile


class Command(BaseCommand):
    help = 'Create user profiles for existing users'

    def handle(self, *args, **options):
        users = User.objects.all()
        created_count = 0
        existing_count = 0
        
        for user in users:
            profile, created = UserProfile.objects.get_or_create(user=user)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'✓ Created profile for {user.username}'))
            else:
                existing_count += 1
                self.stdout.write(f'  Profile already exists for {user.username}')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Summary:'))
        self.stdout.write(f'  Created: {created_count}')
        self.stdout.write(f'  Already existed: {existing_count}')
        self.stdout.write(f'  Total users: {users.count()}')
