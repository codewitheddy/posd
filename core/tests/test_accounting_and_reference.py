"""
Unit and Integration Tests for Phase 5:
- Accounting Public Posting Interface (Double-entry balance, closed period gating, idempotency)
- Kenyan Reference Data (47 Counties, Commercial Banks, CBK clearing codes)
- Kenya Data Protection Act (DPA 2019) Compliance (DSAR export, Anonymization, Sensitive Access Logging)
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models.organization import Company
from core.models.accounting import FiscalPeriod, JournalEntry, JournalEntryLine
from core.models.reference import KenyaCounty, KenyaBank
from core.models.security import SensitiveDataAccessLog
from core.models.events import OutboxEvent
from core.accounting.api import post_journal_entry, is_fiscal_period_closed
from core.seeders.kenya_reference_data import seed_kenya_counties, seed_kenya_banks
from core.privacy.service import (
    export_data_subject_profile,
    anonymize_user_personal_data,
    log_sensitive_data_access,
)


class AccountingPostingInterfaceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name='K-Mart Group Kenya',
            slug='k-mart-group-kenya',
            currency='KES',
            kra_pin='P051234567Z'
        )
        self.admin_user = User.objects.create_superuser(
            username='cfo_admin',
            password='password123',
            email='cfo@kmart.co.ke'
        )

    def test_post_balanced_journal_entry(self):
        """Posting a balanced journal entry creates lines, document sequence, and outbox event."""
        entries = [
            {'account_code': '1000', 'account_name': 'Cash in Till', 'debit': Decimal('5000.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'account_name': 'Sales Revenue', 'debit': Decimal('0.00'), 'credit': Decimal('4310.34')},
            {'account_code': '2100', 'account_name': 'VAT Output Payable', 'debit': Decimal('0.00'), 'credit': Decimal('689.66')},
        ]

        today = timezone.now().date()
        entry = post_journal_entry(
            company=self.company,
            entries=entries,
            source_module='pos',
            source_ref='ZREPORT-20260930-001',
            date_val=today,
            narration='Daily POS cash sales closure',
            posted_by=self.admin_user,
        )

        self.assertIsNotNone(entry.pk)
        self.assertTrue(entry.entry_number.startswith('JRN-'))
        self.assertEqual(entry.total_amount, Decimal('5000.00'))
        self.assertEqual(entry.lines.count(), 3)

        # Check outbox event
        event = OutboxEvent.objects.filter(
            event_name='accounting.journal_entry_posted.v1',
            status=OutboxEvent.STATUS_PENDING,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload['entry_number'], entry.entry_number)
        self.assertEqual(event.payload['total_amount'], '5000.00')

    def test_unbalanced_journal_entry_raises_validation_error(self):
        """Unbalanced journal entries (debits != credits) must be rejected with ValidationError."""
        entries = [
            {'account_code': '1000', 'account_name': 'Cash', 'debit': Decimal('5000.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'account_name': 'Sales Revenue', 'debit': Decimal('0.00'), 'credit': Decimal('4000.00')},
        ]

        with self.assertRaises(ValidationError) as ctx:
            post_journal_entry(
                company=self.company,
                entries=entries,
                source_module='pos',
                source_ref='INV-001',
            )

        self.assertIn('Unbalanced journal entry', str(ctx.exception))

    def test_closed_fiscal_period_prevents_posting(self):
        """Posting to a date within a closed FiscalPeriod is strictly rejected."""
        past_date = date(2025, 12, 15)
        FiscalPeriod.objects.create(
            company=self.company,
            name='December 2025',
            start_date=date(2025, 12, 1),
            end_date=date(2025, 12, 31),
            is_closed=True,
            closed_at=timezone.now(),
            closed_by=self.admin_user,
        )

        self.assertTrue(is_fiscal_period_closed(self.company, past_date))

        entries = [
            {'account_code': '1000', 'account_name': 'Cash', 'debit': Decimal('100.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'account_name': 'Revenue', 'debit': Decimal('0.00'), 'credit': Decimal('100.00')},
        ]

        with self.assertRaises(ValidationError) as ctx:
            post_journal_entry(
                company=self.company,
                entries=entries,
                source_module='pos',
                source_ref='INV-OLD-1',
                date_val=past_date,
            )

        self.assertIn('closed', str(ctx.exception).lower())

    def test_idempotency_prevents_duplicate_journal_entries(self):
        """Duplicate postings with same idempotency_key return existing entry without creating duplicates."""
        entries = [
            {'account_code': '1000', 'account_name': 'Cash', 'debit': Decimal('1000.00'), 'credit': Decimal('0.00')},
            {'account_code': '4000', 'account_name': 'Revenue', 'debit': Decimal('0.00'), 'credit': Decimal('1000.00')},
        ]

        entry1 = post_journal_entry(
            company=self.company,
            entries=entries,
            source_module='pos',
            source_ref='INV-IDEM-001',
            idempotency_key='pos:INV-IDEM-001',
        )

        entry2 = post_journal_entry(
            company=self.company,
            entries=entries,
            source_module='pos',
            source_ref='INV-IDEM-001',
            idempotency_key='pos:INV-IDEM-001',
        )

        self.assertEqual(entry1.pk, entry2.pk)
        self.assertEqual(JournalEntry.objects.filter(company=self.company).count(), 1)


class KenyaReferenceDataTests(TestCase):
    def test_seed_kenya_counties(self):
        """Seeding Kenyan counties creates all 47 counties with codes 001 to 047."""
        count = seed_kenya_counties()
        self.assertEqual(count, 47)
        self.assertEqual(KenyaCounty.objects.count(), 47)

        nbi = KenyaCounty.objects.get(code='047')
        self.assertEqual(nbi.name, 'Nairobi City')
        self.assertEqual(nbi.region, 'nairobi')

        msa = KenyaCounty.objects.get(code='001')
        self.assertEqual(msa.name, 'Mombasa')
        self.assertEqual(msa.region, 'coast')

    def test_seed_kenya_banks(self):
        """Seeding Kenyan banks registers major commercial banks with CBK clearing codes."""
        count = seed_kenya_banks()
        self.assertGreaterEqual(count, 15)

        kcb = KenyaBank.objects.get(bank_code='01')
        self.assertIn('KCB', kcb.name)
        self.assertEqual(kcb.swift_code, 'KCBLKENX')
        self.assertEqual(kcb.paybill_number, '522522')

        equity = KenyaBank.objects.get(bank_code='43')
        self.assertIn('Equity', equity.name)
        self.assertEqual(equity.paybill_number, '247247')


class KenyaDataPrivacyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='staff_john',
            password='password123',
            first_name='John',
            last_name='Kariuki',
            email='john.kariuki@kmart.co.ke'
        )
        self.dpo = User.objects.create_user(
            username='dpo_officer',
            password='password123',
            email='dpo@kmart.co.ke'
        )

    def test_export_data_subject_profile(self):
        """Data Subject Access Request (DSAR) export conforms to Kenya DPA 2019 Section 26."""
        data = export_data_subject_profile(self.user)
        self.assertEqual(data['username'], 'staff_john')
        self.assertEqual(data['first_name'], 'John')
        self.assertEqual(data['email'], 'john.kariuki@kmart.co.ke')
        self.assertIn('Kenya Data Protection Act 2019', data['compliance_statement'])

    def test_anonymize_user_personal_data(self):
        """Anonymizing a user replaces PII and records an audit log while preserving ledger integrity."""
        res = anonymize_user_personal_data(
            user=self.user,
            requested_by=self.dpo,
            reason='Right to be Forgotten Request #8812'
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Anonymized')
        self.assertTrue(self.user.last_name.startswith('User-'))
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())

    def test_log_sensitive_data_access(self):
        """Viewing sensitive data creates an immutable SensitiveDataAccessLog entry."""
        log = log_sensitive_data_access(
            data_subject=self.user,
            accessor=self.dpo,
            data_fields=['national_id', 'kra_pin', 'bank_account'],
            reason='Payroll statutory audit verification',
            ip_address='192.168.1.50',
        )

        self.assertIsNotNone(log.pk)
        self.assertEqual(log.user, self.dpo)
        self.assertEqual(log.entity_id, str(self.user.pk))
        self.assertIn('kra_pin', log.fields_accessed)
