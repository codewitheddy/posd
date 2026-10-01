"""
Unit Tests for POS to Accounting General Ledger Integration
Tests automatic translation of Z-Reports into double-entry journals.
"""
from decimal import Decimal
from datetime import date, datetime, timezone as dt_timezone
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from core.models.organization import Company, Branch
from pos.models import Business, POSSession, ZReport, POSGLMapping, Sale, SalePayment, PaymentMethod
from pos.services.pos_accounting_service import POSAccountingService
from accounting.models import (
    Account, JournalEntry, JournalEntryStatus, JournalEntryType, PostingQueue
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year


class POSIntegrationTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Pwani Supermarket Ltd', slug='pwani-supermarket')
        self.branch = Branch.objects.create(company=self.company, name='Mombasa CBD', code='MSA')
        self.user = User.objects.create_user(username='cashier_ali', password='password123')
        
        # Seed Kenyan COA and 2026 Fiscal Year
        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

        # Create POS Business mapped to company
        self.business = Business.objects.create(name='Pwani Supermarket Ltd', owner=self.user)
        self.gl_mapping = POSGLMapping.get_for_business(self.business)

    def test_zreport_posts_balanced_double_entry_to_gl(self):
        """
        Test that a Z-report with Cash, M-Pesa, VAT, and Sales Revenue generates
        a balanced General Ledger journal entry with status POSTED.
        """
        session = POSSession.objects.create(
            business=self.business,
            opened_by=self.user,
            cashier=self.user,
            opening_cash=Decimal('5000.00'),
            status='closed',
            closed_at=timezone.now(),
            closed_by=self.user,
            closing_cash=Decimal('25000.00'),
            cash_difference=Decimal('0.00')
        )

        report_data = {
            'total_sales': '58000.00',
            'total_revenue': '58000.00',
            'total_tax': '8000.00',
            'net_sales': '50000.00',
            'payment_breakdown': {
                'CASH': '20000.00',
                'MPESA': '30000.00',
                'CARD': '8000.00',
            }
        }

        zreport = ZReport.objects.create(
            business=self.business,
            session=session,
            z_number=1,
            created_by=self.user,
            report_data=report_data,
            data_hash='dummyhash123',
            created_at=datetime(2026, 3, 10, 20, 0, 0, tzinfo=dt_timezone.utc)
        )

        entry = POSAccountingService.post_zreport_to_gl(zreport, user=self.user)

        self.assertIsNotNone(entry)
        self.assertIsInstance(entry, JournalEntry)
        self.assertEqual(entry.status, JournalEntryStatus.POSTED)
        self.assertEqual(entry.entry_type, JournalEntryType.SALES_CLOSE)
        self.assertEqual(entry.source_module, 'pos')
        self.assertEqual(entry.source_ref, 'ZREP-1')
        self.assertEqual(entry.total_amount, Decimal('58000.00'))

        # Check line breakdowns
        lines = {l.account_code: l for l in entry.lines.all()}
        
        # Debits
        self.assertEqual(lines['1010'].debit, Decimal('20000.00')) # Cash
        self.assertEqual(lines['1030'].debit, Decimal('30000.00')) # M-Pesa
        self.assertEqual(lines['1040'].debit, Decimal('8000.00'))  # Card

        # Credits
        self.assertEqual(lines['4000'].credit, Decimal('50000.00')) # Sales Net
        self.assertEqual(lines['2100'].credit, Decimal('8000.00'))  # VAT Output

    def test_zreport_with_cash_shortage(self):
        """
        Test cash drawer shortage: KES 500 short -> Dr Cash Shortage (6900), Cr Cash Till (1010).
        """
        session = POSSession.objects.create(
            business=self.business,
            opened_by=self.user,
            cashier=self.user,
            opening_cash=Decimal('5000.00'),
            status='closed',
            closed_at=timezone.now(),
            closed_by=self.user,
            closing_cash=Decimal('14500.00'),
            cash_difference=Decimal('-500.00')
        )

        report_data = {
            'total_sales': '10000.00',
            'total_tax': '0.00',
            'payment_breakdown': {
                'CASH': '10000.00',
            }
        }

        zreport = ZReport.objects.create(
            business=self.business,
            session=session,
            z_number=2,
            created_by=self.user,
            report_data=report_data,
            data_hash='dummyhash456',
            created_at=datetime(2026, 3, 10, 21, 0, 0, tzinfo=dt_timezone.utc)
        )

        entry = POSAccountingService.post_zreport_to_gl(zreport, user=self.user)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, JournalEntryStatus.POSTED)

        # Lines check: Cash Till net +9500, Shortage +500, Sales +10000
        shortage_line = entry.lines.filter(account_code='6900').first()
        self.assertIsNotNone(shortage_line)
        self.assertEqual(shortage_line.debit, Decimal('500.00'))

    def test_zreport_idempotency_prevents_duplicate_gl_postings(self):
        """Calling post_zreport_to_gl multiple times for the same Z-Report returns existing entry."""
        session = POSSession.objects.create(
            business=self.business,
            opened_by=self.user,
            cashier=self.user,
            opening_cash=Decimal('0.00'),
            status='closed',
            closed_at=timezone.now(),
            closed_by=self.user,
            closing_cash=Decimal('5000.00')
        )
        zreport = ZReport.objects.create(
            business=self.business,
            session=session,
            z_number=3,
            created_by=self.user,
            report_data={'total_sales': '5000.00', 'total_tax': '0.00', 'payment_breakdown': {'CASH': '5000.00'}},
            data_hash='hash789',
            created_at=datetime(2026, 3, 10, 22, 0, 0, tzinfo=dt_timezone.utc)
        )

        entry1 = POSAccountingService.post_zreport_to_gl(zreport, user=self.user)
        entry2 = POSAccountingService.post_zreport_to_gl(zreport, user=self.user)

        self.assertEqual(entry1.pk, entry2.pk)
        self.assertEqual(JournalEntry.objects.filter(company=self.company, source_ref='ZREP-3').count(), 1)

    def test_pos_gl_mapping_view_get_and_post(self):
        """Test GET and POST for /accounting/mappings/pos/"""
        self.client.force_login(self.user)
        response = self.client.get('/accounting/mappings/pos/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounting/mappings/pos_mapping.html')

        # Test POST
        post_data = {
            'cash_account_code': '1010',
            'mpesa_account_code': '1030',
            'card_account_code': '1040',
            'credit_account_code': '1100',
            'sales_revenue_code': '4000',
            'vat_output_code': '2100',
            'cogs_account_code': '5000',
            'inventory_account_code': '1200',
            'cash_variance_code': '6900',
        }
        post_resp = self.client.post('/accounting/mappings/pos/', data=post_data)
        self.assertEqual(post_resp.status_code, 302)

    def test_hr_gl_mapping_view_get_and_post(self):
        """Test GET and POST for /accounting/mappings/hr/"""
        self.client.force_login(self.user)
        response = self.client.get('/accounting/mappings/hr/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounting/mappings/hr_mapping.html')

        post_data = {
            'basic_salaries_expense_code': '6000',
            'employer_nssf_expense_code': '6030',
            'employer_shif_expense_code': '6030',
            'employer_housing_levy_expense_code': '6040',
            'employer_nita_expense_code': '6050',
            'net_salaries_payable_code': '2200',
            'paye_payable_code': '2110',
            'nssf_payable_code': '2120',
            'shif_payable_code': '2130',
            'housing_levy_payable_code': '2140',
            'helb_payable_code': '2150',
            'staff_advances_asset_code': '1310',
        }
        post_resp = self.client.post('/accounting/mappings/hr/', data=post_data)
        self.assertEqual(post_resp.status_code, 302)

    def test_pos_gl_mapping_view_auto_provisions_company_when_missing(self):
        """Test GET /accounting/mappings/pos/ when no Company exists in DB."""
        from core.models.organization import Company
        Company.objects.all().delete()
        self.client.force_login(self.user)
        response = self.client.get('/accounting/mappings/pos/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Company.objects.exists())



