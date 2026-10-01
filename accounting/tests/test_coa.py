"""
Unit Tests for Chart of Accounts (COA) & Seed Data
"""
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

from core.models.organization import Company
from accounting.models import (
    Account, AccountType, AccountCategory, NormalBalance,
    JournalEntry, JournalEntryLine, JournalEntryStatus
)
from accounting.seeders import seed_default_chart_of_accounts, KENYA_SME_DEFAULT_ACCOUNTS


class ChartOfAccountsTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Acme Kenya Ltd', slug='acme-kenya')
        self.user = User.objects.create_user(username='cfo_user', password='password123')

    def test_seed_default_kenyan_chart_of_accounts(self):
        """Test seeding the default Kenyan SME Chart of Accounts."""
        count = seed_default_chart_of_accounts(self.company)
        self.assertEqual(count, len(KENYA_SME_DEFAULT_ACCOUNTS))
        self.assertEqual(Account.objects.filter(company=self.company).count(), len(KENYA_SME_DEFAULT_ACCOUNTS))

        # Check key Kenyan system accounts
        cash_till = Account.objects.get(company=self.company, code='1010')
        self.assertEqual(cash_till.system_tag, 'cash_till')
        self.assertEqual(cash_till.normal_balance, NormalBalance.DEBIT)
        self.assertTrue(cash_till.is_system)

        vat_out = Account.objects.get(company=self.company, code='2100')
        self.assertEqual(vat_out.system_tag, 'vat_output')
        self.assertEqual(vat_out.normal_balance, NormalBalance.CREDIT)

        retained = Account.objects.get(company=self.company, code='3100')
        self.assertEqual(retained.system_tag, 'retained_earnings')

    def test_unique_code_per_company(self):
        """Verify that account codes are unique within the same company."""
        Account.objects.create(
            company=self.company,
            code='1010',
            name='Cash in Drawer',
            account_type=AccountType.ASSET,
            category=AccountCategory.CASH_AND_BANK,
        )

        with self.assertRaises(Exception):
            Account.objects.create(
                company=self.company,
                code='1010',
                name='Duplicate Cash',
                account_type=AccountType.ASSET,
                category=AccountCategory.CASH_AND_BANK,
            )

    def test_system_account_cannot_be_deleted(self):
        """Verify that system-protected accounts cannot be deleted."""
        acct = Account.objects.create(
            company=self.company,
            code='3100',
            name='Retained Earnings',
            account_type=AccountType.EQUITY,
            category=AccountCategory.RETAINED_EARNINGS,
            is_system=True
        )
        with self.assertRaises(ValidationError):
            acct.delete()

    def test_account_with_journal_lines_cannot_be_deleted(self):
        """Verify that accounts with posted transactions cannot be deleted."""
        acct = Account.objects.create(
            company=self.company,
            code='5000',
            name='Cost of Goods Sold',
            account_type=AccountType.EXPENSE,
            category=AccountCategory.COST_OF_SALES,
            is_system=False
        )
        entry = JournalEntry.objects.create(
            company=self.company,
            entry_number='JRN-TEST-001',
            narration='Test Entry',
            status=JournalEntryStatus.POSTED,
            total_amount=Decimal('1000.00')
        )
        JournalEntryLine.objects.create(
            entry=entry,
            account=acct,
            account_code=acct.code,
            account_name=acct.name,
            debit=Decimal('1000.00'),
            credit=Decimal('0.00')
        )

        with self.assertRaises(ValidationError):
            acct.delete()
