"""
Check current user and business membership status
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from django.contrib.auth import get_user_model
from pos.models import Business, BusinessMembership, SupportAccessRequest

User = get_user_model()

# Get the user
username = input("Enter username to check (or press Enter for 'edwinmulirot64'): ").strip()
if not username:
    username = 'edwinmulirot64'

try:
    user = User.objects.get(username=username)
    print(f"\n✅ User found: {user.username}")
    print(f"   Email: {user.email}")
    print(f"   Is superuser: {user.is_superuser}")
    print(f"   Is staff: {user.is_staff}")
    
    # Get business memberships
    memberships = BusinessMembership.objects.filter(user=user, is_active=True)
    print(f"\n📋 Business Memberships ({memberships.count()}):")
    
    for membership in memberships:
        print(f"\n   Business: {membership.business.name}")
        print(f"   Slug: {membership.business.slug}")
        print(f"   Role: {membership.role}")
        print(f"   Is Owner: {membership.role == 'owner'}")
        
        # Check for pending support requests
        pending_requests = SupportAccessRequest.objects.filter(
            business=membership.business,
            status='pending'
        )
        print(f"   Pending Support Requests: {pending_requests.count()}")
        
        for req in pending_requests:
            print(f"      - From: {req.requested_by.username}")
            print(f"        Reason: {req.reason[:50]}...")
            print(f"        Requested: {req.requested_at}")
        
        # URL to access support requests
        print(f"   Support Access URL: /b/{membership.business.slug}/support-access/")
    
    if not memberships.exists():
        print("   ⚠️  No active business memberships found")
        
except User.DoesNotExist:
    print(f"❌ User '{username}' not found")
