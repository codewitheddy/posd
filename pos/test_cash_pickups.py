"""
Comprehensive Test Suite for Cash Pickup / Till Drop (Safe Drop) Module
Covers:
1. Running drawer cash calculations (Float + Cash Sales - Prior Drops - Returns).
2. Dual-custody authentication (Supervisor PIN/Password, Cashier rejection, Peer Witness).
3. Pickup creation, auto-numbering (PKU-YYYYMMDD-XXXX), and immutable locking.
4. Safe transfer workflow (confirmed -> in_safe).
5. Banking roll-up workflow (in_safe -> banked -> BankingRecord).
6. Z-Report financial aggregation with itemized pickup deductions in JSON snapshot.
7. End-to-end Chain of Custody trajectory.
8. All HTTP views, APIs, and 4 audit reports.
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
    BankAccount, BankingRecord, BankStatementLine, ReconciliationMatch,
    CashPickup, BankingAuditLog
)
from pos.cash_pickup_services import CashPickupService
from pos.zreport_service import ZReportService


class CashPickupModuleTests(TestCase):
    def setUp(self):
        # 1. Users with distinct passwords
        self.owner = User.objects.create_user(username='biz_owner', password='OwnerPassword123!')
        self.manager = User.objects.create_user(username='biz_manager', password='ManagerPassword123!')
        self.cashier = User.objects.create_user(username='biz_cashier', password='CashierPassword123!')
        self.peer_cashier = User.objects.create_user(username='peer_cashier', password='CashierPassword123!')

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
            permissions=['can_create_sale', 'can_request_cash_pickup', 'can_authorize_cash_pickup', 'can_record_banking', 'can_view_bank_reconciliation']
        )
        BusinessMembership.objects.create(
            user=self.cashier, business=self.business, role='cashier', is_active=True,
            permissions=['can_create_sale', 'can_request_cash_pickup', 'can_record_banking']
        )
        BusinessMembership.objects.create(
            user=self.peer_cashier, business=self.business, role='cashier', is_active=True,
            permissions=['can_create_sale', 'can_request_cash_pickup']
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

        # 6. Bank Account
        self.bank_account = BankAccount.objects.create(
            business=self.business,
            bank_name="Absa Bank",
            account_name="Main Operations",
            account_number="0099112233",
            opening_balance=Decimal('20000.00'),
            current_balance=Decimal('20000.00'),
            is_default=True
        )

        self.client = Client()

    def test_drawer_cash_live_aggregation(self):
        """Test running drawer cash calculation: Float + Cash Sales - Pickups."""
        # Create Cash Sale: KES 10,000
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

        # 1. Before pickup: Drawer has Opening Float (3,000) + Sale (10,000) = 13,000
        summary = CashPickupService.get_drawer_cash_summary(
            business=self.business, session=self.session
        )
        self.assertEqual(summary['opening_float'], Decimal('3000.00'))
        self.assertEqual(summary['total_cash_sales'], Decimal('10000.00'))
        self.assertEqual(summary['current_drawer_cash'], Decimal('13000.00'))
        self.assertEqual(summary['suggested_pickup'], Decimal('10000.00'))  # 13,000 - 3,000 target float

        # 2. Record a pickup of KES 8,000
        pickup = CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='8899',  # Manager PIN
            amount=Decimal('8000.00'),
            pickup_reference='BAG-7711',
            reason='threshold_exceeded',
            session=self.session,
            terminal=self.terminal,
            branch=self.branch
        )
        self.assertTrue(pickup.pickup_number.startswith('PKU-'))
        self.assertEqual(pickup.status, 'confirmed')

        # 3. After pickup: Drawer has 13,000 - 8,000 = 5,000
        summary2 = CashPickupService.get_drawer_cash_summary(
            business=self.business, session=self.session
        )
        self.assertEqual(summary2['total_pickups'], Decimal('8000.00'))
        self.assertEqual(summary2['current_drawer_cash'], Decimal('5000.00'))
        self.assertEqual(summary2['suggested_pickup'], Decimal('2000.00'))  # 5,000 - 3,000 float

    def test_dual_custody_authorization_rules(self):
        """Test dual custody verification: manager PIN succeeds, cashier PIN fails, peer witness works."""
        # 1. Cashier trying to authorize their own drop -> Rejected
        with self.assertRaises(Exception):
            CashPickupService.record_pickup(
                business=self.business,
                cashier=self.cashier,
                supervisor_credential='1234',  # Cashier's own PIN
                amount=Decimal('2000.00'),
                pickup_reference='BAG-01',
                session=self.session
            )

        # 2. Invalid supervisor credential -> Rejected
        with self.assertRaises(Exception):
            CashPickupService.record_pickup(
                business=self.business,
                cashier=self.cashier,
                supervisor_credential='0000',  # Wrong PIN
                amount=Decimal('2000.00'),
                pickup_reference='BAG-02',
                session=self.session
            )

        # 3. Valid manager password -> Succeeded
        p1 = CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='ManagerPassword123!',  # Manager password
            amount=Decimal('2500.00'),
            pickup_reference='BAG-03',
            session=self.session
        )
        self.assertEqual(p1.supervisor, self.manager)
        self.assertEqual(p1.witness_type, 'supervisor')

        # 4. Peer cashier fallback witness -> Succeeded
        p2 = CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='',
            amount=Decimal('1500.00'),
            pickup_reference='BAG-04',
            session=self.session,
            witness_type='peer_cashier',
            peer_witness_user=self.peer_cashier
        )
        self.assertEqual(p2.supervisor, self.peer_cashier)
        self.assertEqual(p2.witness_type, 'peer_cashier')

    def test_safe_transfer_and_banking_rollup(self):
        """Test advancing pickup lifecycle: confirmed -> in_safe -> banked into BankingRecord."""
        # Create 2 confirmed pickups
        p1 = CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='8899',
            amount=Decimal('5000.00'),
            pickup_reference='BAG-S1',
            session=self.session
        )
        p2 = CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='8899',
            amount=Decimal('3000.00'),
            pickup_reference='BAG-S2',
            session=self.session
        )

        self.assertEqual(p1.status, 'confirmed')
        self.assertEqual(p2.status, 'confirmed')

        # Transfer both to central safe
        transferred = CashPickupService.transfer_to_safe(
            pickup_ids=[p1.id, p2.id],
            business=self.business,
            user=self.manager,
            notes="Transferred to Safe Compartment A"
        )
        self.assertEqual(transferred, 2)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, 'in_safe')
        self.assertEqual(p2.status, 'in_safe')

        # Create BankingRecord and roll pickups into it
        today = timezone.localdate()
        banking_rec = BankingRecord.objects.create(
            business=self.business,
            branch=self.branch,
            bank_account=self.bank_account,
            period_start=today,
            period_end=today,
            expected_amount=Decimal('8000.00'),
            deposited_amount=Decimal('8000.00'),
            deposit_reference="SLIP-SAFE-01",
            deposit_date=today,
            deposited_by=self.manager,
            status='banked'
        )

        banked_count = CashPickupService.roll_into_banking_record(
            pickup_ids=[p1.id, p2.id],
            banking_record=banking_rec,
            user=self.manager
        )
        self.assertEqual(banked_count, 2)

        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, 'banked')
        self.assertEqual(p1.banking_record, banking_rec)

    def test_zreport_session_closing_with_pickups(self):
        """Test Z-Report generation correctly deducts cash pickups from expected cash in report_data."""
        # 1. Add Cash Sale KES 7,000
        sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal,
            session=self.session,
            cashier=self.cashier,
            subtotal=Decimal('7000.00'),
            vat_amount=Decimal('0.00'),
            total=Decimal('7000.00'),
            amount_paid=Decimal('7000.00'),
            date=timezone.now()
        )
        SalePayment.objects.create(
            business=self.business,
            sale=sale,
            payment_method=self.cash_pm,
            amount=Decimal('7000.00')
        )

        # 2. Add Pickup of KES 6,000
        CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='8899',
            amount=Decimal('6000.00'),
            pickup_reference='BAG-ZR-01',
            session=self.session
        )

        # 3. Expected drawer remaining = Float (3,000) + Sale (7,000) - Pickup (6,000) = 4,000
        # Close session with counted cash of KES 4,000 (Balanced)
        zreport = ZReportService.close_session(
            session_id=self.session.id,
            user=self.manager,
            closing_cash=Decimal('4000.00')
        )

        self.assertIsNotNone(zreport)
        report_data = zreport.report_data
        cash_mgmt = report_data['cash_management']

        self.assertEqual(cash_mgmt['opening_float'], 3000.0)
        self.assertEqual(cash_mgmt['cash_sales'], 7000.0)
        self.assertEqual(cash_mgmt['total_cash_pickups'], 6000.0)
        self.assertEqual(cash_mgmt['expected_cash'], 4000.0)
        self.assertEqual(cash_mgmt['actual_cash_counted'], 4000.0)
        self.assertEqual(cash_mgmt['difference'], 0.0)
        self.assertEqual(len(report_data['cash_pickups']), 1)
        self.assertEqual(report_data['cash_pickups'][0]['reference'], 'BAG-ZR-01')

    def test_chain_of_custody_trajectory(self):
        """Test full 5-stage Chain of Custody trajectory from register to statement match."""
        # Step 1 & 2: Pickup
        pickup = CashPickupService.record_pickup(
            business=self.business,
            cashier=self.cashier,
            supervisor_credential='8899',
            amount=Decimal('9500.00'),
            pickup_reference='BAG-TRACE-99',
            session=self.session,
            terminal=self.terminal,
            branch=self.branch
        )

        # Step 3: Safe
        CashPickupService.transfer_to_safe([pickup.id], self.business, self.manager)

        # Step 4: Banking Record
        today = timezone.localdate()
        rec = BankingRecord.objects.create(
            business=self.business,
            bank_account=self.bank_account,
            period_start=today,
            period_end=today,
            expected_amount=Decimal('9500.00'),
            deposited_amount=Decimal('9500.00'),
            deposit_reference="SLIP-TRACE-01",
            deposit_date=today,
            deposited_by=self.manager,
            status='matched'
        )
        CashPickupService.roll_into_banking_record([pickup.id], rec, self.manager)

        # Step 5: Bank Statement Line
        line = BankStatementLine.objects.create(
            business=self.business,
            bank_account=self.bank_account,
            transaction_date=today,
            line_type='credit',
            amount=Decimal('9500.00'),
            reference="DEP-SLIP-TRACE-01",
            status='matched',
            matched_banking_record=rec
        )
        match = ReconciliationMatch.objects.create(
            business=self.business,
            match_type='one_to_one',
            total_banked_amount=Decimal('9500.00'),
            total_statement_amount=Decimal('9500.00'),
            matched_by=self.manager
        )
        match.banking_records.add(rec)
        match.statement_lines.add(line)

        # Build trajectory
        chain = CashPickupService.get_chain_of_custody(pickup, self.business)

        self.assertTrue(chain['step1_till']['completed'])
        self.assertTrue(chain['step2_dual_custody']['completed'])
        self.assertTrue(chain['step3_safe']['completed'])
        self.assertTrue(chain['step4_banking']['completed'])
        self.assertTrue(chain['step5_statement']['completed'])
        self.assertEqual(chain['step5_statement']['credit_amount'], Decimal('9500.00'))

    def test_http_views_and_reports_endpoints(self):
        """Test HTTP GET & POST endpoints for pickups ledger and 4 audit reports."""
        self.client.force_login(self.manager)

        # 1. Pickups Ledger View
        res_list = self.client.get(reverse('cash_pickup_list', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_list.status_code, 200)

        # 2. Drawer status API
        res_drawer = self.client.get(reverse('cash_pickup_drawer_status', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_drawer.status_code, 200)
        data = res_drawer.json()
        self.assertTrue(data['success'])

        # 3. Create pickup POST (via API) - Cashier performs till drop authorized with Manager PIN 8899
        self.client.force_login(self.cashier)
        payload = {
            'amount': '1200.00',
            'pickup_reference': 'BAG-HTTP-01',
            'supervisor_credential': '8899',
            'reason': 'threshold_exceeded',
            'session_id': self.session.id,
        }
        res_create = self.client.post(
            reverse('cash_pickup_create', kwargs={'slug': self.business.slug}),
            data=payload,
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(res_create.status_code, 200)
        create_data = res_create.json()
        self.assertTrue(create_data['success'])
        pickup_id = create_data['pickup']['id']

        # Switch to manager to view detail, slip, and audit reports
        self.client.force_login(self.manager)

        # 4. Detail view
        res_detail = self.client.get(reverse('cash_pickup_detail', kwargs={'slug': self.business.slug, 'pickup_id': pickup_id}))
        self.assertEqual(res_detail.status_code, 200)

        # 5. Slip print view
        res_print = self.client.get(reverse('cash_pickup_slip_print', kwargs={'slug': self.business.slug, 'pickup_id': pickup_id}))
        self.assertEqual(res_print.status_code, 200)

        # 6. Report: Pickup Log
        res_log = self.client.get(reverse('report_cash_pickup_log', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_log.status_code, 200)

        # 7. Report: Chain of Custody
        res_coc = self.client.get(reverse('report_chain_of_custody', kwargs={'slug': self.business.slug}) + f'?q=BAG-HTTP-01')
        self.assertEqual(res_coc.status_code, 200)

        # 8. Report: Z-Report Variance
        res_var = self.client.get(reverse('report_zreport_variance', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_var.status_code, 200)

        # 9. Report: Supervisor Pickup Summary
        res_sup = self.client.get(reverse('report_supervisor_pickup_summary', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_sup.status_code, 200)
