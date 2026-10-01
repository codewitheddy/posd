"""
Kenyan Tax Engine Test Suite (KRA Form VAT 3, WHT, iTax CSV Exporters)
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model

from core.models.organization import Company, Branch
from accounting.models import (
    Account, Customer, Vendor,
    CustomerInvoice, CustomerInvoiceLine, InvoiceStatus,
    VendorBill, VendorBillLine, BillStatus,
    WithholdingTaxRecord, WHTType, WHTCategory
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from accounting import api

User = get_user_model()


class KenyanTaxEngineTests(TestCase):
    """
    Tests Kenyan VAT Return Schedule (Form VAT 3),
    Withholding Tax Schedules (WHT 5%, 3%, 10%, 2%),
    and KRA iTax CSV batch upload exporters.
    """

    def setUp(self):
        self.company = Company.objects.create(
            name="Marid Enterprises Limited",
            slug="marid-ent"
        )
        self.branch = Branch.objects.create(
            company=self.company,
            name="CBD Branch",
            code="CBD-01"
        )
        self.user = User.objects.create_user(
            username='taxaccountant',
            email='tax@marid.co.ke',
            password='password123'
        )

        seed_default_chart_of_accounts(self.company)
        seed_fiscal_year(self.company, year=2026)

        self.revenue_gl = Account.objects.get(company=self.company, code='4000')
        self.expense_gl = Account.objects.get(company=self.company, code='6100')
        self.vat_output_gl = Account.objects.get(company=self.company, code='2100')
        self.vat_input_gl = Account.objects.get(company=self.company, code='1400')

    def test_vat_return_form_vat_3_calculation(self):
        """
        Test KRA Form VAT 3 Return calculation with Standard 16%, Zero Rated,
        Input VAT claims, and WHVAT 2% credits.
        """
        # 1. Customer Invoices (Sales)
        cust_corp = Customer.objects.create(
            company=self.company,
            name="Safaricom PLC",
            kra_pin="P051112233Z"
        )
        cust_export = Customer.objects.create(
            company=self.company,
            name="Uganda Tea Exporters Ltd",
            kra_pin="P059998887Y"
        )

        # Invoice 1: Standard Rated Sales: KES 100,000 + 16% VAT = KES 116,000
        inv1 = CustomerInvoice.objects.create(
            company=self.company,
            branch=self.branch,
            customer=cust_corp,
            invoice_number="INV-2026-001",
            invoice_date=date(2026, 3, 5),
            due_date=date(2026, 3, 20),
            status=InvoiceStatus.DRAFT
        )
        CustomerInvoiceLine.objects.create(
            invoice=inv1,
            account=self.revenue_gl,
            description="ERP Software Consultation",
            quantity=Decimal('1.00'),
            unit_price=Decimal('100000.00'),
            tax_rate=Decimal('16.00')
        )
        api.post_customer_invoice(inv1, user=self.user)

        # Invoice 2: Zero Rated Sales: KES 50,000 (0% VAT)
        inv2 = CustomerInvoice.objects.create(
            company=self.company,
            branch=self.branch,
            customer=cust_export,
            invoice_number="INV-2026-002",
            invoice_date=date(2026, 3, 10),
            due_date=date(2026, 3, 25),
            status=InvoiceStatus.DRAFT
        )
        CustomerInvoiceLine.objects.create(
            invoice=inv2,
            account=self.revenue_gl,
            description="Export Consultancy",
            quantity=Decimal('1.00'),
            unit_price=Decimal('50000.00'),
            tax_rate=Decimal('0.00')
        )
        api.post_customer_invoice(inv2, user=self.user)

        # 2. Vendor Bills (Purchases / Input VAT)
        vend = Vendor.objects.create(
            company=self.company,
            name="Kenya Power & Lighting Co",
            kra_pin="P051100223A"
        )
        # Bill 1: Electricity KES 30,000 + 16% VAT (KES 4,800) = KES 34,800
        bill1 = VendorBill.objects.create(
            company=self.company,
            branch=self.branch,
            vendor=vend,
            bill_number="BILL-2026-001",
            supplier_invoice_number="KPLC-MAR-2026",
            bill_date=date(2026, 3, 12),
            due_date=date(2026, 3, 28),
            status=BillStatus.DRAFT
        )
        VendorBillLine.objects.create(
            bill=bill1,
            account=self.expense_gl,
            description="CBD Office Electricity Bill",
            quantity=Decimal('1.00'),
            unit_price=Decimal('30000.00'),
            tax_rate=Decimal('16.00')
        )
        api.post_vendor_bill(bill1, user=self.user)

        # 3. Withholding VAT Credit (2% on KES 100,000 = KES 2,000 withheld by Safaricom)
        api.record_withholding_tax(
            company=self.company,
            wht_type=WHTType.RECEIVABLE,
            category=WHTCategory.WITHHOLDING_VAT,
            party_name=cust_corp.name,
            party_pin=cust_corp.kra_pin,
            transaction_date=date(2026, 3, 15),
            base_amount=Decimal('100000.00'),
            rate_percentage=Decimal('2.00'),
            certificate_number="WHVAT-2026-00982",
            customer_invoice=inv1,
            user=self.user
        )

        # 4. Generate VAT Return for March 2026
        vat_return = api.get_vat_return(
            company=self.company,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31)
        )

        self.assertIsNotNone(vat_return)
        sales = vat_return['sales']
        purchases = vat_return['purchases']
        summary = vat_return['summary']

        # Sales Assertions
        self.assertEqual(sales['standard_16_taxable'], Decimal('100000.00'))
        self.assertEqual(sales['zero_rated'], Decimal('50000.00'))
        self.assertEqual(sales['output_vat'], Decimal('16000.00'))

        # Purchases Assertions
        self.assertEqual(purchases['standard_16_taxable'], Decimal('30000.00'))
        self.assertEqual(purchases['input_vat'], Decimal('4800.00'))

        # WHVAT & Net VAT Assertions:
        # Total Output VAT: 16,000.00
        # Less Input VAT: 4,800.00
        # Less WHVAT Credits: 2,000.00
        # Net VAT Payable = 16,000 - 4,800 - 2,000 = 9,200.00
        self.assertEqual(summary['total_output_vat'], Decimal('16000.00'))
        self.assertEqual(summary['total_input_vat'], Decimal('4800.00'))
        self.assertEqual(summary['whvat_credits'], Decimal('2000.00'))
        self.assertEqual(summary['net_vat_payable'], Decimal('9200.00'))
        self.assertTrue(summary['is_payable'])

    def test_withholding_tax_schedules(self):
        """Test recording various WHT categories (5% Management, 10% Rent, 2% WHVAT)."""
        # Record 5% WHT on Audit Fees
        wht_audit = api.record_withholding_tax(
            company=self.company,
            wht_type=WHTType.PAYABLE,
            category=WHTCategory.MANAGEMENT_PROFESSIONAL,
            party_name="PKF Kenya LLP",
            party_pin="P050011223K",
            transaction_date=date(2026, 3, 10),
            base_amount=Decimal('200000.00'),
            rate_percentage=Decimal('5.00'),
            certificate_number="WHT-AUD-001",
            user=self.user
        )
        self.assertEqual(wht_audit.tax_amount, Decimal('10000.00'))

        # Record 10% WHT on Office Rent
        wht_rent = api.record_withholding_tax(
            company=self.company,
            wht_type=WHTType.PAYABLE,
            category=WHTCategory.RENT,
            party_name="Nairobi Heights Ltd",
            party_pin="P058887771B",
            transaction_date=date(2026, 3, 15),
            base_amount=Decimal('150000.00'),
            rate_percentage=Decimal('10.00'),
            certificate_number="WHT-RENT-001",
            user=self.user
        )
        self.assertEqual(wht_rent.tax_amount, Decimal('15000.00'))

        # Fetch WHT summary
        wht_summary = api.get_wht_return(
            company=self.company,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            wht_type=WHTType.PAYABLE
        )
        self.assertEqual(wht_summary['total_base_amount'], Decimal('350000.00'))
        self.assertEqual(wht_summary['total_tax_amount'], Decimal('25000.00'))
        self.assertEqual(len(wht_summary['categories']), 2)

    def test_kra_itax_csv_exporters(self):
        """Test CSV format generation for KRA iTax batch upload."""
        cust = Customer.objects.create(
            company=self.company,
            name="Acme Corporation",
            kra_pin="P051239999Z"
        )
        inv = CustomerInvoice.objects.create(
            company=self.company,
            branch=self.branch,
            customer=cust,
            invoice_number="INV-ITAX-01",
            invoice_date=date(2026, 3, 20),
            due_date=date(2026, 4, 5),
            status=InvoiceStatus.DRAFT
        )
        CustomerInvoiceLine.objects.create(
            invoice=inv,
            account=self.revenue_gl,
            description="Hardware Installation Services",
            quantity=Decimal('2.00'),
            unit_price=Decimal('25000.00'),
            tax_rate=Decimal('16.00')
        )
        api.post_customer_invoice(inv, user=self.user)

        # 1. Export Sales CSV
        sales_csv = api.export_itax_vat_sales_csv(
            company=self.company,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31)
        )
        self.assertIn("PIN of Customer", sales_csv)
        self.assertIn("P051239999Z", sales_csv)
        self.assertIn("INV-ITAX-01", sales_csv)
        self.assertIn("50000.00", sales_csv)
        self.assertIn("8000.00", sales_csv)

        # 2. Export WHT CSV
        api.record_withholding_tax(
            company=self.company,
            wht_type=WHTType.PAYABLE,
            category=WHTCategory.MANAGEMENT_PROFESSIONAL,
            party_name="Expert Advisors",
            party_pin="P057771112A",
            transaction_date=date(2026, 3, 22),
            base_amount=Decimal('40000.00'),
            rate_percentage=Decimal('5.00'),
            certificate_number="WHT-CERT-99",
            user=self.user
        )
        wht_csv = api.export_itax_wht_csv(
            company=self.company,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31)
        )
        self.assertIn("PIN of Payee", wht_csv)
        self.assertIn("P057771112A", wht_csv)
        self.assertIn("40000.00", wht_csv)
        self.assertIn("2000.00", wht_csv)
