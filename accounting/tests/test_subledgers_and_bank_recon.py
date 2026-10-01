"""
Unit Tests for Phase 3: Subledgers (AR, AP), Invoicing, Vendor Bills, and Bank/M-Pesa Reconciliation
"""
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone as dt_timezone
from django.test import TestCase
from django.contrib.auth.models import User

from core.models.organization import Company, Branch
from accounting.models import (
    Account, JournalEntry, JournalEntryStatus,
    Customer, Vendor,
    CustomerInvoice, CustomerInvoiceLine, InvoiceStatus,
    CustomerPayment, CustomerPaymentAllocation,
    VendorBill, VendorBillLine, BillStatus,
    VendorPayment, VendorPaymentAllocation,
    BankAccount, BankStatement, BankStatementLine, BankReconciliation
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from accounting import api


class SubledgerAndBankReconciliationTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Safari Hardware Ltd', slug='safari-hardware')
        self.branch = Branch.objects.create(company=self.company, name='Nairobi West', code='NRB-W')
        self.user = User.objects.create_user(username='accountant_jane', password='securepass123')

        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

        # Create Bank Account linked to 1030 (Bank Account - Primary)
        self.bank_gl = Account.objects.get(company=self.company, code='1030')
        self.bank_account = BankAccount.objects.create(
            company=self.company,
            name='KCB Corporate Operating Account',
            bank_name='KCB Bank Kenya',
            account_number='1122334455',
            gl_account=self.bank_gl
        )

        # Create M-Pesa Account linked to 1040 (M-Pesa Clearing)
        self.mpesa_gl = Account.objects.get(company=self.company, code='1040')
        self.mpesa_account = BankAccount.objects.create(
            company=self.company,
            name='Safaricom Paybill 654321',
            bank_name='Safaricom M-Pesa',
            account_number='654321',
            gl_account=self.mpesa_gl
        )

        # Revenue and Expense accounts
        self.sales_gl = Account.objects.get(company=self.company, code='4000')
        self.expense_gl = Account.objects.get(company=self.company, code='6100')  # Rent

    # ─── ACCOUNTS RECEIVABLE (AR) TESTS ───────────────────────────────────────

    def test_customer_invoice_posting_to_gl(self):
        """Test creating and posting a Customer Invoice to General Ledger."""
        customer = Customer.objects.create(
            company=self.company,
            name='Acme Construction Kenya',
            kra_pin='P051234567A',
            phone='+254712345678'
        )

        invoice = CustomerInvoice.objects.create(
            company=self.company,
            branch=self.branch,
            customer=customer,
            invoice_number='INV-2026-001',
            invoice_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=InvoiceStatus.DRAFT
        )

        # Line: 10 items @ KES 10,000 + 16% VAT = KES 100,000 + 16,000 = 116,000
        CustomerInvoiceLine.objects.create(
            invoice=invoice,
            account=self.sales_gl,
            description='Building Cement 50kg bags (x100)',
            quantity=Decimal('10.00'),
            unit_price=Decimal('10000.00'),
            tax_rate=Decimal('16.00')
        )

        entry = api.post_customer_invoice(invoice, user=self.user)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, JournalEntryStatus.POSTED)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InvoiceStatus.POSTED)
        self.assertEqual(invoice.subtotal, Decimal('100000.00'))
        self.assertEqual(invoice.tax_amount, Decimal('16000.00'))
        self.assertEqual(invoice.total_amount, Decimal('116000.00'))
        self.assertEqual(invoice.balance_due, Decimal('116000.00'))

        # GL Lines check: DR 1100 (116k), CR 4000 (100k), CR 2100 (16k)
        lines = {l.account_code: l for l in entry.lines.all()}
        self.assertEqual(lines['1100'].debit, Decimal('116000.00'))
        self.assertEqual(lines['4000'].credit, Decimal('100000.00'))
        self.assertEqual(lines['2100'].credit, Decimal('16000.00'))

    def test_customer_payment_and_subledger_allocation(self):
        """Test recording customer payment receipt and partial/full allocation."""
        customer = Customer.objects.create(company=self.company, name='BuildX Ltd')
        inv = CustomerInvoice.objects.create(
            company=self.company,
            branch=self.branch,
            customer=customer,
            invoice_number='INV-2026-002',
            invoice_date=date(2026, 3, 5),
            due_date=date(2026, 3, 20),
            status=InvoiceStatus.DRAFT
        )
        CustomerInvoiceLine.objects.create(
            invoice=inv,
            account=self.sales_gl,
            description='Timber 2x4',
            quantity=Decimal('1.00'),
            unit_price=Decimal('50000.00'),
            tax_rate=Decimal('0.00')
        )
        api.post_customer_invoice(inv, user=self.user)

        # 1. Partial payment: KES 20,000 received into Bank
        pay1 = CustomerPayment.objects.create(
            company=self.company,
            branch=self.branch,
            customer=customer,
            receipt_number='REC-001',
            payment_date=date(2026, 3, 10),
            amount=Decimal('20000.00'),
            payment_method='bank',
            deposit_account=self.bank_gl
        )
        api.record_customer_payment(pay1, [{'invoice': inv, 'amount': Decimal('20000.00')}], user=self.user)

        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.PARTIAL)
        self.assertEqual(inv.amount_paid, Decimal('20000.00'))
        self.assertEqual(inv.balance_due, Decimal('30000.00'))

        # 2. Final settlement: KES 30,000 received via M-Pesa
        pay2 = CustomerPayment.objects.create(
            company=self.company,
            branch=self.branch,
            customer=customer,
            receipt_number='REC-002',
            payment_date=date(2026, 3, 15),
            amount=Decimal('30000.00'),
            payment_method='mpesa',
            reference='QHJ8291KL0',
            deposit_account=self.mpesa_gl
        )
        api.record_customer_payment(pay2, [{'invoice': inv, 'amount': Decimal('30000.00')}], user=self.user)

        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.PAID)
        self.assertEqual(inv.balance_due, Decimal('0.00'))

    def test_ar_aging_report(self):
        """Test AR aging report bucketing across overdue intervals."""
        cust = Customer.objects.create(company=self.company, name='Premier Developers')

        # Overdue 45 days (bucket 31-60)
        inv1 = CustomerInvoice.objects.create(
            company=self.company,
            customer=cust,
            invoice_number='INV-AGE-1',
            invoice_date=date(2026, 1, 1),
            due_date=date(2026, 1, 31),
            status=InvoiceStatus.POSTED,
            total_amount=Decimal('40000.00'),
            amount_paid=Decimal('0.00'),
            balance_due=Decimal('40000.00')
        )

        # Current (not overdue)
        inv2 = CustomerInvoice.objects.create(
            company=self.company,
            customer=cust,
            invoice_number='INV-AGE-2',
            invoice_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=InvoiceStatus.POSTED,
            total_amount=Decimal('60000.00'),
            amount_paid=Decimal('0.00'),
            balance_due=Decimal('60000.00')
        )

        report = api.get_ar_aging(self.company, as_of_date=date(2026, 3, 15))
        self.assertEqual(report['totals']['current'], Decimal('60000.00'))
        self.assertEqual(report['totals']['days_31_60'], Decimal('40000.00'))
        self.assertEqual(report['totals']['total_due'], Decimal('100000.00'))

    # ─── ACCOUNTS PAYABLE (AP) TESTS ─────────────────────────────────────────

    def test_vendor_bill_posting_and_payment_voucher(self):
        """Test vendor bill creation, posting to GL, and disbursement voucher."""
        vendor = Vendor.objects.create(
            company=self.company,
            name='Nairobi Commercial Properties',
            kra_pin='P059988776B',
            payment_terms_days=30
        )

        bill = VendorBill.objects.create(
            company=self.company,
            branch=self.branch,
            vendor=vendor,
            bill_number='BILL-2026-001',
            supplier_invoice_number='PROP-MAR-2026',
            bill_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=BillStatus.DRAFT
        )

        # Net Rent KES 100,000 + 16% VAT = 116,000
        VendorBillLine.objects.create(
            bill=bill,
            account=self.expense_gl,
            description='Monthly Shop Rent - March 2026',
            quantity=Decimal('1.00'),
            unit_price=Decimal('100000.00'),
            tax_rate=Decimal('16.00')
        )

        entry = api.post_vendor_bill(bill, user=self.user)

        self.assertIsNotNone(entry)
        bill.refresh_from_db()
        self.assertEqual(bill.status, BillStatus.POSTED)
        self.assertEqual(bill.total_amount, Decimal('116000.00'))

        # GL Lines: DR 6100 (100k), DR 1400 (16k), CR 2000 (116k)
        lines = {l.account_code: l for l in entry.lines.all()}
        self.assertEqual(lines['6100'].debit, Decimal('100000.00'))
        self.assertEqual(lines['1400'].debit, Decimal('16000.00'))
        self.assertEqual(lines['2000'].credit, Decimal('116000.00'))

        # Record full payment from Bank Account
        vouch = VendorPayment.objects.create(
            company=self.company,
            branch=self.branch,
            vendor=vendor,
            voucher_number='VOUCH-001',
            payment_date=date(2026, 3, 20),
            amount=Decimal('116000.00'),
            payment_method='bank',
            reference='EFT-889900',
            paid_from_account=self.bank_gl
        )
        api.record_vendor_payment(vouch, [{'bill': bill, 'amount': Decimal('116000.00')}], user=self.user)

        bill.refresh_from_db()
        self.assertEqual(bill.status, BillStatus.PAID)
        self.assertEqual(bill.balance_due, Decimal('0.00'))

    # ─── BANK & M-PESA RECONCILIATION TESTS ───────────────────────────────────

    def test_mpesa_statement_parsing_and_auto_reconciliation(self):
        """
        Test importing a Safaricom M-Pesa statement CSV, parsing lines,
        and auto-reconciling against general ledger entries.
        """
        # First create a GL entry with M-Pesa receipt code
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='ZREP-MPESA-01',
            date_val=date(2026, 3, 10),
            lines=[
                {'account_code': '1040', 'debit': '15000.00', 'credit': '0.00', 'description': 'Customer payment QHD4829J1X'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '15000.00', 'description': 'Sales'},
            ],
            narration='POS M-Pesa Collection',
            branch=self.branch,
            auto_approve=True
        )

        csv_content = """Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
QHD4829J1X,2026-03-10 14:30:00,Customer Transfer from John Doe,Completed,15000.00,,15000.00
TRX998877K,2026-03-10 18:00:00,Merchant Fee Charge,Completed,,150.00,14850.00
"""

        statement = api.parse_mpesa_statement(self.mpesa_account, csv_content, user=self.user)

        self.assertIsNotNone(statement)
        self.assertEqual(statement.lines.count(), 2)

        line1 = statement.lines.get(reference='QHD4829J1X')
        self.assertEqual(line1.amount, Decimal('15000.00'))

        line2 = statement.lines.get(reference='TRX998877K')
        self.assertEqual(line2.amount, Decimal('-150.00'))

        # Run Auto-Reconciliation
        res = api.auto_reconcile_statement(statement)
        self.assertEqual(res['matched'], 1)
        self.assertEqual(res['unmatched'], 1)

        line1.refresh_from_db()
        self.assertTrue(line1.is_reconciled)
        self.assertIsNotNone(line1.matched_journal_line)

    def test_bank_reconciliation_statement_report(self):
        """Test generating a balanced Bank Reconciliation Statement."""
        # 1. Post Bank GL deposit of KES 50,000 (Deposit in transit)
        gl_entry = api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='DEPOSIT-01',
            date_val=date(2026, 3, 25),
            lines=[
                {'account_code': '1030', 'debit': '50000.00', 'credit': '0.00', 'description': 'Cash banking'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '50000.00', 'description': 'Cash Sales'},
            ],
            auto_approve=True
        )

        # 2. Scenario A: Bank statement ending balance is 0.00, so KES 50,000 is an uncredited deposit (in-transit)
        # Formula: Adjusted = Statement (0.00) + In-Transit Deposit (50,000.00) = 50,000.00 == GL Balance (50,000.00)
        stmt = BankStatement.objects.create(
            company=self.company,
            bank_account=self.bank_account,
            statement_date=date(2026, 3, 31),
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            opening_balance=Decimal('0.00'),
            closing_balance=Decimal('0.00')
        )

        from accounting.selectors import get_bank_reconciliation_summary
        recon_data = get_bank_reconciliation_summary(self.bank_account, as_of_date=date(2026, 3, 31))

        self.assertIsNotNone(recon_data)
        self.assertEqual(recon_data['statement_ending_balance'], Decimal('0.00'))
        self.assertEqual(recon_data['unreconciled_deposits'], Decimal('50000.00'))
        self.assertEqual(recon_data['gl_ending_balance'], Decimal('50000.00'))
        self.assertEqual(recon_data['adjusted_gl_balance'], Decimal('50000.00'))
        self.assertEqual(recon_data['difference'], Decimal('0.00'))
        self.assertTrue(recon_data['is_balanced'])

        # 3. Scenario B: Bank statement now reflects the 50,000 deposit and is matched
        stmt.closing_balance = Decimal('50000.00')
        stmt.save(update_fields=['closing_balance'])

        stmt_line = BankStatementLine.objects.create(
            statement=stmt,
            date=date(2026, 3, 26),
            reference='DEPOSIT-01',
            description='Cash Banking',
            amount=Decimal('50000.00'),
            balance=Decimal('50000.00'),
            is_reconciled=True,
            matched_journal_line=gl_entry.lines.get(account_code='1030')
        )

        recon_data_cleared = get_bank_reconciliation_summary(self.bank_account, as_of_date=date(2026, 3, 31))
        self.assertEqual(recon_data_cleared['statement_ending_balance'], Decimal('50000.00'))
        self.assertEqual(recon_data_cleared['unreconciled_deposits'], Decimal('0.00'))
        self.assertEqual(recon_data_cleared['gl_ending_balance'], Decimal('50000.00'))
        self.assertEqual(recon_data_cleared['adjusted_gl_balance'], Decimal('50000.00'))
        self.assertEqual(recon_data_cleared['difference'], Decimal('0.00'))
        self.assertTrue(recon_data_cleared['is_balanced'])
