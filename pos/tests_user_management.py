"""
Unit tests for User Management Enhancements.
Covers PIN management, granular permissions, and discount ceiling guard.

Run with:
    python manage.py test pos.tests_user_management
"""
from decimal import Decimal

import django.test
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from pos.models import (
    Business,
    Branch,
    BusinessMembership,
    UserProfile,
    PERMISSION_CODES,
    DEFAULT_PERMISSIONS,
    DEFAULT_MAX_DISCOUNT,
    POSTerminal,
    POSSession,
    Sale,
    Product,
    Category,
)
from pos.views import check_discount_ceiling
from pos.user_management_views import user_create_view, user_edit_view

from hr.models import Employee


class UserManagementTestCase(django.test.TestCase):
    """Base test case with a User, Business, and membership helper."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            owner=self.user,
        )

    def _make_membership(self, role='cashier', user=None, **kwargs):
        """Create a BusinessMembership for the given role."""
        if user is None:
            user = self.user
        return BusinessMembership.objects.create(
            user=user,
            business=self.business,
            role=role,
            **kwargs,
        )

    # ── PIN tests ─────────────────────────────────────────────────────────────

    def test_set_pin_valid(self):
        """Setting a valid 4-digit PIN marks has_pin_set True and check_pin succeeds."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.set_pin('1234')
        self.assertTrue(profile.has_pin_set)
        self.assertTrue(profile.check_pin('1234'))

    def test_set_pin_invalid_too_short(self):
        """PIN '123' (3 digits) raises ValidationError."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        with self.assertRaises(ValidationError):
            profile.set_pin('123')

    def test_set_pin_invalid_too_long(self):
        """PIN '1234567' (7 digits) raises ValidationError."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        with self.assertRaises(ValidationError):
            profile.set_pin('1234567')

    def test_set_pin_invalid_non_digit(self):
        """PIN '12ab' (non-digit chars) raises ValidationError."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        with self.assertRaises(ValidationError):
            profile.set_pin('12ab')

    def test_set_pin_invalid_empty(self):
        """Empty PIN raises ValidationError."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        with self.assertRaises(ValidationError):
            profile.set_pin('')

    def test_clear_pin(self):
        """After set_pin then clear_pin, has_pin_set is False."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.set_pin('5678')
        self.assertTrue(profile.has_pin_set)
        profile.clear_pin()
        self.assertFalse(profile.has_pin_set)

    # ── Permission / role tests ───────────────────────────────────────────────

    def test_default_permissions_all_roles(self):
        """Each role gets the expected default permissions and max_discount_pct."""
        roles = list(DEFAULT_PERMISSIONS.keys())
        users = {}
        for role in roles:
            u = User.objects.create_user(username=f'user_{role}', password='pass')
            users[role] = u

        for role in roles:
            membership = BusinessMembership.objects.create(
                user=users[role],
                business=self.business,
                role=role,
            )
            self.assertEqual(
                sorted(membership.permissions),
                sorted(DEFAULT_PERMISSIONS[role]),
                msg=f"permissions mismatch for role '{role}'",
            )
            self.assertEqual(
                membership.max_discount_pct,
                DEFAULT_MAX_DISCOUNT[role],
                msg=f"max_discount_pct mismatch for role '{role}'",
            )

    def test_role_change_resets_permissions(self):
        """Changing a membership's role replaces permissions with the new role's defaults."""
        membership = self._make_membership(role='cashier')
        # cashier has limited permissions
        self.assertEqual(sorted(membership.permissions), sorted(DEFAULT_PERMISSIONS['cashier']))

        membership.role = 'manager'
        membership.save()

        membership.refresh_from_db()
        self.assertEqual(sorted(membership.permissions), sorted(DEFAULT_PERMISSIONS['manager']))
        self.assertEqual(membership.max_discount_pct, DEFAULT_MAX_DISCOUNT['manager'])

    def test_has_permission_inactive(self):
        """An inactive membership returns False for every permission code."""
        membership = self._make_membership(role='owner', is_active=False)
        for code in PERMISSION_CODES:
            self.assertFalse(
                membership.has_permission(code),
                msg=f"Expected False for '{code}' on inactive membership",
            )

    def test_has_permission_granular(self):
        """Active membership with specific permissions returns correct True/False."""
        membership = self._make_membership(role='cashier')
        # cashier gets: can_apply_discount, can_refund_sale, can_create_sale, can_print_receipt, can_view_reports
        self.assertTrue(membership.has_permission('can_apply_discount'))
        self.assertTrue(membership.has_permission('can_refund_sale'))
        self.assertTrue(membership.has_permission('can_create_sale'))
        self.assertTrue(membership.has_permission('can_print_receipt'))
        self.assertTrue(membership.has_permission('can_view_reports'))
        self.assertFalse(membership.has_permission('can_manage_users'))
        self.assertFalse(membership.has_permission('can_void_sale'))

    def test_cashier_can_print_receipt_with_empty_or_legacy_permissions(self):
        """Cashier with empty or legacy permissions can still print receipts."""
        membership = self._make_membership(role='cashier')
        membership.permissions = []
        membership.save(update_fields=['permissions'])
        self.assertTrue(membership.has_permission('can_print_receipt'))

        # Legacy permissions list missing can_print_receipt
        membership.permissions = ['can_apply_discount', 'can_refund_sale']
        membership.save(update_fields=['permissions'])
        self.assertTrue(membership.has_permission('can_print_receipt'))

    # ── Discount guard tests ──────────────────────────────────────────────────

    def test_discount_guard_allows_within_ceiling(self):
        """10% discount with 20% ceiling is allowed."""
        membership = self._make_membership(role='cashier')
        # cashier ceiling is 20%
        allowed, _, _ = check_discount_ceiling(membership, 'percentage', Decimal('10'), Decimal('100'))
        self.assertTrue(allowed)

    def test_discount_guard_blocks_over_ceiling(self):
        """30% discount with 20% ceiling and no override is blocked."""
        membership = self._make_membership(role='cashier')
        # cashier ceiling is 20%, no can_exceed_max_discount
        allowed, _, _ = check_discount_ceiling(membership, 'percentage', Decimal('30'), Decimal('100'))
        self.assertFalse(allowed)

    def test_discount_guard_allows_with_override(self):
        """30% discount with 20% ceiling is allowed when membership has can_exceed_max_discount."""
        membership = self._make_membership(role='cashier')
        # Manually grant override permission
        membership.permissions = list(membership.permissions) + ['can_exceed_max_discount']
        membership.save(update_fields=['permissions'])

        allowed, _, _ = check_discount_ceiling(membership, 'percentage', Decimal('30'), Decimal('100'))
        self.assertTrue(allowed)

    def test_discount_guard_flat_conversion(self):
        """Flat discount of 10 on a 100 total (=10%) is allowed with 20% ceiling."""
        membership = self._make_membership(role='cashier')
        # 10 / 100 * 100 = 10% effective, ceiling 20%
        allowed, effective_pct, _ = check_discount_ceiling(membership, 'flat', Decimal('10'), Decimal('100'))
        self.assertTrue(allowed)
        self.assertAlmostEqual(float(effective_pct), 10.0, places=4)


class UserManagementHRAutoProvisioningTestCase(django.test.TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.owner = User.objects.create_user(username='owner-user', password='pass123!')
        self.business = Business.objects.create(
            name='HR Sync Biz',
            slug='hr-sync-biz',
            owner=self.owner,
        )
        self.owner_membership = BusinessMembership.objects.create(
            user=self.owner,
            business=self.business,
            role='owner',
            is_active=True,
        )
        self.branch = Branch.objects.create(
            business=self.business,
            name='Main Branch',
            address='123 Main Street',
            is_default=True,
        )

    def _build_request(self, method, path, data=None, user=None):
        request_factory = getattr(self.factory, method.lower())
        request = request_factory(path, data=data or {})
        request.user = user or self.owner
        request.business = self.business
        request.business_membership = self.owner_membership

        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        setattr(request, '_messages', FallbackStorage(request))
        return request

    def test_staff_user_creation_auto_registers_employee(self):
        request = self._build_request(
            'post',
            f'/b/{self.business.slug}/settings/users/create/',
            data={
                'username': 'cashier-sync',
                'password': 'pass123!',
                'password_confirm': 'pass123!',
                'role': 'cashier',
                'first_name': 'Cash',
                'last_name': 'User',
                'branch_id': str(self.branch.id),
            },
        )

        response = user_create_view(request, slug=self.business.slug)

        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username='cashier-sync')
        employee = Employee.objects.get(user_account=created_user, business=self.business)
        created_user.refresh_from_db()
        self.assertEqual(employee.branch, self.branch)
        self.assertEqual(employee.job_title, 'Cashier')
        self.assertEqual(created_user.profile.employee_id, employee.staff_code)

    def test_viewer_creation_does_not_auto_register_employee(self):
        request = self._build_request(
            'post',
            f'/b/{self.business.slug}/settings/users/create/',
            data={
                'username': 'viewer-sync',
                'password': 'pass123!',
                'password_confirm': 'pass123!',
                'role': 'viewer',
            },
        )

        response = user_create_view(request, slug=self.business.slug)

        self.assertEqual(response.status_code, 302)
        created_user = User.objects.get(username='viewer-sync')
        self.assertFalse(Employee.objects.filter(user_account=created_user, business=self.business).exists())

    def test_editing_staff_user_backfills_missing_employee_profile(self):
        user = User.objects.create_user(username='legacy-cashier', password='pass123!')
        BusinessMembership.objects.create(
            user=user,
            business=self.business,
            role='cashier',
            is_active=True,
        )
        UserProfile.objects.get_or_create(user=user)

        request = self._build_request(
            'post',
            f'/b/{self.business.slug}/settings/users/{user.id}/edit/',
            data={
                'first_name': 'Legacy',
                'last_name': 'Cashier',
                'email': '',
                'role': 'cashier',
                'phone': '',
                'employee_id': '',
                'branch_id': str(self.branch.id),
                'is_active': 'on',
            },
        )

        response = user_edit_view(request, slug=self.business.slug, pk=user.id)

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        employee = Employee.objects.get(user_account=user, business=self.business)
        self.assertEqual(employee.branch, self.branch)
        self.assertEqual(user.profile.employee_id, employee.staff_code)


class CashierReceiptPrintingTestCase(django.test.TestCase):
    """Test receipt printing view access for cashiers."""

    def setUp(self):
        from pos.models import Sale, Product, Category, PaymentMethod
        self.owner = User.objects.create_user(username='owner_user', password='password123')
        self.cashier = User.objects.create_user(username='cashier_user', password='password123')
        self.business = Business.objects.create(
            name='Receipt Biz',
            slug='receipt-biz',
            owner=self.owner,
        )
        self.owner_membership = BusinessMembership.objects.create(
            user=self.owner,
            business=self.business,
            role='owner',
            is_active=True,
        )
        self.cashier_membership = BusinessMembership.objects.create(
            user=self.cashier,
            business=self.business,
            role='cashier',
            is_active=True,
        )
        self.category = Category.objects.create(name='General', business=self.business)
        self.product = Product.objects.create(
            name='Test Product',
            unit_price=Decimal('100.00'),
            cost_price=Decimal('70.00'),
            category=self.category,
            business=self.business,
        )
        self.sale = Sale.objects.create(
            business=self.business,
            cashier=self.cashier,
            invoice_number='INV-TEST-001',
            subtotal=Decimal('100.00'),
            vat_amount=Decimal('16.00'),
            total=Decimal('116.00'),
            amount_paid=Decimal('116.00'),
        )

    def test_cashier_can_access_thermal_receipt(self):
        """Cashier can access the thermal receipt view without permission error."""
        self.client.login(username='cashier_user', password='password123')
        from django.urls import reverse
        url = reverse('thermal_receipt', kwargs={'slug': self.business.slug, 'pk': self.sale.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/receipt_thermal.html')

    def test_cashier_can_access_invoice_pdf(self):
        """Cashier can access the invoice PDF download without permission error."""
        self.client.login(username='cashier_user', password='password123')
        from django.urls import reverse
        url = reverse('invoice_pdf', kwargs={'slug': self.business.slug, 'pk': self.sale.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class BackOfficeSalesTrackingTestCase(django.test.TestCase):
    """Test Back Office admin capability to track sales filtered by Cashier, Branch, and POS Terminal."""

    def setUp(self):
        self.admin_user = User.objects.create_user(username='admin_boss', password='password123')
        self.cashier1 = User.objects.create_user(username='cashier_alice', password='password123')
        self.cashier2 = User.objects.create_user(username='cashier_bob', password='password123')

        self.business = Business.objects.create(
            name='Tracking Retail Co',
            slug='tracking-retail',
            owner=self.admin_user,
        )

        BusinessMembership.objects.create(
            business=self.business,
            user=self.admin_user,
            role='admin',
            is_active=True,
            permissions={'can_view_reports': True, 'can_manage_users': True},
        )
        BusinessMembership.objects.create(
            business=self.business,
            user=self.cashier1,
            role='cashier',
            is_active=True,
            permissions={'can_create_sale': True, 'can_print_receipt': True},
        )
        BusinessMembership.objects.create(
            business=self.business,
            user=self.cashier2,
            role='cashier',
            is_active=True,
            permissions={'can_create_sale': True, 'can_print_receipt': True},
        )

        self.branch1 = Branch.objects.create(
            business=self.business,
            name='Nairobi Central',
            code='NBI-01',
            is_active=True,
        )
        self.branch2 = Branch.objects.create(
            business=self.business,
            name='Mombasa Hub',
            code='MSA-01',
            is_active=True,
        )

        self.terminal1 = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch1,
            name='Main Register 1',
            terminal_code='TERM-NBI-01',
            device_token='token-term-nbi-01',
            ip_address='192.168.1.10',
            is_active=True,
        )
        self.terminal2 = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch2,
            name='Express Counter',
            terminal_code='TERM-MSA-01',
            device_token='token-term-msa-01',
            ip_address='192.168.2.20',
            is_active=True,
        )

        self.session1 = POSSession.objects.create(
            business=self.business,
            session_number=1,
            branch=self.branch1,
            terminal=self.terminal1,
            opened_by=self.cashier1,
            cashier=self.cashier1,
            opening_cash=Decimal('500.00'),
        )
        self.session2 = POSSession.objects.create(
            business=self.business,
            session_number=2,
            branch=self.branch2,
            terminal=self.terminal2,
            opened_by=self.cashier2,
            cashier=self.cashier2,
            opening_cash=Decimal('300.00'),
        )

        self.sale1 = Sale.objects.create(
            business=self.business,
            branch=self.branch1,
            session=self.session1,
            cashier=self.cashier1,
            invoice_number='INV-NBI-001',
            subtotal=Decimal('200.00'),
            vat_amount=Decimal('32.00'),
            total=Decimal('232.00'),
            amount_paid=Decimal('232.00'),
        )
        self.sale2 = Sale.objects.create(
            business=self.business,
            branch=self.branch2,
            session=self.session2,
            cashier=self.cashier2,
            invoice_number='INV-MSA-002',
            subtotal=Decimal('450.00'),
            vat_amount=Decimal('72.00'),
            total=Decimal('522.00'),
            amount_paid=Decimal('522.00'),
        )

    def test_admin_sales_list_filtered_by_cashier(self):
        """Admin can filter sales list by cashier."""
        self.client.login(username='admin_boss', password='password123')
        from django.urls import reverse
        url = reverse('sales_list', kwargs={'slug': self.business.slug})

        # Filter by Cashier 1
        resp1 = self.client.get(url, {'cashier': self.cashier1.id})
        self.assertEqual(resp1.status_code, 200)
        sales1 = list(resp1.context['sales'])
        self.assertIn(self.sale1, sales1)
        self.assertNotIn(self.sale2, sales1)

        # Filter by Cashier 2
        resp2 = self.client.get(url, {'cashier': self.cashier2.id})
        self.assertEqual(resp2.status_code, 200)
        sales2 = list(resp2.context['sales'])
        self.assertIn(self.sale2, sales2)
        self.assertNotIn(self.sale1, sales2)

    def test_admin_sales_list_filtered_by_branch(self):
        """Admin can filter sales list by branch."""
        self.client.login(username='admin_boss', password='password123')
        from django.urls import reverse
        url = reverse('sales_list', kwargs={'slug': self.business.slug})

        # Filter by Branch 1
        resp = self.client.get(url, {'branch': self.branch1.id})
        self.assertEqual(resp.status_code, 200)
        sales = list(resp.context['sales'])
        self.assertIn(self.sale1, sales)
        self.assertNotIn(self.sale2, sales)

    def test_admin_sales_list_filtered_by_terminal(self):
        """Admin can filter sales list by POS Terminal."""
        self.client.login(username='admin_boss', password='password123')
        from django.urls import reverse
        url = reverse('sales_list', kwargs={'slug': self.business.slug})

        # Filter by Terminal 2
        resp = self.client.get(url, {'terminal': self.terminal2.id})
        self.assertEqual(resp.status_code, 200)
        sales = list(resp.context['sales'])
        self.assertIn(self.sale2, sales)
        self.assertNotIn(self.sale1, sales)

    def test_admin_sales_report_filter_by_branch_and_terminal(self):
        """Admin can filter sales report by branch and terminal."""
        self.client.login(username='admin_boss', password='password123')
        from django.urls import reverse
        url = reverse('sales_report', kwargs={'slug': self.business.slug})

        resp = self.client.get(url, {
            'branch': self.branch1.id,
            'terminal': self.terminal1.id,
            'cashier': self.cashier1.id,
        })
        self.assertEqual(resp.status_code, 200)
        sales = list(resp.context['sales'])
        self.assertEqual(len(sales), 1)
        self.assertEqual(sales[0].id, self.sale1.id)
        self.assertEqual(resp.context['summary']['transaction_count'], 1)

    def test_admin_cashier_report_tracking(self):
        """Admin can view cashier performance breakdown and filter by branch & terminal."""
        self.client.login(username='admin_boss', password='password123')
        from django.urls import reverse
        url = reverse('cashier_report', kwargs={'slug': self.business.slug})

        # Filter by Branch 2
        resp = self.client.get(url, {'branch': self.branch2.id})
        self.assertEqual(resp.status_code, 200)
        cashier_stats = resp.context['cashier_stats']
        self.assertEqual(len(cashier_stats), 1)
        self.assertEqual(cashier_stats[0]['cashier'], self.cashier2)
        self.assertEqual(cashier_stats[0]['total_sales'], 1)
        self.assertEqual(cashier_stats[0]['total_revenue'], Decimal('522.00'))

