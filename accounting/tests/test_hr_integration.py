"""
Unit Tests for HR & Payroll to Accounting General Ledger Integration
Tests automatic translation of monthly Payroll Runs into double-entry journals.
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth.models import User

from core.models.organization import Company, Branch
from pos.models import Business, Branch as POSBranch
from hr.models import Employee, Payroll, HRGLMapping
from hr.services import PayrollAccountingService
from accounting.models import (
    Account, JournalEntry, JournalEntryStatus, JournalEntryType, PostingQueue
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year


class HRIntegrationTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Lake Basin Tech Ltd', slug='lake-basin-tech')
        self.branch = Branch.objects.create(company=self.company, name='Kisumu HQ', code='KSM')
        self.user = User.objects.create_user(username='hr_officer', password='password123')
        
        # Seed Kenyan COA and 2026 Fiscal Year
        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

        # Create Business mapped to company
        self.business = Business.objects.create(name='Lake Basin Tech Ltd', owner=self.user)
        self.pos_branch = POSBranch.objects.create(business=self.business, name='Kisumu Main Branch')
        self.gl_mapping = HRGLMapping.get_for_business(self.business)

        # Create 2 employees
        self.emp1 = Employee.objects.create(
            business=self.business,
            branch=self.pos_branch,
            first_name='Otieno',
            last_name='Omondi',
            id_number='12345678',
            kra_pin='A012345678B',
            nssf_number='NSSF001',
            hire_date=date(2025, 1, 1),
            basic_salary=Decimal('80000.00'),
            house_allowance=Decimal('20000.00'),
        )

        self.emp2 = Employee.objects.create(
            business=self.business,
            branch=self.pos_branch,
            first_name='Achieng',
            last_name='Anyango',
            id_number='87654321',
            kra_pin='A987654321C',
            nssf_number='NSSF002',
            hire_date=date(2025, 3, 1),
            basic_salary=Decimal('50000.00'),
            house_allowance=Decimal('10000.00'),
        )

    def test_payroll_run_posts_balanced_journal_to_gl(self):
        """
        Verify that a monthly payroll run posts an auto-balancing journal:
        Gross Salaries (Dr 160,000) + Employer Contributions (Dr) = Net Pay (Cr) + Statutory Payables (Cr).
        """
        period_start = date(2026, 4, 1)
        period_end = date(2026, 4, 30)

        # Create Payroll records for both staff
        # Emp 1: Gross 100,000 (Basic 80k + House 20k)
        # Deductions: PAYE 20,000, SHIF 2,750, NSSF 2,160 (Empr 2,160), Housing Levy 1,500 (Empr 1,500), HELB 5,000, Advance 10,000
        # Net = 100,000 - 41,410 = 58,590
        p1 = Payroll.objects.create(
            employee=self.emp1,
            period_start=period_start,
            period_end=period_end,
            basic_salary=Decimal('80000.00'),
            house_allowance=Decimal('20000.00'),
            paye=Decimal('20000.00'),
            shif=Decimal('2750.00'),
            nssf=Decimal('2160.00'),
            housing_levy=Decimal('1500.00'),
            employer_nssf=Decimal('2160.00'),
            employer_housing_levy=Decimal('1500.00'),
            employer_nita=Decimal('50.00'),
            helb_deduction=Decimal('5000.00'),
            advances_deducted=Decimal('10000.00'),
            net_salary=Decimal('58590.00'),
            status='pending'
        )

        # Emp 2: Gross 60,000 (Basic 50k + House 10k)
        # Deductions: PAYE 10,000, SHIF 1,650, NSSF 2,160 (Empr 2,160), Housing Levy 900 (Empr 900)
        # Net = 60,000 - 14,710 = 45,290
        p2 = Payroll.objects.create(
            employee=self.emp2,
            period_start=period_start,
            period_end=period_end,
            basic_salary=Decimal('50000.00'),
            house_allowance=Decimal('10000.00'),
            paye=Decimal('10000.00'),
            shif=Decimal('1650.00'),
            nssf=Decimal('2160.00'),
            housing_levy=Decimal('900.00'),
            employer_nssf=Decimal('2160.00'),
            employer_housing_levy=Decimal('900.00'),
            employer_nita=Decimal('50.00'),
            helb_deduction=Decimal('0.00'),
            advances_deducted=Decimal('0.00'),
            net_salary=Decimal('45290.00'),
            status='pending'
        )

        entry = PayrollAccountingService.post_payroll_to_gl(
            business=self.business,
            period_start=period_start,
            period_end=period_end,
            user=self.user
        )

        self.assertIsNotNone(entry)
        self.assertEqual(entry.status, JournalEntryStatus.POSTED)
        self.assertEqual(entry.entry_type, JournalEntryType.PAYROLL)
        self.assertEqual(entry.source_module, 'hr')
        self.assertEqual(entry.date, period_end)

        lines = {l.account_code: l for l in entry.lines.all()}

        # 1. Debits (Expenses):
        # Gross = 100,000 + 60,000 = 160,000
        self.assertEqual(lines['6000'].debit, Decimal('160000.00'))
        # Empr NSSF = 2,160 + 2,160 = 4,320
        self.assertEqual(lines['6030'].debit, Decimal('4320.00'))
        # Empr Housing Levy = 1,500 + 900 = 2,400
        self.assertEqual(lines['6040'].debit, Decimal('2400.00'))
        # Empr NITA = 50 + 50 = 100
        self.assertEqual(lines['6050'].debit, Decimal('100.00'))

        # Total Debits = 160,000 + 4,320 + 2,400 + 100 = 166,820.00
        self.assertEqual(entry.total_amount, Decimal('166820.00'))

        # 2. Credits (Payables):
        # Net Salaries = 58,590 + 45,290 = 103,880
        self.assertEqual(lines['2200'].credit, Decimal('103880.00'))
        # PAYE = 20,000 + 10,000 = 30,000
        self.assertEqual(lines['2110'].credit, Decimal('30000.00'))
        # Total NSSF (Emp + Empr) = 4,320 + 4,320 = 8,640
        self.assertEqual(lines['2120'].credit, Decimal('8640.00'))
        # SHIF = 2,750 + 1,650 = 4,400
        self.assertEqual(lines['2130'].credit, Decimal('4400.00'))
        # Total Housing Levy (Emp + Empr) = 2,400 + 2,400 = 4,800
        self.assertEqual(lines['2140'].credit, Decimal('4800.00'))
        # HELB = 5,000
        self.assertEqual(lines['2150'].credit, Decimal('5000.00'))
        # Advances = 10,000
        self.assertEqual(lines['1310'].credit, Decimal('10000.00'))

    def test_payroll_idempotency_protection(self):
        """Re-submitting the same payroll period returns the existing journal entry without duplicates."""
        period_start = date(2026, 5, 1)
        period_end = date(2026, 5, 31)

        Payroll.objects.create(
            employee=self.emp1,
            period_start=period_start,
            period_end=period_end,
            basic_salary=Decimal('50000.00'),
            net_salary=Decimal('50000.00'),
        )

        entry1 = PayrollAccountingService.post_payroll_to_gl(
            business=self.business,
            period_start=period_start,
            period_end=period_end,
            user=self.user
        )

        entry2 = PayrollAccountingService.post_payroll_to_gl(
            business=self.business,
            period_start=period_start,
            period_end=period_end,
            user=self.user
        )

        self.assertEqual(entry1.pk, entry2.pk)
        self.assertEqual(JournalEntry.objects.filter(company=self.company, source_ref=f"PAYROLL-202605-{self.business.pk}").count(), 1)
