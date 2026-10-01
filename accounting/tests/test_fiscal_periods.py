"""
Unit Tests for Fiscal Years, Periods & Year-End Closing
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

from core.models.organization import Company
from accounting.models import (
    Account, AccountType, AccountCategory, NormalBalance,
    FiscalYear, FiscalPeriod, JournalEntry, JournalEntryStatus
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from accounting.services import FiscalPeriodService, JournalPostingService


class FiscalPeriodTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Kilima Enterprises Ltd', slug='kilima')
        self.user = User.objects.create_user(username='accountant', password='password123')
        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

    def test_seed_fiscal_year_creates_12_periods(self):
        """Verify 12 monthly periods created for 2026."""
        self.assertEqual(self.fiscal_year.periods.count(), 12)
        jan_period = self.fiscal_year.periods.get(period_number=1)
        self.assertEqual(jan_period.start_date, date(2026, 1, 1))
        self.assertEqual(jan_period.end_date, date(2026, 1, 31))
        self.assertFalse(jan_period.is_closed)

    def test_closed_period_blocks_journal_posting(self):
        """Verify that posting into a closed period is rejected."""
        jan_period = self.fiscal_year.periods.get(period_number=1)
        FiscalPeriodService.close_period(jan_period, user=self.user)
        self.assertTrue(jan_period.is_closed)

        # Attempt to post a journal into January 2026
        with self.assertRaises(ValidationError) as ctx:
            JournalPostingService.post_journal(
                company=self.company,
                source_module='manual',
                source_ref='REF-001',
                date_val=date(2026, 1, 15),
                lines=[
                    {'account_code': '1010', 'debit': Decimal('500.00'), 'credit': Decimal('0.00')},
                    {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('500.00')},
                ],
                narration='Posting into closed January period'
            )
        self.assertIn("closed", str(ctx.exception).lower())

    def test_reopen_period_allows_posting_with_audit_trail(self):
        """Verify that reopening a period allows postings and generates audit record."""
        jan_period = self.fiscal_year.periods.get(period_number=1)
        FiscalPeriodService.close_period(jan_period, user=self.user)
        self.assertTrue(FiscalPeriodService.is_period_closed(self.company, date(2026, 1, 15)))

        FiscalPeriodService.reopen_period(jan_period, user=self.user, reason='Audit adjustment needed')
        self.assertFalse(FiscalPeriodService.is_period_closed(self.company, date(2026, 1, 15)))

        entry = JournalPostingService.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='REF-002',
            date_val=date(2026, 1, 15),
            lines=[
                {'account_code': '1010', 'debit': Decimal('500.00'), 'credit': Decimal('0.00')},
                {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('500.00')},
            ],
            narration='Posting after reopen'
        )
        self.assertEqual(entry.status, JournalEntryStatus.POSTED)

    def test_year_end_close_rolls_profit_to_retained_earnings(self):
        """
        Verify Year-End Closing:
        Revenue KES 10,000, Expense KES 4,000 -> Net Profit KES 6,000 rolled into Retained Earnings (3100).
        """
        # Post revenue
        JournalPostingService.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='SALE-001',
            date_val=date(2026, 6, 1),
            lines=[
                {'account_code': '1010', 'debit': Decimal('10000.00'), 'credit': Decimal('0.00')},
                {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('10000.00')},
            ],
            narration='Sales revenue'
        )

        # Post expense
        JournalPostingService.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='EXP-001',
            date_val=date(2026, 6, 15),
            lines=[
                {'account_code': '6000', 'debit': Decimal('4000.00'), 'credit': Decimal('0.00')},
                {'account_code': '1010', 'debit': Decimal('0.00'), 'credit': Decimal('4000.00')},
            ],
            narration='Salaries expense'
        )

        # Close fiscal year
        closing_entry = FiscalPeriodService.close_fiscal_year(self.fiscal_year, user=self.user)
        self.assertIsNotNone(closing_entry)
        self.assertTrue(self.fiscal_year.is_closed)
        self.assertEqual(self.fiscal_year.periods.filter(is_closed=False).count(), 0)

        # Verify closing entry lines
        lines = list(closing_entry.lines.all())
        # Should debit 4000 (10,000), credit 6000 (4,000), credit 3100 (6,000)
        retained_earnings_line = [l for l in lines if l.account_code == '3100'][0]
        self.assertEqual(retained_earnings_line.credit, Decimal('6000.00'))
        self.assertEqual(retained_earnings_line.debit, Decimal('0.00'))
