"""
Create a test support access request for testing
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.contrib.auth import get_user_model
from pos.models import Business, SupportAccessRequest

User = get_user_model()

# Get superuser (platform admin)
superuser = User.objects.filter(is_superuser=True).first()
if not superuser:
    print("❌ No superuser found. Please create a superuser first.")
    exit(1)

print(f"✅ Found superuser: {superuser.username}")

# Get first business
business = Business.objects.filter(is_active=True).first()
if not business:
    print("❌ No active business found.")
    exit(1)

print(f"✅ Found business: {business.name} (Owner: {business.owner.username})")

# Check if request already exists
existing = SupportAccessRequest.objects.filter(
    business=business,
    requested_by=superuser,
    status='pending'
).first()

if existing:
    print(f"⚠️  Pending request already exists (ID: {existing.id})")
    print(f"   Reason: {existing.reason}")
else:
    # Create test request
    request = SupportAccessRequest.objects.create(
        business=business,
        requested_by=superuser,
        reason="Test support access request - Customer needs help with system setup and configuration"
    )
    print(f"✅ Created test support access request (ID: {request.id})")
    print(f"   Business: {business.name}")
    print(f"   Requested by: {superuser.username}")
    print(f"   Status: {request.status}")

print("\n📋 Instructions:")
print(f"1. Log in as business owner: {business.owner.username}")
print(f"2. Go to Settings → Support Access")
print(f"3. You should see the pending request")
print(f"4. Approve or deny the request")
print(f"\nOr access directly: /b/{business.slug}/support-access/")
