import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.contrib.auth.models import User

# Get admin user
admin = User.objects.get(username='admin')

# Set new password
new_password = 'Edwin254.@'
admin.set_password(new_password)
admin.save()

print(f"Password successfully reset for user: {admin.username}")
print(f"New password: {new_password}")
print(f"You can now login at: http://127.0.0.1:8000/login/")
