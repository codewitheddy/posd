"""
Middleware for POS System
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.http import Http404

User = get_user_model()


class AuditRequestMiddleware:
    """
    Stores the current request in thread-local storage so AuditModelMixin
    can attach user/IP info to audit log entries automatically.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .models import set_audit_request
        set_audit_request(request)
        response = self.get_response(request)
        set_audit_request(None)
        return response


class TenantMiddleware:
    """
    Middleware to detect and set the current business (tenant) from URL.
    
    Extracts business slug from URL pattern /b/{slug}/... and sets:
    - request.business: The Business instance
    - request.business_membership: User's membership in this business
    
    Also verifies user has access to the requested business.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Extract business slug from URL
        business_slug = self._extract_business_slug(request.path)
        
        if business_slug:
            # Import here to avoid circular imports
            from .models import Business, BusinessMembership
            
            try:
                # Get business
                business = Business.objects.get(slug=business_slug, is_active=True)
                request.business = business
                
                # Check user access if authenticated
                if request.user.is_authenticated:
                    # Check if user has access to this business
                    try:
                        membership = BusinessMembership.objects.get(
                            user=request.user,
                            business=business,
                            is_active=True
                        )
                        request.business_membership = membership
                    except BusinessMembership.DoesNotExist:
                        # Check if user is superuser with active support access
                        if request.user.is_superuser:
                            from .models import SupportAccessRequest
                            support_access = SupportAccessRequest.objects.filter(
                                business=business,
                                requested_by=request.user,
                                status='approved'
                            ).first()
                            
                            if support_access and support_access.is_active():
                                # Grant temporary access via support request
                                request.business_membership = None
                                request.support_access = support_access
                            else:
                                # No active support access
                                from django.contrib import messages
                                messages.error(request, 'You do not have access to this business. Please request support access first.')
                                return redirect('platform_admin_dashboard')
                        else:
                            # Regular user without access
                            from django.contrib import messages
                            messages.error(request, 'You do not have access to this business. The business owner must invite you first.')
                            return redirect('business_list')
                else:
                    request.business_membership = None
                    
            except Business.DoesNotExist:
                raise Http404("Business not found")
        else:
            # No business in URL (public pages like registration, login)
            request.business = None
            request.business_membership = None
        
        response = self.get_response(request)
        return response
    
    def _extract_business_slug(self, path):
        """Extract business slug from URL path"""
        # Pattern: /b/{slug}/...
        parts = path.strip('/').split('/')
        if len(parts) >= 2 and parts[0] == 'b':
            return parts[1]
        return None


class TestModeMiddleware:
    """
    Middleware to bypass authentication in TEST_MODE.
    
    WARNING: Only use for testing/demo purposes!
    NEVER enable TEST_MODE in production with real data!
    
    When TEST_MODE=True, this middleware automatically logs in
    users as a superuser, bypassing all authentication requirements.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self._test_user = None
    
    def __call__(self, request):
        # Only activate in TEST_MODE
        if getattr(settings, 'TEST_MODE', False):
            # Check if user is not authenticated
            if isinstance(request.user, AnonymousUser) or not request.user.is_authenticated:
                # Get or create test user
                test_user = self._get_test_user()
                if test_user:
                    request.user = test_user
                    # Add a flag to indicate test mode
                    request.test_mode_active = True
        
        response = self.get_response(request)
        return response
    
    def _get_test_user(self):
        """
        Get or create a test superuser for TEST_MODE.
        Caches the user to avoid repeated database queries.
        """
        if self._test_user is None:
            try:
                # Try to get existing superuser
                self._test_user = User.objects.filter(is_superuser=True).first()
                
                # If no superuser exists, create one
                if not self._test_user:
                    print("TEST_MODE: Creating test superuser...")
                    self._test_user = User.objects.create_superuser(
                        username='testuser',
                        email='test@example.com',
                        password='testpass123',
                        first_name='Test',
                        last_name='User'
                    )
                    print(f"TEST_MODE: Test user created - {self._test_user.username}")
                else:
                    print(f"TEST_MODE: Using existing superuser - {self._test_user.username}")
                    
            except Exception as e:
                print(f"TEST_MODE Error: Could not get/create test user - {e}")
                self._test_user = None
        
        return self._test_user


# ---------------------------------------------------------------------------
# Multi-Branch middleware
# ---------------------------------------------------------------------------

import threading
_branch_context = threading.local()


def get_active_branch():
    """Return the currently active Branch from thread-local, or None."""
    return getattr(_branch_context, 'value', None)


class BranchMiddleware:
    """
    Runs after TenantMiddleware. Resolves the active Branch for the request.

    Priority:
    1. session['active_branch_id']
    2. URL kwarg 'branch_id' (for branch-scoped views)

    Sets request.branch to a Branch instance or None (HQ context).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.branch = None
        _branch_context.value = None

        business = getattr(request, 'business', None)
        if business:
            from .models import Branch
            branch_id = request.session.get('active_branch_id')
            if not branch_id and getattr(request, 'resolver_match', None):
                branch_id = request.resolver_match.kwargs.get('branch_id')
            if branch_id:
                try:
                    branch = Branch.objects.get(
                        pk=branch_id,
                        business=business,
                        is_active=True,
                    )
                    request.branch = branch
                    _branch_context.value = branch
                except Branch.DoesNotExist:
                    pass

        response = self.get_response(request)
        _branch_context.value = None
        return response
