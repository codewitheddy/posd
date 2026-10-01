"""
Tests for Home Portal Screen and Authentication Gateways
Covers dual Backoffice (Admin Password) and FrontOffice (Cashier PIN) workflows.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.cache import cache

from pos.models import (
    Business, Branch, BusinessMembership, UserProfile,
    POSTerminal, POSSession, PINLoginAuditLog
)


class HomePortalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

        # Clean existing businesses for predictable test environment
        Business.objects.all().delete()

        # Create Admin User
        self.admin_user = User.objects.create_user(
            username='adminuser',
            email='portal_admin_unique@example.com',
            password='AdminPassword123!',
            is_staff=True,
            is_superuser=True
        )

        # Create Business & Branch
        self.business = Business.objects.create(
            name='Marid Flagship Store',
            slug='marid-flagship-store',
            owner=self.admin_user,
            is_active=True
        )
        self.branch = Branch.objects.create(
            business=self.business,
            name='Downtown Branch',
            code='DT01',
            is_default=True,
            is_active=True
        )

        BusinessMembership.objects.create(
            user=self.admin_user,
            business=self.business,
            role='owner',
            is_active=True
        )

        # Create Cashier User with Unique PIN (e.g. 5432)
        self.cashier_user = User.objects.create_user(
            username='cashier_sarah',
            email='sarah_jenkins_unique@example.com',
            password='CashierPass123!',
            first_name='Sarah',
            last_name='Jenkins'
        )
        BusinessMembership.objects.create(
            user=self.cashier_user,
            business=self.business,
            role='cashier',
            is_active=True
        )
        self.cashier_profile, _ = UserProfile.objects.get_or_create(user=self.cashier_user)
        self.cashier_profile.set_pin('5432')

    def tearDown(self):
        cache.clear()

    def test_home_portal_page_renders_successfully(self):
        """Verify the home screen loads with status 200 and renders cards."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/home_portal.html')
        self.assertContains(response, 'Backoffice')
        self.assertContains(response, 'FrontOffice')
        self.assertContains(response, 'Admin Password')
        self.assertContains(response, 'Cashier PIN')
        self.assertContains(response, 'Marid Flagship Store')

    def test_portal_alias_url(self):
        """Verify the /portal/ alias URL also loads the home screen."""
        response = self.client.get(reverse('home_portal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select Workspace Portal')

    def test_admin_password_login_success(self):
        """Test successful admin login via Backoffice AJAX modal."""
        response = self.client.post(
            reverse('api_backoffice_login'),
            {
                'username': 'adminuser',
                'password': 'AdminPassword123!'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('redirect_url'), reverse('dashboard'))

        # Check user is logged in
        self.assertEqual(int(self.client.session['_auth_user_id']), self.admin_user.id)

    def test_admin_password_login_with_email_success(self):
        """Test admin login using email address."""
        response = self.client.post(
            reverse('api_backoffice_login'),
            {
                'username': 'portal_admin_unique@example.com',
                'password': 'AdminPassword123!'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))

    def test_admin_password_login_failure(self):
        """Test invalid credentials response for admin login."""
        response = self.client.post(
            reverse('api_backoffice_login'),
            {
                'username': 'adminuser',
                'password': 'WrongPassword123'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('Invalid administrator', data.get('error'))

    def test_cashier_pin_login_success_unique_pin(self):
        """Test cashier login using unique PIN without specifying username."""
        response = self.client.post(
            reverse('api_cashier_pin_login'),
            {
                'pin': '5432'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('Sarah Jenkins', data.get('cashier_name'))
        self.assertEqual(data.get('redirect_url'), reverse('terminal_session_open'))

        # Check session is front office session
        self.assertEqual(int(self.client.session['_auth_user_id']), self.cashier_user.id)
        self.assertTrue(self.client.session.get('is_front_office_session'))

        # Check audit log
        audit = PINLoginAuditLog.objects.filter(user=self.cashier_user).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.status, 'success')

    def test_cashier_pin_login_with_active_shift_resumes_pos(self):
        """Test that if cashier has an open shift, redirect goes straight to pos_screen."""
        session = POSSession.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.cashier_user,
            opened_by=self.cashier_user,
            session_number=1,
            opening_cash=1000,
            status='open'
        )

        response = self.client.post(
            reverse('api_cashier_pin_login'),
            {
                'pin': '5432'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('redirect_url'), reverse('pos_screen'))

    def test_cashier_pin_login_invalid_pin(self):
        """Test cashier login failure with incorrect PIN."""
        response = self.client.post(
            reverse('api_cashier_pin_login'),
            {
                'pin': '9999'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 401)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('Invalid security PIN', data.get('error'))

        # Check failed audit log
        audit = PINLoginAuditLog.objects.filter(status='failed_pin').first()
        self.assertIsNotNone(audit)

    def test_home_portal_renders_all_four_workspace_cards(self):
        """Verify Backoffice, FrontOffice POS, HR & Payroll, and Accounting & GL cards are all rendered."""
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Backoffice Hub')
        self.assertContains(response, 'FrontOffice POS')
        self.assertContains(response, 'HR &amp; Payroll')
        self.assertContains(response, 'Accounting &amp; GL')
        self.assertContains(response, 'accountingAuthModal')
        self.assertContains(response, 'Double-Entry GL')

    def test_accounting_login_redirects_to_accounting_dashboard(self):
        """Test authentication via Accounting modal redirects to accounting_dashboard."""
        response = self.client.post(
            reverse('api_backoffice_login'),
            {
                'username': 'adminuser',
                'password': 'AdminPassword123!',
                'next': reverse('accounting_dashboard')
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('redirect_url'), reverse('accounting_dashboard'))

    def test_hr_pin_login_enter_hr_portal(self):
        """Test HR PIN login redirecting to HR Dashboard/Attendance."""
        response = self.client.post(
            reverse('api_hr_pin_login'),
            {
                'pin': '5432',
                'action': 'enter_hr'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('action'), 'enter_hr')
        self.assertIn('hr', data.get('redirect_url'))

    def test_hr_pin_clock_in_and_clock_out(self):
        """Test 1-tap clock in and clock out from the home portal modal."""
        # 1. Clock in
        response_in = self.client.post(
            reverse('api_hr_pin_login'),
            {
                'pin': '5432',
                'action': 'clock_in'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response_in.status_code, 200)
        data_in = response_in.json()
        self.assertTrue(data_in.get('success'))
        self.assertEqual(data_in.get('action'), 'clock_in')
        self.assertIn('clocked in at', data_in.get('message'))

        # 2. Clock out
        response_out = self.client.post(
            reverse('api_hr_pin_login'),
            {
                'pin': '5432',
                'action': 'clock_out'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response_out.status_code, 200)
        data_out = response_out.json()
        self.assertTrue(data_out.get('success'))
        self.assertEqual(data_out.get('action'), 'clock_out')
        self.assertIn('clocked out at', data_out.get('message'))

    def test_hr_admin_password_login_redirects_to_hr_dashboard(self):
        """Test authentication via HR modal using Admin Password redirects to hr_dashboard."""
        response = self.client.post(
            reverse('api_backoffice_login'),
            {
                'username': 'adminuser',
                'password': 'AdminPassword123!',
                'next': reverse('hr_dashboard')
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('redirect_url'), reverse('hr_dashboard'))
        self.assertIn('HR & Payroll', data.get('message'))



