"""
Middleware for POS System
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.http import Http404
from django.contrib.sessions.middleware import SessionMiddleware as DjangoSessionMiddleware

User = get_user_model()


class SafeSessionMiddleware(DjangoSessionMiddleware):
    """
    Subclasses Django's SessionMiddleware to catch SessionInterrupted or UpdateError.
    If a session was deleted, expired, or invalidated in a concurrent request or long-running operation,
    this middleware gracefully recovers the session instead of crashing with a 500 error.
    """
    def process_response(self, request, response):
        try:
            return super().process_response(request, response)
        except Exception as e:
            if 'SessionInterrupted' in type(e).__name__ or 'UpdateError' in type(e).__name__:
                try:
                    if hasattr(request, 'session'):
                        request.session.cycle_key()
                        request.session.save(must_create=True)
                        response.set_cookie(
                            settings.SESSION_COOKIE_NAME,
                            request.session.session_key,
                            max_age=settings.SESSION_COOKIE_AGE,
                            domain=settings.SESSION_COOKIE_DOMAIN,
                            path=settings.SESSION_COOKIE_PATH,
                            secure=settings.SESSION_COOKIE_SECURE or False,
                            httponly=settings.SESSION_COOKIE_HTTPONLY or False,
                            samesite=settings.SESSION_COOKIE_SAMESITE,
                        )
                except Exception:
                    pass
                return response
            raise e


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


class StoreMiddleware:
    """
    Single-store middleware.
    Automatically resolves the store (Business) and attaches it to request.business and request.store.
    Also ensures BusinessMembership for authenticated users.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self._default_store = None
    
    def _get_or_create_default_store(self):
        from .models import Business, BusinessSettings
        
        # 1. Prioritize active store owned by administrator / superuser
        store = Business.objects.filter(is_active=True, owner__is_superuser=True).order_by('id').first()
        
        # 2. Look for active store with existing products/inventory
        if not store:
            store = Business.objects.filter(is_active=True, products__isnull=False).distinct().order_by('id').first()
        
        # 3. Fallback to first active store by primary key ID
        if not store:
            store = Business.objects.filter(is_active=True).order_by('id').first()
            
        if not store:
            store = Business.objects.order_by('id').first()
        
        if not store:
            # Create a default store if database is empty
            admin_user = User.objects.filter(is_superuser=True).first()
            if not admin_user:
                admin_user = User.objects.create_superuser(
                    username='admin',
                    email='admin@marid.co.ke',
                    password='adminpassword123'
                )
            
            store = Business.objects.create(
                name='Marid POS Store',
                slug='main-store',
                owner=admin_user,
                subscription_plan='paid',
                license_status='active',
                is_trial=False,
                setup_completed=True,
            )
            
            BusinessSettings.objects.get_or_create(
                business=store,
                defaults={
                    'currency': 'KES',
                    'tax_rate': 16.00,
                    'low_stock_threshold': 10,
                }
            )
            
        return store

    def __call__(self, request):
        from .models import Business, BusinessMembership, Branch
        
        store = None
        membership = None
        
        # 1. Check if URL explicitly specifies a tenant slug (e.g., /b/<slug>/...)
        if request.path.startswith('/b/'):
            parts = request.path.strip('/').split('/')
            if len(parts) >= 2 and parts[0] == 'b':
                slug = parts[1]
                store = Business.objects.filter(slug=slug, is_active=True).first()
                if not store:
                    store = Business.objects.filter(slug=slug).first()

        # 2. Check authenticated user's active memberships
        if not store and hasattr(request, 'user') and request.user.is_authenticated:
            user_memberships = list(BusinessMembership.objects.filter(
                user=request.user,
                is_active=True
            ).select_related('business'))
            
            if len(user_memberships) == 1:
                # Exactly one business membership (e.g., standard single-store or unit test)
                store = user_memberships[0].business
                membership = user_memberships[0]
            elif len(user_memberships) > 1:
                # Multiple business memberships: prioritize the primary active store
                primary_store = self._get_or_create_default_store()
                if primary_store:
                    matching_m = next((m for m in user_memberships if m.business_id == primary_store.id), None)
                    if matching_m:
                        store = primary_store
                        membership = matching_m
                if not store:
                    store = user_memberships[0].business
                    membership = user_memberships[0]

        # 3. Fallback to default primary store
        if not store:
            try:
                store = self._get_or_create_default_store()
            except Exception:
                store = None
        
        request.business = store
        request.store = store
        
        if store and hasattr(request, 'user') and request.user.is_authenticated and not membership:
            membership = BusinessMembership.objects.filter(
                user=request.user,
                business=store,
                is_active=True
            ).first()
            
            if not membership:
                is_owner = request.user.is_superuser or (getattr(store, 'owner_id', None) and request.user.id == store.owner_id)
                is_test_mode = getattr(settings, 'TEST_MODE', False)
                
                # Only auto-provision membership for superusers, the business owner, or in TEST_MODE
                if is_owner or is_test_mode:
                    default_role = 'owner' if is_owner else ('manager' if request.user.is_staff else 'cashier')
                    membership, _ = BusinessMembership.objects.get_or_create(
                        user=request.user,
                        business=store,
                        defaults={
                            'role': default_role,
                            'is_active': True
                        }
                    )
        
        request.business_membership = membership
        
        response = self.get_response(request)
        return response


# Alias for backward compatibility
TenantMiddleware = StoreMiddleware


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
    Runs after StoreMiddleware. Resolves the active Branch for the request.

    Priority:
    1. session['active_branch_id'] if set (explicit selection by user, or 'hq' / 0 for HQ)
    2. URL kwarg 'branch_id' (for branch-scoped views)
    3. User's assigned branch membership
    4. Store default branch
    5. First active branch

    Sets request.branch to a Branch instance or None (HQ context).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.branch = None
        _branch_context.value = None

        business = getattr(request, 'business', None)
        if business:
            from .models import Branch, BranchMembership
            
            # Check URL kwarg first if resolving specific branch page
            branch_id = None
            if getattr(request, 'resolver_match', None):
                branch_id = request.resolver_match.kwargs.get('branch_id')
            
            # If not in URL, check session
            if not branch_id and 'active_branch_id' in request.session:
                session_branch = request.session.get('active_branch_id')
                if session_branch in (None, 'hq', 'all', 0, '0', ''):
                    # Explicit HQ mode
                    branch_id = None
                else:
                    branch_id = session_branch

            # If still None and user is authenticated and not explicit HQ, try user's assigned branch or default
            if branch_id is None and 'active_branch_id' not in request.session:
                if request.user.is_authenticated:
                    user_bm = BranchMembership.objects.filter(
                        user=request.user,
                        branch__business=business,
                        branch__is_active=True,
                        is_active=True
                    ).select_related('branch').first()
                    if user_bm:
                        branch_id = user_bm.branch.pk

                if not branch_id:
                    default_branch = Branch.objects.filter(
                        business=business, is_default=True, is_active=True
                    ).first()
                    if default_branch:
                        branch_id = default_branch.pk
                    else:
                        first_branch = Branch.objects.filter(
                            business=business, is_active=True
                        ).first()
                        if first_branch:
                            branch_id = first_branch.pk

            if branch_id:
                try:
                    branch = Branch.objects.get(
                        pk=branch_id,
                        business=business,
                        is_active=True,
                    )
                    request.branch = branch
                    _branch_context.value = branch
                except (Branch.DoesNotExist, ValueError):
                    pass

        response = self.get_response(request)
        _branch_context.value = None
        return response


class TerminalMiddleware:
    """
    Resolves the physical POSTerminal for the request from:
    1. Cookie 'pos_terminal_token' or header 'HTTP_X_TERMINAL_TOKEN'
    2. Session 'active_terminal_id'
    3. If resolved, attaches request.terminal and resolves active pos_session
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.terminal = None
        request.pos_session = None

        business = getattr(request, 'business', None)
        if business:
            from .models import POSTerminal, POSSession
            
            token = request.COOKIES.get('pos_terminal_token') or request.META.get('HTTP_X_TERMINAL_TOKEN')
            terminal_id = request.session.get('active_terminal_id')
            
            terminal = None
            if token:
                terminal = POSTerminal.objects.filter(business=business, device_token=token, is_active=True).first()
            if not terminal and terminal_id:
                terminal = POSTerminal.objects.filter(business=business, pk=terminal_id, is_active=True).first()
            
            request.terminal = terminal
            
            # If user is authenticated, resolve active open session for user/terminal
            if request.user.is_authenticated:
                from django.db.models import Q
                session_id = request.session.get('pos_session_id')
                if session_id:
                    pos_session = POSSession.objects.filter(
                        pk=session_id, business=business, status='open'
                    ).first()
                    if pos_session:
                        request.pos_session = pos_session
                
                if not request.pos_session:
                    request.pos_session = POSSession.objects.filter(
                        business=business, status='open'
                    ).filter(
                        Q(cashier=request.user) | Q(opened_by=request.user)
                    ).order_by('-opened_at').first()

                if not request.pos_session and terminal:
                    request.pos_session = POSSession.objects.filter(
                        business=business, terminal=terminal, status='open'
                    ).order_by('-opened_at').first()

                if request.pos_session:
                    if request.session.get('pos_session_id') != request.pos_session.pk:
                        request.session['pos_session_id'] = request.pos_session.pk

        response = self.get_response(request)
        return response


class RoleAccessControlMiddleware:
    """
    Enforces Back Office vs Front Office role separation server-side.
    - Cashiers and sales-only users are strictly blocked from Back Office routes
      and redirected to /pos/ (Front Office).
    - Managers/Chief Cashiers are blocked from System Admin routes (/settings/, /backup/, /users/, /platform-admin/).
    - Excludes static, media, API, auth, front-office, receipts, and sales viewing routes.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            path = request.path
            
            # Strip multitenant prefix /b/<slug>/ to evaluate relative path
            clean_path = path
            if clean_path.startswith('/b/'):
                parts = clean_path.split('/', 3)
                if len(parts) >= 4:
                    clean_path = '/' + parts[3]
                else:
                    clean_path = '/'
            
            # Exempt routes
            is_exempt = (
                clean_path.startswith('/pos/')
                or clean_path.startswith('/api/')
                or '/api/' in clean_path
                or '/z-reports/' in clean_path
                or '/zreport/' in clean_path
                or '/finances/pickups/' in clean_path  # Allow cashiers to create pickups and view pickup slips
                or '/finances/paid-outs/' in clean_path  # Allow cashiers to create paid-outs and attach receipts
                or clean_path.startswith('/invoice/')  # Allow cashiers to view/print receipts
                or '/invoice/' in clean_path
                or clean_path.startswith('/sales/')     # Allow cashiers to view sales
                or clean_path.startswith('/reports/sales/')  # Allow cashiers to view sales reports
                or clean_path.startswith('/static/')
                or clean_path.startswith('/media/')
                or clean_path in ['/login/', '/logout/', '/password-reset/', '/terms/', '/privacy/', '/refund/', '/ping/', '/offline/', '/sw.js']
            )

            if not is_exempt:
                membership = getattr(request, 'business_membership', None)
                if membership:
                    role = membership.role
                    
                    # 1. Cashier / Sales attempting Back Office access
                    if role in ['cashier', 'sales']:
                        from django.contrib import messages
                        messages.warning(request, 'Cashier access is restricted to Front Office POS.')
                        return redirect('pos_screen')
                    
                    # 2. Manager / Chief Cashier attempting System Admin routes
                    is_admin_route = (
                        clean_path.startswith('/settings/')
                        or clean_path.startswith('/business-settings/')
                        or clean_path.startswith('/backup/')
                        or clean_path.startswith('/users/')
                        or clean_path.startswith('/platform-admin/')
                        or clean_path.startswith('/admin/')
                    )
                    if is_admin_route and role not in ['owner', 'admin']:
                        from django.contrib import messages
                        messages.error(request, 'System Administrator access required for this area.')
                        return redirect('dashboard')

        response = self.get_response(request)
        return response


