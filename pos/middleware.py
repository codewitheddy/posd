"""
Middleware for POS System
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.conf import settings

User = get_user_model()


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
