"""
Tests for Front Office & Back Office Separation, Terminal Binding, PIN Authentication, and Audit Trail.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
import uuid

from pos.models import (
    Business, Branch, BusinessMembership, UserProfile,
    POSTerminal, POSSession, PINLoginAuditLog, ZReport
)


class FrontBackOfficeSegregationTest(TestCase):
    def setUp(self):
        self.client = Client()
        from django.core.cache import cache
        cache.clear()
        
        # 1. Admin / Owner User
        self.admin_user = User.objects.create_user(
            username="admin_user",
            password="adminpassword123",
            first_name="Admin",
            last_name="User"
        )

        # Use or Create Business & Default Branch
        self.business = Business.objects.first()
        if not self.business:
            self.business = Business.objects.create(
                name="Alpha Supermarket",
                slug="alpha-supermarket",
                owner=self.admin_user,
                is_active=True
            )
        else:
            self.business.owner = self.admin_user
            self.business.save()

        self.branch = Branch.objects.filter(business=self.business, is_default=True).first()
        if not self.branch:
            self.branch = Branch.objects.create(
                business=self.business,
                name="Main Branch",
                code="MAIN",
                is_default=True,
                is_active=True
            )
        
        # Create Terminal
        self.terminal = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch,
            name="Till 1",
            terminal_code="TILL-01",
            device_token="test-device-token-12345",
            is_active=True
        )
        
        # 1. Admin Membership
        self.admin_membership = BusinessMembership.objects.create(
            business=self.business,
            user=self.admin_user,
            role="admin",
            is_active=True
        )
        
        # 2. Manager User
        self.manager_user = User.objects.create_user(
            username="manager_user",
            password="managerpassword123",
            first_name="Manager",
            last_name="User"
        )
        self.manager_membership = BusinessMembership.objects.create(
            business=self.business,
            user=self.manager_user,
            role="manager",
            is_active=True
        )
        
        # 3. Cashier User with PIN
        self.cashier_user = User.objects.create_user(
            username="cashier_jane",
            password="cashierpassword123",
            first_name="Jane",
            last_name="Doe"
        )
        self.cashier_membership = BusinessMembership.objects.create(
            business=self.business,
            user=self.cashier_user,
            role="cashier",
            is_active=True
        )
        self.cashier_profile, _ = UserProfile.objects.get_or_create(user=self.cashier_user)
        self.cashier_profile.set_pin("1234", business=self.business)
        self.cashier_profile.employee_id = "EMP-001"
        self.cashier_profile.save()

    def test_cashier_pin_login_success(self):
        """Test cashier can log into Front Office using valid PIN on registered terminal"""
        # Set terminal cookie
        self.client.cookies['pos_terminal_token'] = self.terminal.device_token
        
        response = self.client.post(reverse('terminal_pin_login'), {
            'employee_id': 'EMP-001',
            'pin': '1234',
            'device_token': self.terminal.device_token
        })
        # If no active session, redirects to open shift; if active session, to pos_screen
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/pos/session/open/') or response.url.endswith('/pos/'))
        
        # Check audit log recorded
        log = PINLoginAuditLog.objects.filter(employee_id='EMP-001', status='success').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.terminal, self.terminal)

    def test_cashier_direct_pin_only_login(self):
        """Test cashier can log in by entering ONLY their unique PIN (without typing employee ID)"""
        self.client.cookies['pos_terminal_token'] = self.terminal.device_token
        
        response = self.client.post(reverse('terminal_pin_login'), {
            'pin': '1234',
            'device_token': self.terminal.device_token
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify authenticated user is cashier_user
        self.assertEqual(int(self.client.session['_auth_user_id']), self.cashier_user.id)
        
        # Verify success audit log
        log = PINLoginAuditLog.objects.filter(user=self.cashier_user, status='success').first()
        self.assertIsNotNone(log)

    def test_unique_pin_validation_prevents_duplicates(self):
        """Test that assigning an existing PIN to another cashier in the same business raises ValidationError"""
        from django.core.exceptions import ValidationError
        
        cashier2 = User.objects.create_user(username="cashier2", password="password123")
        BusinessMembership.objects.create(business=self.business, user=cashier2, role="cashier", is_active=True)
        profile2, _ = UserProfile.objects.get_or_create(user=cashier2)
        
        # Attempting to assign same PIN "1234" should raise ValidationError
        with self.assertRaises(ValidationError):
            profile2.set_pin("1234", business=self.business)
        
        # Assigning unique PIN "5678" should succeed
        profile2.set_pin("5678", business=self.business)
        self.assertTrue(profile2.has_pin_set)
        self.assertTrue(profile2.check_pin("5678"))

    def test_cashier_pin_login_failure_and_lockout(self):
        """Test failed PIN attempts increment failure count and lock out after max attempts"""
        self.client.cookies['pos_terminal_token'] = self.terminal.device_token
        
        # Attempts 1 to 4 wrong PIN
        for i in range(4):
            self.client.post(reverse('terminal_pin_login'), {
                'employee_id': 'EMP-001',
                'pin': '9999',
                'device_token': self.terminal.device_token
            })
        
        self.assertEqual(PINLoginAuditLog.objects.filter(status='failed_pin').count(), 4)
        
        # Attempt 5 wrong PIN -> should trigger lockout
        response = self.client.post(reverse('terminal_pin_login'), {
            'employee_id': 'EMP-001',
            'pin': '9999',
            'device_token': self.terminal.device_token
        })
        self.assertEqual(response.status_code, 200)
        
        from django.core.cache import cache
        lockout_until = cache.get(f'pin_lockout_{self.cashier_user.id}')
        self.assertIsNotNone(lockout_until)
        self.assertTrue(PINLoginAuditLog.objects.filter(status='locked_out').exists())

    def test_cashier_blocked_from_back_office_server_side(self):
        """Test Cashiers are strictly blocked from all Back Office views (Dashboard, Products, etc.)"""
        self.client.force_login(self.cashier_user)
        
        # Attempt to access Back Office Dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/pos/', response.url)
        
        # Attempt to access Products list
        response = self.client.get(reverse('product_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/pos/', response.url)
        
        # Attempt to access User Management
        response = self.client.get(reverse('user_management_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/pos/', response.url)

    def test_admin_has_full_access(self):
        """Test Admin has access to Back Office Dashboard, Terminals, and Front Office POS"""
        self.client.force_login(self.admin_user)
        
        # Back office dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Terminal management
        response = self.client.get(reverse('terminal_list'))
        self.assertEqual(response.status_code, 200)
        
        # Front office POS with active session
        POSSession.objects.create(
            business=self.business,
            branch=self.branch,
            opened_by=self.admin_user,
            status='open',
            opening_cash=Decimal('0.00')
        )
        response = self.client.get(reverse('pos_screen'))
        self.assertEqual(response.status_code, 200)

    def test_terminal_session_lifecycle(self):
        """Test opening and closing cashier shift session and generating Z-Report"""
        self.client.force_login(self.cashier_user)
        self.client.cookies['pos_terminal_token'] = self.terminal.device_token
        
        # Open Shift
        response = self.client.post(reverse('terminal_session_open'), {
            'opening_cash': '1000.00',
            'notes': 'Morning shift float'
        })
        self.assertEqual(response.status_code, 302)
        
        session = POSSession.objects.filter(cashier=self.cashier_user, status='open').first()
        self.assertIsNotNone(session)
        self.assertEqual(session.opening_cash, Decimal('1000.00'))
        
        # Close Shift
        response = self.client.post(reverse('terminal_session_close'), {
            'closing_cash': '1500.00',
            'closing_notes': 'End of shift'
        })
        self.assertEqual(response.status_code, 302)
        
        session.refresh_from_db()
        self.assertEqual(session.status, 'closed')
        self.assertEqual(session.closing_cash, Decimal('1500.00'))
        
        # Verify Z-Report created
        zreport = ZReport.objects.filter(session=session).first()
        self.assertIsNotNone(zreport)
