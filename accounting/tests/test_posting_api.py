"""
Unit Tests for Accounting Public Posting API & Reversals
Enforces strict double-entry invariants, idempotency, and validations.
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

from core.models.organization import Company, Branch
from accounting.models import (
    Account, AccountType, AccountCategory, NormalBalance,
    JournalEntry, JournalEntryLine, JournalEntryStatus, JournalEntryType,
    PostingQueue
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from accounting import api


class PostingApiTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Safari Motors Ltd', slug='safari-motors')
        self.branch = Branch.objects.create(company=self.company, name='Nairobi HQ', code='NBO')
        self.user = User.objects.create_user(username='accountant_jane', password='securepass123')
        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

    def test_successful_double_entry_posting(self):
        """Test valid 2-legged balanced journal posting via public API."""
        lines = [
            {'account_code': '1010', 'debit': Decimal('15000.00'), 'credit': Decimal('0.00'), 'description': 'Cash from sales'},
            {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('15000.00'), 'description': 'Daily Sales'},
        ]
        entry = api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='POS-TXN-001',
            date_val=date(2026, 3, 10),
            lines=lines,
            narration='Daily POS Sales Cash Register',
            posted_by=self.user,
            branch=self.branch,
        )

        self.assertIsNotNone(entry.pk)
        self.assertEqual(entry.status, JournalEntryStatus.POSTED)
        self.assertEqual(entry.total_amount, Decimal('15000.00'))
        self.assertTrue(entry.entry_number.startswith('JRN-'))
        self.assertEqual(entry.lines.count(), 2)

        # Verify line items snapshot account names & codes
        line_cash = entry.lines.get(account_code='1010')
        self.assertEqual(line_cash.debit, Decimal('15000.00'))
        self.assertEqual(line_cash.credit, Decimal('0.00'))
        self.assertEqual(line_cash.account_name, 'Cash in Till / Cash Drawer')

        line_sales = entry.lines.get(account_code='4000')
        self.assertEqual(line_sales.credit, Decimal('15000.00'))
        self.assertEqual(line_sales.debit, Decimal('0.00'))

    def test_unbalanced_journal_rejected(self):
        """Verify that unbalanced transactions are strictly rejected with ValidationError."""
        lines = [
            {'account_code': '1010', 'debit': Decimal('10000.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('8500.00')},
        ]
        with self.assertRaises(ValidationError) as ctx:
            api.post_journal(
                company=self.company,
                source_module='pos',
                source_ref='POS-UNBALANCED-01',
                date_val=date(2026, 3, 10),
                lines=lines,
                narration='Unbalanced sales attempt'
            )
        self.assertIn("unbalanced", str(ctx.exception).lower())

    def test_zero_amount_line_rejected(self):
        """Verify that lines with both zero debit and zero credit are rejected."""
        lines = [
            {'account_code': '1010', 'debit': Decimal('0.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('0.00')},
        ]
        with self.assertRaises(ValidationError) as ctx:
            api.post_journal(
                company=self.company,
                source_module='manual',
                source_ref='ZERO-01',
                date_val=date(2026, 3, 10),
                lines=lines,
                narration='Zero amount test'
            )
        self.assertIn("non-zero debit or credit", str(ctx.exception).lower())

    def test_negative_amounts_rejected(self):
        """Verify that negative amounts in lines are strictly prohibited."""
        lines = [
            {'account_code': '1010', 'debit': Decimal('-500.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('-500.00')},
        ]
        with self.assertRaises(ValidationError) as ctx:
            api.post_journal(
                company=self.company,
                source_module='manual',
                source_ref='NEG-01',
                date_val=date(2026, 3, 10),
                lines=lines,
                narration='Negative test'
            )
        self.assertIn("cannot be negative", str(ctx.exception).lower())

    def test_minimum_two_lines_required(self):
        """Single-line entry must be rejected (double-entry invariant)."""
        lines = [
            {'account_code': '1010', 'debit': Decimal('1000.00'), 'credit': Decimal('0.00')},
        ]
        with self.assertRaises(ValidationError) as ctx:
            api.post_journal(
                company=self.company,
                source_module='manual',
                source_ref='SINGLE-01',
                date_val=date(2026, 3, 10),
                lines=lines,
                narration='Single line'
            )
        self.assertIn("at least two", str(ctx.exception).lower())

    def test_idempotency_key_prevents_duplicate_posting(self):
        """Submitting the same idempotency key twice returns the existing entry without re-posting."""
        idempotency_key = "pos:shift_z:branch_1:2026-03-10:001"
        lines = [
            {'account_code': '1010', 'debit': Decimal('5000.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('5000.00')},
        ]

        entry1 = api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='Z-REPORT-001',
            date_val=date(2026, 3, 10),
            lines=lines,
            narration='Z-Report Shift 1',
            idempotency_key=idempotency_key
        )

        entry2 = api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='Z-REPORT-001',
            date_val=date(2026, 3, 10),
            lines=lines,
            narration='Z-Report Shift 1 duplicate call',
            idempotency_key=idempotency_key
        )

        # Must return the identical JournalEntry
        self.assertEqual(entry1.pk, entry2.pk)
        self.assertEqual(JournalEntry.objects.filter(company=self.company, idempotency_key=idempotency_key).count(), 1)

    def test_journal_reversal(self):
        """Test reversing a posted journal generates exact countervailing entry and sets status."""
        lines = [
            {'account_code': '1010', 'debit': Decimal('7500.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('7500.00')},
        ]
        original_entry = api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='SALE-REV-01',
            date_val=date(2026, 3, 10),
            lines=lines,
            narration='Erroneous duplicate sale',
            posted_by=self.user
        )

        reversal = api.reverse_journal(
            entry=original_entry,
            reversed_by=self.user,
            reason='Customer cancelled order immediately',
            date_val=date(2026, 3, 10)
        )

        original_entry.refresh_from_db()
        self.assertEqual(original_entry.status, JournalEntryStatus.REVERSED)
        self.assertEqual(original_entry.reversal_entry, reversal)
        self.assertEqual(original_entry.reversal_reason, 'Customer cancelled order immediately')

        self.assertEqual(reversal.status, JournalEntryStatus.POSTED)
        self.assertEqual(reversal.entry_type, JournalEntryType.REVERSING)
        self.assertEqual(reversal.total_amount, Decimal('7500.00'))

        # Check that debits and credits were inverted
        rev_cash_line = reversal.lines.get(account_code='1010')
        self.assertEqual(rev_cash_line.debit, Decimal('0.00'))
        self.assertEqual(rev_cash_line.credit, Decimal('7500.00'))

        rev_sales_line = reversal.lines.get(account_code='4000')
        self.assertEqual(rev_sales_line.debit, Decimal('7500.00'))
        self.assertEqual(rev_sales_line.credit, Decimal('0.00'))

    def test_cannot_reverse_already_reversed_entry(self):
        """Attempting to reverse an already reversed journal must raise ValidationError."""
        lines = [
            {'account_code': '1010', 'debit': Decimal('1000.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('1000.00')},
        ]
        original_entry = api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='SALE-REV-02',
            date_val=date(2026, 3, 10),
            lines=lines,
            narration='Sale to reverse'
        )

        api.reverse_journal(entry=original_entry, reversed_by=self.user, reason='First reversal')

        with self.assertRaises(ValidationError) as ctx:
            api.reverse_journal(entry=original_entry, reversed_by=self.user, reason='Second reversal')
        self.assertIn("already reversed", str(ctx.exception).lower())

    def test_queue_posting(self):
        """Verify queue_posting creates a PostingQueue record and processes it."""
        payload = {
            'source_module': 'pos',
            'source_ref': 'POS-QUEUE-01',
            'date': '2026-03-10',
            'narration': 'Queued POS Sync',
            'lines': [
                {'account_code': '1010', 'debit': '3000.00', 'credit': '0.00'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '3000.00'},
            ]
        }
        queue_item = api.queue_posting(
            company=self.company,
            payload=payload,
            idempotency_key='queue:pos:001',
            process_immediately=True
        )

        self.assertEqual(queue_item.status, PostingQueue.STATUS_PROCESSED)
        self.assertIsNotNone(queue_item.created_journal_entry)
        self.assertEqual(queue_item.created_journal_entry.total_amount, Decimal('3000.00'))
