from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError

from pos.models import (
    Business, BusinessMembership, Branch, POSTerminal, Supplier, SupplierInvoice, SupplierPayment,
    SupplierCredit, SupplierCreditApplication, SupplierRefund,
    PaymentAllocation, BankAccount, BankStatementImportBatch, BankStatementLine,
    ReconciliationMatch, POSSession, CashPaidOut, ExpenseCategory
)
from pos.supplier_ap_services import (
    SupplierInvoiceService, SupplierPaymentAPService,
    SupplierCreditService, SupplierReportService
)
from pos.cash_paid_out_services import CashPaidOutService
from pos.banking_services import ReconciliationEngine

User = get_user_model()


class SupplierPaymentsAndCreditsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ap_manager',
            email='ap@example.com',
            password='testpassword123',
            first_name='AP',
            last_name='Manager'
        )

        self.business = Business.objects.create(
            name='Test Retail Enterprise',
            slug='test-retail-ent',
            owner=self.user
        )

        BusinessMembership.objects.create(
            user=self.user,
            business=self.business,
            role='owner',
            is_active=True
        )

        self.branch = Branch.objects.create(
            business=self.business,
            name='Main Outlet',
            code='MAIN-01'
        )

        self.terminal = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch,
            name='Register 01',
            terminal_code='REG-01'
        )

        self.supplier = Supplier.objects.create(
            business=self.business,
            name='Global Supplies Ltd',
            email='orders@globalsupplies.com',
            phone='+254700111222'
        )

        self.bank_account = BankAccount.objects.create(
            business=self.business,
            bank_name='Equity Bank',
            account_name='Operations Current',
            account_number='0110192837465',
            currency='KES',
            opening_balance=Decimal('50000.00'),
            current_balance=Decimal('50000.00'),
            is_default=True
        )

        self.pos_session = POSSession.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal,
            opened_by=self.user,
            cashier=self.user,
            opening_cash=Decimal('10000.00'),
            status='open'
        )

    # ==================== 1. SUPPLIER INVOICE TESTS ====================

    def test_create_supplier_invoice(self):
        """Test recording an accrual supplier invoice"""
        inv = SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-2026-001',
            invoice_date=date(2026, 9, 1),
            due_date=date(2026, 9, 30),
            amount=Decimal('15000.00'),
            notes='Delivery for September inventory',
            created_by=self.user
        )

        self.assertEqual(inv.status, 'unpaid')
        self.assertEqual(inv.amount, Decimal('15000.00'))
        self.assertEqual(inv.total_paid(), Decimal('0.00'))
        self.assertEqual(inv.total_credited(), Decimal('0.00'))
        self.assertEqual(inv.remaining_balance(), Decimal('15000.00'))
        self.assertFalse(inv.is_overdue())

    def test_duplicate_invoice_number_raises_error(self):
        """Cannot create two invoices with the same invoice number for the same supplier"""
        SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-DUP-1',
            invoice_date=date(2026, 9, 1),
            due_date=date(2026, 9, 30),
            amount=Decimal('5000.00'),
            created_by=self.user
        )

        with self.assertRaises(ValidationError):
            SupplierInvoiceService.create_invoice(
                business=self.business,
                supplier=self.supplier,
                invoice_number='INV-DUP-1',
                invoice_date=date(2026, 9, 5),
                due_date=date(2026, 10, 5),
                amount=Decimal('8000.00'),
                created_by=self.user
            )

    # ==================== 2. SUPPLIER PAYMENTS & ALLOCATIONS ====================

    def test_pay_supplier_via_bank_transfer_and_fifo_allocation(self):
        """Test paying supplier from bank account with automated FIFO allocation"""
        inv1 = SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-001',
            invoice_date=date(2026, 9, 1),
            due_date=date(2026, 9, 15),
            amount=Decimal('10000.00'),
            created_by=self.user
        )
        inv2 = SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-002',
            invoice_date=date(2026, 9, 5),
            due_date=date(2026, 9, 20),
            amount=Decimal('10000.00'),
            created_by=self.user
        )

        # Pay KES 15,000 via Bank Transfer (should clear inv1 and partially pay inv2)
        payment = SupplierPaymentAPService.record_payment(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('15000.00'),
            payment_date=date(2026, 9, 10),
            payment_method_type='bank_transfer',
            source_type='bank_account',
            bank_account=self.bank_account,
            reference_number='EFT-998877',
            authorized_by=self.user,
            created_by=self.user
        )

        inv1.refresh_from_db()
        inv2.refresh_from_db()

        self.assertEqual(payment.status, 'sent')
        self.assertEqual(payment.unallocated_amount(), Decimal('0.00'))
        self.assertEqual(inv1.status, 'paid')
        self.assertEqual(inv1.remaining_balance(), Decimal('0.00'))
        self.assertEqual(inv2.status, 'partially_paid')
        self.assertEqual(inv2.remaining_balance(), Decimal('5000.00'))
        self.assertEqual(payment.allocations.count(), 2)

    def test_pay_supplier_via_cash_drawer_creates_linked_paid_out(self):
        """Paying supplier from cash drawer must automatically create CashPaidOut and deduct till"""
        inv = SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-CASH-1',
            invoice_date=date(2026, 9, 10),
            due_date=date(2026, 9, 25),
            amount=Decimal('3500.00'),
            created_by=self.user
        )

        payment = SupplierPaymentAPService.record_payment(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('3500.00'),
            payment_date=date(2026, 9, 10),
            payment_method_type='cash',
            source_type='cash_drawer',
            authorized_by=self.user,
            created_by=self.user,
            pos_session=self.pos_session
        )

        inv.refresh_from_db()
        self.assertEqual(payment.status, 'cleared')  # Cash is immediate
        self.assertIsNotNone(payment.cash_paid_out)
        self.assertEqual(payment.cash_paid_out.amount, Decimal('3500.00'))
        self.assertEqual(payment.cash_paid_out.payee, self.supplier.name)
        self.assertEqual(inv.status, 'paid')

        # Check drawer cash reflects deduction
        drawer_summary = CashPaidOutService.get_drawer_cash_summary(business=self.business, session=self.pos_session)
        self.assertEqual(drawer_summary['total_paid_outs'], Decimal('3500.00'))
        self.assertEqual(drawer_summary['current_drawer_cash'], Decimal('6500.00'))

    def test_payment_reversal(self):
        """Reversing a payment restores invoice balances and reverses linked paid-outs"""
        inv = SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-REV-1',
            invoice_date=date(2026, 9, 10),
            due_date=date(2026, 9, 25),
            amount=Decimal('4000.00'),
            created_by=self.user
        )

        payment = SupplierPaymentAPService.record_payment(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('4000.00'),
            payment_date=date(2026, 9, 10),
            payment_method_type='cash',
            source_type='cash_drawer',
            authorized_by=self.user,
            created_by=self.user,
            pos_session=self.pos_session
        )

        inv.refresh_from_db()
        self.assertEqual(inv.status, 'paid')

        # Reverse payment
        SupplierPaymentAPService.reverse_payment(
            payment=payment,
            user=self.user,
            reason='Paid wrong supplier by error'
        )

        payment.refresh_from_db()
        payment.cash_paid_out.refresh_from_db()
        inv.refresh_from_db()

        self.assertTrue(payment.is_reversed)
        self.assertEqual(payment.status, 'reversed')
        self.assertEqual(inv.status, 'unpaid')
        self.assertEqual(inv.remaining_balance(), Decimal('4000.00'))

        # Linked cash paid out should also be cancelled/reversed
        self.assertTrue(payment.cash_paid_out.is_reversed)

    # ==================== 3. SUPPLIER CREDITS & REFUNDS ====================

    def test_raise_credit_and_apply_to_invoice(self):
        """Raising a credit note and applying it to reduce an open invoice balance"""
        inv = SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-CREDIT-TEST',
            invoice_date=date(2026, 9, 1),
            due_date=date(2026, 9, 30),
            amount=Decimal('20000.00'),
            created_by=self.user
        )

        # Raise credit for damaged goods
        credit = SupplierCreditService.raise_credit(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('5000.00'),
            reason='damaged_delivery',
            date_raised=date(2026, 9, 5),
            related_invoice=inv,
            notes='Damaged cartons on delivery',
            authorized_by=self.user,
            created_by=self.user
        )

        self.assertEqual(credit.status, 'approved_by_supplier')
        self.assertEqual(credit.remaining_credit(), Decimal('5000.00'))

        # Apply credit to invoice
        app = SupplierCreditService.apply_credit_to_invoice(
            credit=credit,
            invoice=inv,
            amount=Decimal('5000.00'),
            user=self.user,
            notes='Offsetting damaged items'
        )

        credit.refresh_from_db()
        inv.refresh_from_db()

        self.assertEqual(credit.status, 'applied_to_invoice')
        self.assertEqual(credit.remaining_credit(), Decimal('0.00'))
        self.assertEqual(inv.total_credited(), Decimal('5000.00'))
        self.assertEqual(inv.remaining_balance(), Decimal('15000.00'))
        self.assertEqual(inv.status, 'partially_paid')

    def test_supplier_cash_refund_for_credit(self):
        """Test recording an incoming refund from a supplier settling a credit claim"""
        credit = SupplierCreditService.raise_credit(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('8000.00'),
            reason='rebate_discount',
            date_raised=date(2026, 9, 1),
            authorized_by=self.user,
            created_by=self.user
        )

        refund = SupplierCreditService.record_refund(
            credit=credit,
            amount=Decimal('8000.00'),
            received_date=date(2026, 9, 8),
            received_via='bank_transfer',
            destination_account=self.bank_account,
            reference='REFUND-TX-100',
            user=self.user
        )

        credit.refresh_from_db()
        self.assertEqual(credit.status, 'refunded')
        self.assertEqual(credit.remaining_credit(), Decimal('0.00'))
        self.assertEqual(refund.status, 'pending')
        self.assertEqual(refund.amount, Decimal('8000.00'))

    # ==================== 4. TWO-WAY BANK STATEMENT RECONCILIATION ====================

    def test_two_way_bank_reconciliation_auto_match(self):
        """
        Test ReconciliationEngine matching both:
        1. Outflows (Bank Debit Lines <-> SupplierPayment) -> marks payment 'cleared'
        2. Inflows (Bank Credit Lines <-> SupplierRefund) -> marks refund 'cleared'
        """
        # 1. Outgoing payment (EFT)
        payment = SupplierPaymentAPService.record_payment(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('12500.00'),
            payment_date=date(2026, 9, 12),
            payment_method_type='bank_transfer',
            source_type='bank_account',
            bank_account=self.bank_account,
            reference_number='EFT-AUTOBANK-1',
            authorized_by=self.user,
            created_by=self.user
        )
        self.assertEqual(payment.status, 'sent')

        # 2. Incoming supplier refund
        credit = SupplierCreditService.raise_credit(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('6200.00'),
            reason='overcharge',
            date_raised=date(2026, 9, 10),
            authorized_by=self.user,
            created_by=self.user
        )
        refund = SupplierCreditService.record_refund(
            credit=credit,
            amount=Decimal('6200.00'),
            received_date=date(2026, 9, 12),
            received_via='bank_transfer',
            destination_account=self.bank_account,
            reference='REFUND-BANK-1',
            user=self.user
        )
        self.assertEqual(refund.status, 'pending')

        # 3. Import Bank Statement with Debit (12,500) and Credit (6,200)
        batch = BankStatementImportBatch.objects.create(
            business=self.business,
            bank_account=self.bank_account,
            statement_start_date=date(2026, 9, 1),
            statement_end_date=date(2026, 9, 30),
            opening_balance=Decimal('50000.00'),
            closing_balance=Decimal('43700.00'),
            imported_by=self.user
        )

        debit_line = BankStatementLine.objects.create(
            batch=batch,
            bank_account=self.bank_account,
            business=self.business,
            transaction_date=date(2026, 9, 12),
            line_type='debit',
            amount=Decimal('12500.00'),
            description='EFT Outflow Supplier Payment EFT-AUTOBANK-1',
            reference='EFT-AUTOBANK-1',
            status='unmatched'
        )

        credit_line = BankStatementLine.objects.create(
            batch=batch,
            bank_account=self.bank_account,
            business=self.business,
            transaction_date=date(2026, 9, 12),
            line_type='credit',
            amount=Decimal('6200.00'),
            description='Refund Inflow REFUND-BANK-1',
            reference='REFUND-BANK-1',
            status='unmatched'
        )

        # Run Auto Match
        auto_results = ReconciliationEngine.auto_match(
            business=self.business,
            bank_account=self.bank_account,
            user=self.user
        )

        self.assertGreaterEqual(auto_results['matched_count'], 2)

        # Check payment status updated to cleared and linked
        payment.refresh_from_db()
        refund.refresh_from_db()
        debit_line.refresh_from_db()
        credit_line.refresh_from_db()

        self.assertEqual(payment.status, 'cleared')
        self.assertEqual(payment.bank_statement_line, debit_line)
        self.assertEqual(debit_line.status, 'matched')
        self.assertEqual(debit_line.matched_supplier_payment, payment)

        self.assertEqual(refund.status, 'matched')
        self.assertEqual(refund.bank_statement_line, credit_line)
        self.assertEqual(credit_line.status, 'matched')
        self.assertEqual(credit_line.matched_supplier_refund, refund)

    def test_locked_matched_records_cannot_be_modified_without_unmatching(self):
        """Payments matched to bank statements cannot be reversed directly"""
        payment = SupplierPaymentAPService.record_payment(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('5000.00'),
            payment_date=date(2026, 9, 10),
            payment_method_type='bank_transfer',
            source_type='bank_account',
            bank_account=self.bank_account,
            authorized_by=self.user,
            created_by=self.user
        )

        batch = BankStatementImportBatch.objects.create(
            business=self.business,
            bank_account=self.bank_account,
            statement_start_date=date(2026, 9, 1),
            statement_end_date=date(2026, 9, 30),
            opening_balance=Decimal('50000.00'),
            closing_balance=Decimal('45000.00'),
            imported_by=self.user
        )

        debit_line = BankStatementLine.objects.create(
            batch=batch,
            bank_account=self.bank_account,
            business=self.business,
            transaction_date=date(2026, 9, 10),
            line_type='debit',
            amount=Decimal('5000.00'),
            description='Supplier Payment',
            reference='EFT-5000',
            status='unmatched'
        )

        match = ReconciliationEngine.manual_match(
            business=self.business,
            statement_line_ids=[debit_line.id],
            supplier_payment_ids=[payment.id],
            user=self.user
        )

        payment.refresh_from_db()
        self.assertEqual(payment.status, 'cleared')

        # Attempting reversal should raise ValidationError
        with self.assertRaises(ValidationError):
            SupplierPaymentAPService.reverse_payment(
                payment=payment,
                user=self.user,
                reason='Trying to reverse cleared bank payment'
            )

        # Unmatching allows reversal
        ReconciliationEngine.unmatch(
            reconciliation_match_id=match.id,
            business=self.business,
            user=self.user
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'sent')
        self.assertIsNone(payment.bank_statement_line)

        # Now reversal succeeds
        SupplierPaymentAPService.reverse_payment(
            payment=payment,
            user=self.user,
            reason='Unmatched and reversed successfully'
        )
        payment.refresh_from_db()
        self.assertTrue(payment.is_reversed)

    # ==================== 5. REPORTS TESTS ====================

    def test_ap_aging_report(self):
        """Test AP aging buckets (current, 30, 60, 90+)"""
        today = timezone.now().date()

        # Current (10 days old)
        SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-AGE-1',
            invoice_date=today - timedelta(days=10),
            due_date=today + timedelta(days=20),
            amount=Decimal('1000.00'),
            created_by=self.user
        )

        # 31-60 days (40 days old)
        SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-AGE-2',
            invoice_date=today - timedelta(days=40),
            due_date=today - timedelta(days=10),
            amount=Decimal('2000.00'),
            created_by=self.user
        )

        # 61-90 days (70 days old)
        SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-AGE-3',
            invoice_date=today - timedelta(days=70),
            due_date=today - timedelta(days=40),
            amount=Decimal('3000.00'),
            created_by=self.user
        )

        # 90+ days (100 days old)
        SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-AGE-4',
            invoice_date=today - timedelta(days=100),
            due_date=today - timedelta(days=70),
            amount=Decimal('4000.00'),
            created_by=self.user
        )

        report = SupplierReportService.get_ap_aging_report(business=self.business, as_of_date=today)

        self.assertEqual(report['totals']['current'], Decimal('1000.00'))
        self.assertEqual(report['totals']['days_30'], Decimal('2000.00'))
        self.assertEqual(report['totals']['days_60'], Decimal('3000.00'))
        self.assertEqual(report['totals']['days_90_plus'], Decimal('4000.00'))
        self.assertEqual(report['totals']['total'], Decimal('10000.00'))

    def test_supplier_statement_report(self):
        """Test running balance on supplier statement"""
        inv = SupplierInvoiceService.create_invoice(
            business=self.business,
            supplier=self.supplier,
            invoice_number='INV-STMT-1',
            invoice_date=date(2026, 9, 1),
            due_date=date(2026, 9, 30),
            amount=Decimal('50000.00'),
            created_by=self.user
        )

        pay = SupplierPaymentAPService.record_payment(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('20000.00'),
            payment_date=date(2026, 9, 10),
            payment_method_type='bank_transfer',
            source_type='bank_account',
            bank_account=self.bank_account,
            authorized_by=self.user,
            created_by=self.user
        )

        cr = SupplierCreditService.raise_credit(
            business=self.business,
            supplier=self.supplier,
            amount=Decimal('5000.00'),
            reason='rebate_discount',
            date_raised=date(2026, 9, 15),
            authorized_by=self.user,
            created_by=self.user
        )

        stmt = SupplierReportService.get_supplier_statement(supplier=self.supplier)

        self.assertEqual(stmt['total_invoiced'], Decimal('50000.00'))
        self.assertEqual(stmt['total_paid'], Decimal('20000.00'))
        self.assertEqual(stmt['total_credits'], Decimal('5000.00'))
        # Closing balance = 50,000 - 20,000 - 5,000 = 25,000
        self.assertEqual(stmt['closing_balance'], Decimal('25000.00'))

    # ==================== 6. HTTP VIEWS TESTS ====================

    def test_supplier_ap_views_http(self):
        """Test HTTP GET & POST endpoints for Invoices, Payments, Credits, Reports"""
        self.client.force_login(self.user)

        # 1. Invoice list & create
        res = self.client.get('/purchasing/invoices/')
        self.assertEqual(res.status_code, 200)

        res = self.client.get('/purchasing/invoices/create/')
        self.assertEqual(res.status_code, 200)

        res = self.client.post('/purchasing/invoices/create/', {
            'supplier_id': self.supplier.id,
            'invoice_number': 'INV-HTTP-101',
            'invoice_date': '2026-09-01',
            'due_date': '2026-09-30',
            'amount': '12000.00',
            'notes': 'Test via HTTP'
        })
        self.assertEqual(res.status_code, 302)
        inv = SupplierInvoice.objects.filter(invoice_number='INV-HTTP-101').first()
        self.assertIsNotNone(inv)

        # 2. Payment list & create
        res = self.client.get('/purchasing/payments/')
        self.assertEqual(res.status_code, 200)

        res = self.client.get('/purchasing/payments/create/')
        self.assertEqual(res.status_code, 200)

        res = self.client.post('/purchasing/payments/create/', {
            'supplier_id': self.supplier.id,
            'amount': '6000.00',
            'payment_date': '2026-09-10',
            'source_type': 'bank_account',
            'payment_method_type': 'bank_transfer',
            'bank_account_id': self.bank_account.id,
            'reference_number': 'REF-HTTP-1'
        })
        self.assertEqual(res.status_code, 302)

        # 3. Credit list & create
        res = self.client.get('/purchasing/credits/')
        self.assertEqual(res.status_code, 200)

        res = self.client.get('/purchasing/credits/create/')
        self.assertEqual(res.status_code, 200)

        res = self.client.post('/purchasing/credits/create/', {
            'supplier_id': self.supplier.id,
            'amount': '2000.00',
            'reason': 'return',
            'date_raised': '2026-09-12',
            'notes': 'HTTP Credit'
        })
        self.assertEqual(res.status_code, 302)

        # 4. Reports
        res = self.client.get('/purchasing/reports/aging/')
        self.assertEqual(res.status_code, 200)

        res = self.client.get(f'/purchasing/reports/statement/?supplier_id={self.supplier.id}')
        self.assertEqual(res.status_code, 200)

        res = self.client.get('/purchasing/reports/outstanding-credits/')
        self.assertEqual(res.status_code, 200)

        res = self.client.get('/purchasing/reports/outstanding-cheques/')
        self.assertEqual(res.status_code, 200)

        res = self.client.get('/purchasing/reports/unmatched-statements/')
        self.assertEqual(res.status_code, 200)
