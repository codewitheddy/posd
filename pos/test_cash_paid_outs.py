"""
Comprehensive Test Suite for Cash Paid-Out / Till Expenses Module
Covers:
1. Real-time drawer cash math: Float + Cash Sales - Pickups - Paid-Outs - Refunds.
2. Category threshold validation & supervisor PIN authorization rules.
3. Post-payout receipt attachment and automatic GL Expense posting.
4. Informal vendor manager exception note sign-off.
5. Payout reversal transaction and cash return to drawer.
6. Z-Report financial segregation of paid-outs vs pickups and expected cash snapshot.
7. Full HTTP views, JSON APIs, and 4 audit reports.
"""

from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from pos.models import (
    Business, BusinessMembership, Branch, POSTerminal, POSSession,
    PaymentMethod, Sale, SalePayment, UserProfile,
    ExpenseCategory, Expense, CashPickup, CashPaidOut, BankingAuditLog
)
from pos.cash_paid_out_services import CashPaidOutService
from pos.cash_pickup_services import CashPickupService
from pos.zreport_service import ZReportService


class CashPaidOutModuleTests(TestCase):
    def setUp(self):
        # 1. Users
        self.owner = User.objects.create_user(username='biz_owner', password='OwnerPassword123!')
        self.manager = User.objects.create_user(username='biz_manager', password='ManagerPassword123!')
        self.cashier = User.objects.create_user(username='biz_cashier', password='CashierPassword123!')

        # 2. Business & Memberships
        self.business = Business.objects.create(
            name="Apex Retail Supermarkets",
            slug="apex-supermarket",
            owner=self.owner
        )

        BusinessMembership.objects.create(
            user=self.owner, business=self.business, role='owner', is_active=True
        )
        BusinessMembership.objects.create(
            user=self.manager, business=self.business, role='manager', is_active=True,
            permissions=['can_create_sale', 'can_request_cash_pickup', 'can_authorize_cash_pickup',
                         'can_request_cash_paid_out', 'can_authorize_cash_paid_out', 'can_manage_paid_out_receipts']
        )
        BusinessMembership.objects.create(
            user=self.cashier, business=self.business, role='cashier', is_active=True,
            permissions=['can_create_sale', 'can_request_cash_pickup', 'can_request_cash_paid_out',
                         'can_manage_paid_out_receipts']
        )

        # 3. Configure Manager PIN
        manager_profile, _ = UserProfile.objects.get_or_create(user=self.manager)
        manager_profile.set_pin('8899')

        cashier_profile, _ = UserProfile.objects.get_or_create(user=self.cashier)
        cashier_profile.set_pin('1234')

        # 4. Branch, Terminal, and POS Session
        self.branch = Branch.objects.create(
            business=self.business,
            name="Downtown Store",
            code="DTN-01"
        )
        self.terminal = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch,
            name="Lane 01",
            terminal_code="TILL-01"
        )
        self.session = POSSession.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal,
            opened_by=self.cashier,
            cashier=self.cashier,
            opening_cash=Decimal('3000.00'),
            status='open'
        )

        # 5. Payment Methods
        self.cash_pm, _ = PaymentMethod.objects.get_or_create(
            business=self.business, code='CASH', defaults={'name': 'Cash', 'is_active': True}
        )

        # 6. Expense Categories
        self.cat_fuel = ExpenseCategory.objects.create(
            business=self.business,
            name="Delivery Fuel",
            chart_of_accounts_code="5100",
            requires_manager_approval_above=Decimal('1000.00'),
            monthly_budget_cap=Decimal('20000.00')
        )
        self.cat_tea = ExpenseCategory.objects.create(
            business=self.business,
            name="Staff Welfare",
            chart_of_accounts_code="5200",
            requires_manager_approval_above=Decimal('500.00'),
            monthly_budget_cap=Decimal('10000.00')
        )

        self.client = Client()

    def test_drawer_cash_live_aggregation_with_paid_outs(self):
        """Test running drawer cash calculation: Float + Cash Sales - Pickups - Paid-Outs."""
        # Cash Sale: KES 10,000
        sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal,
            session=self.session,
            cashier=self.cashier,
            subtotal=Decimal('10000.00'),
            vat_amount=Decimal('0.00'),
            total=Decimal('10000.00'),
            amount_paid=Decimal('10000.00'),
            date=timezone.now()
        )
        SalePayment.objects.create(
            business=self.business,
            sale=sale,
            payment_method=self.cash_pm,
            amount=Decimal('10000.00')
        )

        # 1. Cash Pickup of KES 4,000
        CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='8899',
            amount=Decimal('4000.00'),
            pickup_reference='BAG-PO-01',
            session=self.session
        )

        # 2. Before Paid-Out: Drawer has 3,000 + 10,000 - 4,000 = 9,000
        summary1 = CashPaidOutService.get_drawer_cash_summary(self.business, self.session)
        self.assertEqual(summary1['current_drawer_cash'], Decimal('9000.00'))

        # 3. Record Paid-Out of KES 1,500 (authorized by manager PIN)
        pout = CashPaidOutService.record_paid_out(
            business=self.business,
            requested_by=self.cashier,
            category=self.cat_fuel,
            amount=Decimal('1500.00'),
            payee="Total Station",
            description="Fuel for delivery bike",
            supervisor_credential='8899',
            session=self.session
        )
        self.assertTrue(pout.paid_out_number.startswith('POUT-'))
        self.assertEqual(pout.status, 'paid_pending_receipt')

        # 4. After Paid-Out: Drawer has 9,000 - 1,500 = 7,500
        summary2 = CashPaidOutService.get_drawer_cash_summary(self.business, self.session)
        self.assertEqual(summary2['total_paid_outs'], Decimal('1500.00'))
        self.assertEqual(summary2['current_drawer_cash'], Decimal('7500.00'))
        self.assertEqual(summary2['pending_receipts_count'], 1)

    def test_threshold_and_dual_custody_authorization(self):
        """Test auto-approval under category threshold vs mandatory manager PIN above threshold."""
        # 1. Under threshold: KES 300 for Staff Welfare (Threshold: 500) -> Auto-approved by cashier
        p1 = CashPaidOutService.record_paid_out(
            business=self.business,
            requested_by=self.cashier,
            category=self.cat_tea,
            amount=Decimal('300.00'),
            payee="Local Dairy",
            description="Milk for staff morning tea",
            session=self.session
        )
        self.assertEqual(p1.authorized_by, self.cashier)
        self.assertEqual(p1.status, 'paid_pending_receipt')

        # 2. Above threshold: KES 1,200 for Delivery Fuel (Threshold: 1000) without supervisor credential -> Rejected
        with self.assertRaises(Exception):
            CashPaidOutService.record_paid_out(
                business=self.business,
                requested_by=self.cashier,
                category=self.cat_fuel,
                amount=Decimal('1200.00'),
                payee="Rubis Station",
                description="Fuel for delivery van",
                supervisor_credential='',  # Missing PIN
                session=self.session
            )

        # 3. Cashier self-authorizing with own PIN above threshold -> Rejected
        with self.assertRaises(Exception):
            CashPaidOutService.record_paid_out(
                business=self.business,
                requested_by=self.cashier,
                category=self.cat_fuel,
                amount=Decimal('1200.00'),
                payee="Rubis Station",
                description="Fuel for delivery van",
                supervisor_credential='1234',  # Cashier's PIN
                session=self.session
            )

        # 4. Above threshold with valid Manager PIN -> Succeeded
        p2 = CashPaidOutService.record_paid_out(
            business=self.business,
            requested_by=self.cashier,
            category=self.cat_fuel,
            amount=Decimal('1200.00'),
            payee="Rubis Station",
            description="Fuel for delivery van",
            supervisor_credential='8899',  # Manager PIN
            session=self.session
        )
        self.assertEqual(p2.authorized_by, self.manager)
        self.assertEqual(p2.status, 'paid_pending_receipt')

    def test_receipt_attachment_and_gl_expense_posting(self):
        """Test attaching receipt marks status confirmed and automatically posts GL Expense entry."""
        # Create payout
        pout = CashPaidOutService.record_paid_out(
            business=self.business,
            requested_by=self.cashier,
            category=self.cat_fuel,
            amount=Decimal('800.00'),
            payee="Shell Petrol",
            description="Fuel for generator",
            session=self.session
        )
        self.assertIsNone(pout.expense_entry)
        self.assertEqual(pout.status, 'paid_pending_receipt')

        # Attach receipt
        updated_pout = CashPaidOutService.attach_receipt(
            paid_out=pout,
            user=self.cashier,
            receipt_reference="INV-SHELL-9988",
            notes="Checked by cashier"
        )
        self.assertEqual(updated_pout.status, 'confirmed')
        self.assertIsNotNone(updated_pout.receipt_received_at)
        self.assertIsNotNone(updated_pout.expense_entry)

        # Check GL Expense entry properties
        expense = updated_pout.expense_entry
        self.assertEqual(expense.amount, Decimal('800.00'))
        self.assertEqual(expense.category, self.cat_fuel)
        self.assertEqual(expense.reference_number, "INV-SHELL-9988")
        self.assertEqual(expense.payment_method, 'cash')

    def test_informal_vendor_receipt_exception(self):
        """Test manager exception note for informal vendors confirms payout and posts to GL."""
        pout = CashPaidOutService.record_paid_out(
            business=self.business,
            requested_by=self.cashier,
            category=self.cat_tea,
            amount=Decimal('400.00'),
            payee="Kiosk Mama Jane",
            description="Fresh lemons and ginger for staff",
            session=self.session
        )

        updated_pout = CashPaidOutService.grant_receipt_exception(
            paid_out=pout,
            supervisor_user=self.manager,
            exception_reason="Casual local vendor without receipt book. Cash verified by manager."
        )

        self.assertEqual(updated_pout.status, 'confirmed')
        self.assertTrue(updated_pout.has_receipt_exception)
        self.assertEqual(updated_pout.exception_approved_by, self.manager)
        self.assertIsNotNone(updated_pout.expense_entry)

    def test_paid_out_reversal_and_cash_return(self):
        """Test reversing a payout returns cash to drawer and deletes linked GL Expense."""
        pout = CashPaidOutService.record_paid_out(
            business=self.business,
            requested_by=self.cashier,
            category=self.cat_fuel,
            amount=Decimal('600.00'),
            payee="Ola Energy",
            description="Fuel container",
            session=self.session
        )
        CashPaidOutService.attach_receipt(pout, self.cashier, "OLA-11")
        pout.refresh_from_db()
        self.assertIsNotNone(pout.expense_entry)

        # Drawer before reversal: 3,000 - 600 = 2,400
        s1 = CashPaidOutService.get_drawer_cash_summary(self.business, self.session)
        self.assertEqual(s1['current_drawer_cash'], Decimal('2400.00'))

        # Reverse payout
        reversed_pout = CashPaidOutService.reverse_paid_out(
            paid_out=pout,
            user=self.cashier,
            supervisor_credential='8899',
            reversal_reason="Purchase cancelled because station was out of fuel. Cash returned."
        )

        self.assertEqual(reversed_pout.status, 'reversed')
        self.assertTrue(reversed_pout.is_reversed)
        self.assertIsNone(reversed_pout.expense_entry)

        # Drawer after reversal: 2,400 + 600 = 3,000
        s2 = CashPaidOutService.get_drawer_cash_summary(self.business, self.session)
        self.assertEqual(s2['current_drawer_cash'], Decimal('3000.00'))

    def test_zreport_session_closing_with_paid_outs_and_pickups(self):
        """Test Z-Report correctly segregates paid-outs from pickups and computes exact expected cash."""
        # Cash Sale: KES 8,000
        sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal,
            session=self.session,
            cashier=self.cashier,
            subtotal=Decimal('8000.00'),
            vat_amount=Decimal('0.00'),
            total=Decimal('8000.00'),
            amount_paid=Decimal('8000.00'),
            date=timezone.now()
        )
        SalePayment.objects.create(
            business=self.business,
            sale=sale,
            payment_method=self.cash_pm,
            amount=Decimal('8000.00')
        )

        # Pickup: KES 4,000
        CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='8899',
            amount=Decimal('4000.00'),
            pickup_reference='BAG-ZR-P01',
            session=self.session
        )

        # Paid-Out: KES 1,000
        CashPaidOutService.record_paid_out(
            business=self.business,
            requested_by=self.cashier,
            category=self.cat_fuel,
            amount=Decimal('1000.00'),
            payee="Total CBD",
            description="Delivery fuel",
            session=self.session
        )

        # Expected Drawer Cash = Float (3,000) + Sale (8,000) - Pickup (4,000) - Paid-Out (1,000) = 6,000
        zreport = ZReportService.close_session(
            session_id=self.session.id,
            user=self.manager,
            closing_cash=Decimal('6000.00')
        )

        self.assertIsNotNone(zreport)
        report_data = zreport.report_data
        cash_mgmt = report_data['cash_management']

        self.assertEqual(cash_mgmt['opening_float'], 3000.0)
        self.assertEqual(cash_mgmt['cash_sales'], 8000.0)
        self.assertEqual(cash_mgmt['total_cash_pickups'], 4000.0)
        self.assertEqual(cash_mgmt['total_cash_paid_outs'], 1000.0)
        self.assertEqual(cash_mgmt['expected_cash'], 6000.0)
        self.assertEqual(cash_mgmt['actual_cash_counted'], 6000.0)
        self.assertEqual(cash_mgmt['difference'], 0.0)
        self.assertEqual(len(report_data['cash_pickups']), 1)
        self.assertEqual(len(report_data['cash_paid_outs']), 1)
        self.assertEqual(report_data['cash_paid_outs'][0]['payee'], 'Total CBD')

    def test_http_views_and_reports_endpoints(self):
        """Test HTTP GET & POST endpoints for paid-outs ledger, create API, and 4 audit reports."""
        # 1. Paid-Outs Ledger View
        self.client.force_login(self.manager)
        res_list = self.client.get(reverse('cash_paid_out_list', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_list.status_code, 200)

        # 2. Drawer status API
        res_drawer = self.client.get(reverse('cash_paid_out_drawer_status', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_drawer.status_code, 200)
        drawer_json = res_drawer.json()
        self.assertTrue(drawer_json['success'])

        # 3. Create Paid-Out POST (Cashier session with Manager PIN authorization for high-value)
        self.client.force_login(self.cashier)
        payload = {
            'amount': '1500.00',
            'category_id': self.cat_fuel.id,
            'payee': 'Express Courier Services',
            'description': 'Customer same-day parcel delivery',
            'supervisor_credential': '8899',  # Manager PIN
            'session_id': self.session.id,
        }
        res_create = self.client.post(
            reverse('cash_paid_out_create', kwargs={'slug': self.business.slug}),
            data=payload,
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_create.status_code, 200)
        create_data = res_create.json()
        self.assertTrue(create_data['success'])
        paid_out_id = create_data['paid_out']['id']

        # 4. Detail view
        self.client.force_login(self.manager)
        res_detail = self.client.get(reverse('cash_paid_out_detail', kwargs={'slug': self.business.slug, 'paid_out_id': paid_out_id}))
        self.assertEqual(res_detail.status_code, 200)

        # 5. Slip print view
        res_print = self.client.get(reverse('cash_paid_out_slip_print', kwargs={'slug': self.business.slug, 'paid_out_id': paid_out_id}))
        self.assertEqual(res_print.status_code, 200)

        # 6. Report: Paid-Outs Log
        res_log = self.client.get(reverse('report_paid_outs_log', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_log.status_code, 200)

        # 7. Report: Missing Receipts
        res_missing = self.client.get(reverse('report_missing_receipts', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_missing.status_code, 200)

        # 8. Report: Category Summary
        res_cat = self.client.get(reverse('report_expense_category_summary', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_cat.status_code, 200)

        # 9. Report: Approval Audit
        res_audit = self.client.get(reverse('report_paid_out_approval_audit', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_audit.status_code, 200)
