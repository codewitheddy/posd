"""
Accounting Views & Templates End-to-End Test Suite
Tests AR, AP, Banking, Kenyan Tax, and Financial Statements UI and CBVs.
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models.organization import Company, Branch, CompanyMembership
from accounting.models import (
    Account, AccountType, AccountCategory, NormalBalance,
    FiscalYear, FiscalPeriod,
    Customer, Vendor,
    CustomerInvoice, CustomerInvoiceLine, InvoiceStatus,
    CustomerPayment, CustomerPaymentAllocation,
    VendorBill, VendorBillLine, BillStatus,
    VendorPayment, VendorPaymentAllocation,
    BankAccount, BankStatement, BankStatementLine, BankReconciliation,
    WithholdingTaxRecord, WHTType, WHTCategory
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from accounting import api

User = get_user_model()


class AccountingViewsAndTemplatesTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name='Safari Highlands Retail Ltd', slug='safari-highlands')
        self.branch = Branch.objects.create(company=self.company, name='Nairobi West', code='NRB-W')
        self.user = User.objects.create_user(username='lead_accountant', password='password123')

        self.membership = CompanyMembership.objects.create(
            user=self.user,
            company=self.company,
            role=CompanyMembership.ROLE_ADMIN,
            is_active=True
        )

        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

        # Login and set session
        self.client.login(username='lead_accountant', password='password123')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()

        # Seed sample customer and vendor
        self.customer = Customer.objects.create(
            company=self.company,
            name='Acme Corporation Kenya',
            kra_pin='P051998877X',
            credit_limit=Decimal('500000.00'),
            created_by=self.user
        )

        self.vendor = Vendor.objects.create(
            company=self.company,
            name='Kenya Power & Lighting Co',
            kra_pin='P051112233A',
            payment_terms_days=15,
            created_by=self.user
        )

        self.bank_gl = Account.objects.get(company=self.company, code='1010')
        self.bank_account = BankAccount.objects.create(
            company=self.company,
            name='KCB Operating Account',
            bank_name='KCB Bank Kenya',
            account_number='1122334455',
            gl_account=self.bank_gl,
            created_by=self.user
        )

    # ─── Accounts Receivable Views ──────────────────────────────────────────

    def test_customer_list_and_create_views(self):
        # List View
        resp = self.client.get(reverse('accounting_customer_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Acme Corporation Kenya')
        self.assertContains(resp, 'P051998877X')

        # Create View GET
        resp_get = self.client.get(reverse('accounting_customer_create'))
        self.assertEqual(resp_get.status_code, 200)

        # Create View POST
        resp_post = self.client.post(reverse('accounting_customer_create'), {
            'name': 'Kilifi Supermarket Ltd',
            'kra_pin': 'P051445566Z',
            'email': 'accounts@kilifi.co.ke',
            'phone': '+254711223344',
            'payment_terms_days': 45,
            'credit_limit': '250000.00',
            'address': 'Mombasa Road, Kilifi'
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(Customer.objects.filter(company=self.company, name='Kilifi Supermarket Ltd').exists())

    def test_customer_invoice_lifecycle_views(self):
        # Create Draft Invoice
        inv = CustomerInvoice.objects.create(
            company=self.company,
            customer=self.customer,
            invoice_number='INV-2026-TEST-001',
            invoice_date=date(2026, 3, 1),
            due_date=date(2026, 3, 31),
            status=InvoiceStatus.DRAFT,
            subtotal=Decimal('100000.00'),
            tax_amount=Decimal('16000.00'),
            total_amount=Decimal('116000.00'),
            balance_due=Decimal('116000.00'),
            created_by=self.user
        )
        rev_acct = Account.objects.get(company=self.company, code='4000')
        CustomerInvoiceLine.objects.create(
            invoice=inv,
            account=rev_acct,
            description='Consulting Services',
            quantity=Decimal('1.00'),
            unit_price=Decimal('100000.00'),
            tax_rate=Decimal('16.00'),
            tax_amount=Decimal('16000.00'),
            line_total=Decimal('116000.00')
        )

        # Invoice List View
        resp_list = self.client.get(reverse('accounting_invoice_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, 'INV-2026-TEST-001')

        # Invoice Detail View
        resp_detail = self.client.get(reverse('accounting_invoice_detail', kwargs={'pk': inv.pk}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, 'Consulting Services')
        self.assertContains(resp_detail, 'Post to General Ledger')

        # Post Invoice to GL View
        resp_post = self.client.post(reverse('accounting_invoice_post', kwargs={'pk': inv.pk}))
        self.assertEqual(resp_post.status_code, 302)
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.POSTED)
        self.assertIsNotNone(inv.journal_entry)

    def test_customer_payment_create_and_list_views(self):
        resp_get = self.client.get(reverse('accounting_customer_payment_create'))
        self.assertEqual(resp_get.status_code, 200)

        resp_post = self.client.post(reverse('accounting_customer_payment_create'), {
            'customer': self.customer.pk,
            'branch': self.branch.pk,
            'receipt_number': 'REC-2026-TEST-001',
            'payment_date': '2026-03-05',
            'amount': '50000.00',
            'payment_method': 'mpesa',
            'reference': 'QHD123456X',
            'deposit_account': self.bank_gl.pk,
            'notes': 'M-Pesa payment from customer'
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(CustomerPayment.objects.filter(company=self.company, receipt_number='REC-2026-TEST-001').exists())

        # List View
        resp_list = self.client.get(reverse('accounting_customer_payment_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, 'REC-2026-TEST-001')

    def test_ar_aging_report_view(self):
        resp = self.client.get(reverse('accounting_ar_aging_report') + '?as_of_date=2026-03-31')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Accounts Receivable Aging Schedule')
        self.assertContains(resp, 'Total Outstanding')

    # ─── Accounts Payable Views ─────────────────────────────────────────────

    def test_vendor_list_and_create_views(self):
        # List View
        resp = self.client.get(reverse('accounting_vendor_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Kenya Power &amp; Lighting Co')

        # Create View GET
        resp_get = self.client.get(reverse('accounting_vendor_create'))
        self.assertEqual(resp_get.status_code, 200)

        # Create View POST
        resp_post = self.client.post(reverse('accounting_vendor_create'), {
            'name': 'Nairobi Water and Sewerage Co',
            'kra_pin': 'P051778899B',
            'email': 'info@nairobiwater.co.ke',
            'phone': '+254700112233',
            'payment_terms_days': 30,
            'address': 'Kampala Road, Industrial Area'
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(Vendor.objects.filter(company=self.company, name='Nairobi Water and Sewerage Co').exists())

    def test_vendor_bill_lifecycle_views(self):
        # Create Draft Bill
        bill = VendorBill.objects.create(
            company=self.company,
            vendor=self.vendor,
            bill_number='BILL-2026-TEST-001',
            supplier_invoice_number='KPLC-INV-8899',
            bill_date=date(2026, 3, 2),
            due_date=date(2026, 3, 17),
            status=BillStatus.DRAFT,
            subtotal=Decimal('40000.00'),
            tax_amount=Decimal('6400.00'),
            total_amount=Decimal('46400.00'),
            balance_due=Decimal('46400.00'),
            created_by=self.user
        )
        util_acct = Account.objects.get(company=self.company, code='6110')
        VendorBillLine.objects.create(
            bill=bill,
            account=util_acct,
            description='Electricity Monthly Charges',
            quantity=Decimal('1.00'),
            unit_price=Decimal('40000.00'),
            tax_rate=Decimal('16.00'),
            tax_amount=Decimal('6400.00'),
            line_total=Decimal('46400.00')
        )

        # Bill List View
        resp_list = self.client.get(reverse('accounting_bill_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, 'BILL-2026-TEST-001')

        # Bill Detail View
        resp_detail = self.client.get(reverse('accounting_bill_detail', kwargs={'pk': bill.pk}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, 'Electricity Monthly Charges')
        self.assertContains(resp_detail, 'Post to General Ledger')

        # Post Bill to GL View
        resp_post = self.client.post(reverse('accounting_bill_post', kwargs={'pk': bill.pk}))
        self.assertEqual(resp_post.status_code, 302)
        bill.refresh_from_db()
        self.assertEqual(bill.status, BillStatus.POSTED)
        self.assertIsNotNone(bill.journal_entry)

    def test_vendor_payment_create_and_list_views(self):
        resp_get = self.client.get(reverse('accounting_vendor_payment_create'))
        self.assertEqual(resp_get.status_code, 200)

        resp_post = self.client.post(reverse('accounting_vendor_payment_create'), {
            'vendor': self.vendor.pk,
            'branch': self.branch.pk,
            'voucher_number': 'VOUCH-2026-TEST-001',
            'payment_date': '2026-03-08',
            'amount': '30000.00',
            'payment_method': 'bank',
            'reference': 'EFT-889911',
            'paid_from_account': self.bank_gl.pk,
            'notes': 'EFT settlement for utilities'
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(VendorPayment.objects.filter(company=self.company, voucher_number='VOUCH-2026-TEST-001').exists())

        # List View
        resp_list = self.client.get(reverse('accounting_vendor_payment_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, 'VOUCH-2026-TEST-001')

    def test_ap_aging_report_view(self):
        resp = self.client.get(reverse('accounting_ap_aging_report') + '?as_of_date=2026-03-31')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Accounts Payable Aging Schedule')
        self.assertContains(resp, 'Total Payables')

    # ─── Banking & Reconciliation Views ──────────────────────────────────────

    def test_banking_views(self):
        # Account List View
        resp_list = self.client.get(reverse('accounting_bank_account_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, 'KCB Operating Account')

        # Account Create View
        resp_create_get = self.client.get(reverse('accounting_bank_account_create'))
        self.assertEqual(resp_create_get.status_code, 200)

        till_gl = Account.objects.get(company=self.company, code='1030')
        resp_create_post = self.client.post(reverse('accounting_bank_account_create'), {
            'name': 'M-Pesa Buy Goods Till 123456',
            'bank_name': 'Safaricom M-Pesa',
            'account_number': '123456',
            'gl_account': till_gl.pk,
            'branch_name': 'Main Branch'
        })
        self.assertEqual(resp_create_post.status_code, 302)

        # Account Detail View
        resp_detail = self.client.get(reverse('accounting_bank_account_detail', kwargs={'pk': self.bank_account.pk}))
        self.assertEqual(resp_detail.status_code, 200)
        self.assertContains(resp_detail, 'KCB Operating Account')

        # Statement Import View GET
        resp_import_get = self.client.get(reverse('accounting_bank_statement_import', kwargs={'pk': self.bank_account.pk}))
        self.assertEqual(resp_import_get.status_code, 200)

        # Statement Import View POST (Bank CSV)
        csv_data = "Date,Reference,Description,Debit,Credit,Balance\n2026-03-10,FT001,Deposit,,100000.00,100000.00\n"
        csv_file = SimpleUploadedFile("statement.csv", csv_data.encode('utf-8'), content_type="text/csv")
        resp_import_post = self.client.post(reverse('accounting_bank_statement_import', kwargs={'pk': self.bank_account.pk}), {
            'statement_type': 'bank',
            'csv_file': csv_file
        })
        self.assertEqual(resp_import_post.status_code, 302)
        stmt = BankStatement.objects.filter(bank_account=self.bank_account).first()
        self.assertIsNotNone(stmt)

        # Reconcile Action View
        resp_recon = self.client.post(reverse('accounting_bank_statement_reconcile', kwargs={'pk': stmt.pk}))
        self.assertEqual(resp_recon.status_code, 302)

        # Reconciliation Report View
        resp_recon_report = self.client.get(reverse('accounting_bank_reconciliation_report', kwargs={'pk': self.bank_account.pk}))
        self.assertEqual(resp_recon_report.status_code, 200)
        self.assertContains(resp_recon_report, 'Bank Reconciliation Schedule')

    # ─── Kenyan Tax Views ───────────────────────────────────────────────────

    def test_kenyan_tax_views(self):
        # Post a transaction with standard sales
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='TAX-TEST-01',
            date_val=date(2026, 3, 15),
            lines=[
                {'account_code': '1010', 'debit': '116000.00', 'credit': '0.00'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '100000.00'},
                {'account_code': '2100', 'debit': '0.00', 'credit': '16000.00'},
            ],
            auto_approve=True
        )

        # Create WHT Record
        WithholdingTaxRecord.objects.create(
            company=self.company,
            wht_type=WHTType.PAYABLE,
            category=WHTCategory.MANAGEMENT_PROFESSIONAL,
            rate_percentage=Decimal('5.00'),
            base_amount=Decimal('100000.00'),
            tax_amount=Decimal('5000.00'),
            party_name='Legal & Advisory Associates',
            party_pin='P051887766M',
            transaction_date=date(2026, 3, 20),
            created_by=self.user
        )

        # VAT Return Schedule View
        resp_vat = self.client.get(reverse('accounting_vat_return') + '?start_date=2026-03-01&end_date=2026-03-31')
        self.assertEqual(resp_vat.status_code, 200)
        self.assertContains(resp_vat, 'VAT Return Schedule (Form VAT 3)')
        self.assertContains(resp_vat, 'General Rated Sales (16%)')

        # VAT Sales CSV Export
        resp_vat_sales = self.client.get(reverse('accounting_vat_sales_csv') + '?start_date=2026-03-01&end_date=2026-03-31')
        self.assertEqual(resp_vat_sales.status_code, 200)
        self.assertEqual(resp_vat_sales['Content-Type'], 'text/csv')

        # VAT Purchases CSV Export
        resp_vat_purchases = self.client.get(reverse('accounting_vat_purchases_csv') + '?start_date=2026-03-01&end_date=2026-03-31')
        self.assertEqual(resp_vat_purchases.status_code, 200)
        self.assertEqual(resp_vat_purchases['Content-Type'], 'text/csv')

        # WHT Schedule View
        resp_wht = self.client.get(reverse('accounting_wht_schedule') + '?start_date=2026-03-01&end_date=2026-03-31')
        self.assertEqual(resp_wht.status_code, 200)
        self.assertContains(resp_wht, 'Withholding Tax Schedule')
        self.assertContains(resp_wht, 'Legal &amp; Advisory Associates')

        # WHT CSV Export
        resp_wht_csv = self.client.get(reverse('accounting_wht_csv') + '?start_date=2026-03-01&end_date=2026-03-31')
        self.assertEqual(resp_wht_csv.status_code, 200)
        self.assertEqual(resp_wht_csv['Content-Type'], 'text/csv')

    # ─── Financial Statements Views ─────────────────────────────────────────

    def test_financial_statements_views(self):
        # Post activity
        api.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='FS-REV-01',
            date_val=date(2026, 3, 1),
            lines=[
                {'account_code': '1010', 'debit': '300000.00', 'credit': '0.00'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '300000.00'},
            ],
            auto_approve=True
        )
        api.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='FS-EXP-01',
            date_val=date(2026, 3, 5),
            lines=[
                {'account_code': '6100', 'debit': '50000.00', 'credit': '0.00'},
                {'account_code': '1010', 'debit': '0.00', 'credit': '50000.00'},
            ],
            auto_approve=True
        )

        # Income Statement View
        resp_is = self.client.get(reverse('accounting_income_statement') + '?start_date=2026-03-01&end_date=2026-03-31')
        self.assertEqual(resp_is.status_code, 200)
        self.assertContains(resp_is, 'Income Statement (Profit &amp; Loss)')
        self.assertContains(resp_is, 'GROSS PROFIT')
        self.assertContains(resp_is, 'OPERATING PROFIT / EBIT')
        self.assertContains(resp_is, 'NET PROFIT / (LOSS) FOR THE PERIOD')

        # Balance Sheet View
        resp_bs = self.client.get(reverse('accounting_balance_sheet') + '?as_of_date=2026-03-31')
        self.assertEqual(resp_bs.status_code, 200)
        self.assertContains(resp_bs, 'Balance Sheet')
        self.assertContains(resp_bs, 'Statement of Financial Position')
        self.assertContains(resp_bs, 'Perfect Mathematical Equilibrium')

        # Cash Flow Statement View
        resp_cf = self.client.get(reverse('accounting_cash_flow_statement') + '?start_date=2026-03-01&end_date=2026-03-31')
        self.assertEqual(resp_cf.status_code, 200)
        self.assertContains(resp_cf, 'Cash Flow Statement')
        self.assertContains(resp_cf, 'CASH FLOWS FROM OPERATING ACTIVITIES')
        self.assertContains(resp_cf, 'CASH &amp; CASH EQUIVALENTS AT END OF PERIOD')
