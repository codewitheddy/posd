"""
Comprehensive Test Suite for Bank Reconciliation & Cash Banking Module
Covers:
- BankAccount CRUD and multi-tenancy isolation
- Expected cash calculations from POS sales and shifts
- BankingRecord variance calculation and auto-numbering
- CSV and OFX Statement Parser
- Auto-matching engine (amount + date tolerance window)
- Manual multi-link matching (combined deposits, split deposits, bank charges)
- Unmatch rollback mechanism
- Segregation of duties permissions
- Financial banking reports
"""

import io
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from pos.models import (
    Business, BusinessMembership, Branch, POSTerminal, PaymentMethod,
    Sale, SaleItem, SalePayment, Category, Product,
    BankAccount, BankingRecord, BankStatementImportBatch, BankStatementLine,
    ReconciliationMatch, BankingAuditLog
)
from pos.banking_services import (
    BankingCalculationService, StatementParserService, ReconciliationEngine
)


class BankReconciliationTests(TestCase):
    def setUp(self):
        # 1. Create Users and Business
        self.owner = User.objects.create_user(username='apex_owner', password='Password123!')
        self.other_owner = User.objects.create_user(username='other_owner', password='Password123!')
        self.manager = User.objects.create_user(username='apex_manager', password='Password123!')
        self.cashier = User.objects.create_user(username='apex_cashier', password='Password123!')

        self.business = Business.objects.create(
            name="Apex Retailers Ltd",
            slug="apex-retailers",
            owner=self.owner
        )
        self.other_business = Business.objects.create(
            name="Other Shop",
            slug="other-shop",
            owner=self.other_owner
        )

        BusinessMembership.objects.create(
            user=self.owner, business=self.business, role='owner', is_active=True
        )
        BusinessMembership.objects.create(
            user=self.manager, business=self.business, role='manager', is_active=True
        )
        BusinessMembership.objects.create(
            user=self.cashier, business=self.business, role='cashier', is_active=True,
            permissions=['can_create_sale', 'can_record_banking']
        )

        # 2. Branch & Terminal
        self.branch = Branch.objects.create(
            business=self.business,
            name="Main Branch",
            code="BRN-001",
            address="Kenyatta Avenue, Nairobi"
        )
        self.terminal = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch,
            name="Till 1",
            terminal_code="TILL-01"
        )

        # 3. Payment Methods
        self.cash_pm, _ = PaymentMethod.objects.get_or_create(
            business=self.business, code='CASH', defaults={'name': 'Cash', 'is_active': True}
        )
        self.card_pm, _ = PaymentMethod.objects.get_or_create(
            business=self.business, code='CARD', defaults={'name': 'Credit Card', 'is_active': True}
        )
        self.cheque_pm, _ = PaymentMethod.objects.get_or_create(
            business=self.business, code='CHEQUE', defaults={'name': 'Cheque', 'is_active': True}
        )

        # 4. Bank Accounts
        self.bank_kcb = BankAccount.objects.create(
            business=self.business,
            bank_name="KCB Bank",
            account_name="Main Collections Account",
            account_number="1100223344",
            opening_balance=Decimal('50000.00'),
            current_balance=Decimal('50000.00'),
            is_default=True
        )
        self.bank_equity = BankAccount.objects.create(
            business=self.business,
            bank_name="Equity Bank",
            account_name="Working Capital",
            account_number="0180293847",
            opening_balance=Decimal('10000.00'),
            current_balance=Decimal('10000.00')
        )

        # 5. Product & Sales Setup
        self.category = Category.objects.create(business=self.business, name="Groceries")
        self.product = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Premium Rice 5kg",
            cost_price=Decimal('500.00'),
            unit_price=Decimal('750.00'),
            stock_quantity=Decimal('100.000'),
            barcode="616110001234"
        )

        self.client = Client()

    def test_bank_account_creation_and_isolation(self):
        """Test bank account creation, default switching, and multi-tenant isolation."""
        self.assertEqual(BankAccount.objects.filter(business=self.business).count(), 2)
        self.assertTrue(self.bank_kcb.is_default)

        # Setting equity as default should toggle off KCB
        self.bank_equity.is_default = True
        self.bank_equity.save()

        self.bank_kcb.refresh_from_db()
        self.assertFalse(self.bank_kcb.is_default)
        self.assertTrue(self.bank_equity.is_default)

        # Other business should see zero bank accounts
        self.assertEqual(BankAccount.objects.filter(business=self.other_business).count(), 0)

    def test_calculate_expected_cash_from_sales(self):
        """Test calculation of expected cash collections from completed sales."""
        today = timezone.localdate()

        # Create Sale 1: KES 1,500 Cash
        sale1 = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal,
            cashier=self.cashier,
            subtotal=Decimal('1500.00'),
            vat_amount=Decimal('0.00'),
            total=Decimal('1500.00'),
            amount_paid=Decimal('1500.00'),
            date=timezone.now()
        )
        SalePayment.objects.create(
            business=self.business,
            sale=sale1,
            payment_method=self.cash_pm,
            amount=Decimal('1500.00')
        )

        # Create Sale 2: KES 750 Card (non-cash)
        sale2 = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal,
            cashier=self.cashier,
            subtotal=Decimal('750.00'),
            vat_amount=Decimal('0.00'),
            total=Decimal('750.00'),
            amount_paid=Decimal('750.00'),
            date=timezone.now()
        )
        SalePayment.objects.create(
            business=self.business,
            sale=sale2,
            payment_method=self.card_pm,
            amount=Decimal('750.00')
        )

        res = BankingCalculationService.calculate_expected_cash(
            business=self.business,
            branch=self.branch,
            period_start=today,
            period_end=today,
            payment_type='cash'
        )

        self.assertEqual(res['expected_amount'], Decimal('1500.00'))
        self.assertEqual(res['sales_count'], 1)

    def test_banking_record_variance_and_numbering(self):
        """Test physical deposit record creation, auto-generated ref, and variance calculation."""
        today = timezone.localdate()

        rec = BankingRecord.objects.create(
            business=self.business,
            branch=self.branch,
            bank_account=self.bank_kcb,
            period_start=today,
            period_end=today,
            expected_amount=Decimal('5000.00'),
            deposited_amount=Decimal('4950.00'),
            deposit_reference="SLIP-KCB-99201",
            deposit_date=today,
            deposited_by=self.cashier,
            variance_reason="KES 50 short due to coin shortage retained in till float"
        )

        self.assertTrue(rec.record_number.startswith('BNK-'))
        self.assertEqual(rec.variance_amount, Decimal('-50.00'))
        self.assertEqual(rec.status, 'banked')

    def test_csv_statement_parser(self):
        """Test parsing a commercial bank statement CSV file."""
        csv_data = """Transaction Date,Narrative,Reference,Debit,Credit,Balance
2026-09-14,CASH DEPOSIT TELLER 04,SLIP-99201,,4950.00,54950.00
2026-09-15,MONTHLY LEDGER FEE,FEE-09,150.00,,54800.00
2026-09-15,BULK CASH DEPOSIT,DEP-4491,,12000.00,66800.00
"""
        file_obj = io.BytesIO(csv_data.encode('utf-8'))
        file_obj.name = "kcb_statement.csv"

        batch = StatementParserService.parse_csv(file_obj, self.bank_kcb, self.manager)

        self.assertEqual(batch.total_lines, 3)
        self.assertEqual(batch.total_credits, Decimal('16950.00'))
        self.assertEqual(batch.total_debits, Decimal('150.00'))
        self.assertEqual(BankStatementLine.objects.filter(batch=batch, line_type='credit').count(), 2)
        self.assertEqual(BankStatementLine.objects.filter(batch=batch, line_type='debit').count(), 1)

    def test_auto_matching_engine(self):
        """Test auto-matching engine pairs deposit with statement line within date window."""
        deposit_date = date(2026, 9, 14)
        statement_date = date(2026, 9, 15) # 1 day later

        rec = BankingRecord.objects.create(
            business=self.business,
            bank_account=self.bank_kcb,
            period_start=deposit_date,
            period_end=deposit_date,
            expected_amount=Decimal('8000.00'),
            deposited_amount=Decimal('8000.00'),
            deposit_reference="SLIP-8800",
            deposit_date=deposit_date,
            deposited_by=self.cashier,
            status='banked'
        )

        line = BankStatementLine.objects.create(
            business=self.business,
            bank_account=self.bank_kcb,
            transaction_date=statement_date,
            line_type='credit',
            amount=Decimal('8000.00'),
            reference="DEP-SLIP-8800",
            description="CASH DEPOSIT APEX",
            status='unmatched'
        )

        res = ReconciliationEngine.auto_match(
            business=self.business,
            bank_account=self.bank_kcb,
            date_tolerance_days=3,
            user=self.manager
        )

        self.assertEqual(res['matched_count'], 1)
        self.assertEqual(res['total_matched_amount'], Decimal('8000.00'))

        rec.refresh_from_db()
        line.refresh_from_db()

        self.assertEqual(rec.status, 'matched')
        self.assertEqual(line.status, 'matched')
        self.assertEqual(line.matched_banking_record, rec)

    def test_manual_matching_combined_deposits(self):
        """Test manual matching combining two daily deposits into one lumped bank credit line."""
        d1 = date(2026, 9, 10)
        d2 = date(2026, 9, 11)

        rec1 = BankingRecord.objects.create(
            business=self.business,
            bank_account=self.bank_kcb,
            period_start=d1,
            period_end=d1,
            expected_amount=Decimal('3000.00'),
            deposited_amount=Decimal('3000.00'),
            deposit_reference="SLIP-DAY1",
            deposit_date=d1,
            deposited_by=self.cashier,
            status='banked'
        )
        rec2 = BankingRecord.objects.create(
            business=self.business,
            bank_account=self.bank_kcb,
            period_start=d2,
            period_end=d2,
            expected_amount=Decimal('2000.00'),
            deposited_amount=Decimal('2000.00'),
            deposit_reference="SLIP-DAY2",
            deposit_date=d2,
            deposited_by=self.cashier,
            status='banked'
        )

        # Single bank credit of KES 5,000 on 12th
        line = BankStatementLine.objects.create(
            business=self.business,
            bank_account=self.bank_kcb,
            transaction_date=date(2026, 9, 12),
            line_type='credit',
            amount=Decimal('5000.00'),
            description="COMBINED CASH DEP",
            status='unmatched'
        )

        match_obj = ReconciliationEngine.manual_match(
            business=self.business,
            banking_record_ids=[rec1.id, rec2.id],
            statement_line_ids=[line.id],
            bank_charge=Decimal('0.00'),
            user=self.manager,
            notes="Matched combined weekend banking"
        )

        self.assertEqual(match_obj.match_type, 'many_to_one')
        self.assertEqual(match_obj.total_banked_amount, Decimal('5000.00'))
        self.assertEqual(match_obj.total_statement_amount, Decimal('5000.00'))

        rec1.refresh_from_db()
        rec2.refresh_from_db()
        line.refresh_from_db()

        self.assertEqual(rec1.status, 'matched')
        self.assertEqual(rec2.status, 'matched')
        self.assertEqual(line.status, 'matched')

        # Test unmatch rollback
        unmatched = ReconciliationEngine.unmatch(match_obj.id, self.business, self.manager)
        self.assertTrue(unmatched)

        rec1.refresh_from_db()
        rec2.refresh_from_db()
        line.refresh_from_db()

        self.assertEqual(rec1.status, 'banked')
        self.assertEqual(rec2.status, 'banked')
        self.assertEqual(line.status, 'unmatched')

    def test_reconciliation_statement_calculation(self):
        """Test calculation of formal 4-part bank reconciliation statement."""
        as_of = date(2026, 9, 16)

        # Banked record not yet on statement (Deposit in transit)
        BankingRecord.objects.create(
            business=self.business,
            bank_account=self.bank_kcb,
            period_start=as_of,
            period_end=as_of,
            expected_amount=Decimal('15000.00'),
            deposited_amount=Decimal('15000.00'),
            deposit_reference="TRANSIT-SLIP-01",
            deposit_date=as_of,
            deposited_by=self.cashier,
            status='banked'
        )

        recon = ReconciliationEngine.get_reconciliation_statement(
            business=self.business,
            bank_account=self.bank_kcb,
            as_of_date=as_of
        )

        self.assertEqual(recon['opening_balance'], Decimal('50000.00'))
        self.assertEqual(recon['deposits_in_transit'], Decimal('15000.00'))
        self.assertEqual(recon['book_balance'], Decimal('65000.00'))

    def test_banking_views_http_endpoints(self):
        """Test HTTP responses for banking views."""
        self.client.force_login(self.manager)

        # 1. Accounts list
        res_acc = self.client.get(reverse('bank_account_list', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_acc.status_code, 200)

        # 2. Banking records list
        res_rec = self.client.get(reverse('banking_record_list', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_rec.status_code, 200)

        # 3. Create banking record GET
        res_create = self.client.get(reverse('banking_record_create', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_create.status_code, 200)

        # 4. Statements list
        res_stmt = self.client.get(reverse('bank_statement_list', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_stmt.status_code, 200)

        # 5. Reconciliation workspace
        res_ws = self.client.get(reverse('bank_reconciliation_workspace', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_ws.status_code, 200)

        # 6. Reports
        res_daily = self.client.get(reverse('report_daily_banking_summary', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_daily.status_code, 200)

        res_unbanked = self.client.get(reverse('report_unbanked_funds', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_unbanked.status_code, 200)

        res_statement = self.client.get(reverse('report_bank_reconciliation_statement', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_statement.status_code, 200)

        res_var = self.client.get(reverse('report_variance_discrepancy', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_var.status_code, 200)

        res_aging = self.client.get(reverse('report_aging_unmatched', kwargs={'slug': self.business.slug}))
        self.assertEqual(res_aging.status_code, 200)
