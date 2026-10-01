"""
Unit Tests for Posting Exceptions & Integration Mappings Views
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from core.models.organization import Company, Branch, CompanyMembership
from accounting.models import PostingQueue, JournalEntry, JournalEntryStatus
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from pos.models import Business, POSGLMapping
from hr.models import HRGLMapping


class PostingExceptionsViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.company = Company.objects.create(name='Highland Hardware Ltd', slug='highland-hardware')
        self.branch = Branch.objects.create(company=self.company, name='Eldoret Branch', code='ELD')
        self.user = User.objects.create_user(username='accountant_kim', password='securepass123')
        
        # Membership
        self.membership = CompanyMembership.objects.create(
            user=self.user,
            company=self.company,
            role=CompanyMembership.ROLE_ADMIN,
            is_active=True
        )

        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

        # Login
        self.client.login(username='accountant_kim', password='securepass123')
        session = self.client.session
        session['active_company_id'] = self.company.id
        session.save()

    def test_posting_exceptions_list_view(self):
        """Test accessing the posting exceptions list view."""
        # Create a failed queue item
        PostingQueue.objects.create(
            company=self.company,
            source_module='pos',
            source_ref='ZREP-001',
            payload={'lines': []},
            status=PostingQueue.STATUS_FAILED,
            error_message='Line 1: Account not found'
        )

        resp = self.client.get(reverse('posting_exceptions'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Posting Queue &amp; Exceptions')
        self.assertContains(resp, 'ZREP-001')
        self.assertContains(resp, 'Line 1: Account not found')

    def test_posting_exception_retry_success(self):
        """Test retrying a valid pending/failed item executes it successfully."""
        queue_item = PostingQueue.objects.create(
            company=self.company,
            source_module='pos',
            source_ref='ZREP-002',
            payload={
                'source_module': 'pos',
                'source_ref': 'ZREP-002',
                'date': '2026-03-10',
                'narration': 'Valid sales close',
                'lines': [
                    {'account_code': '1010', 'debit': '1000.00', 'credit': '0.00'},
                    {'account_code': '4000', 'debit': '0.00', 'credit': '1000.00'},
                ]
            },
            status=PostingQueue.STATUS_FAILED,
            error_message='Previous network timeout'
        )

        resp = self.client.post(reverse('posting_exception_retry', kwargs={'pk': queue_item.pk}))
        self.assertEqual(resp.status_code, 302)

        queue_item.refresh_from_db()
        self.assertEqual(queue_item.status, PostingQueue.STATUS_PROCESSED)
        self.assertIsNotNone(queue_item.created_journal_entry)
        self.assertEqual(queue_item.created_journal_entry.status, JournalEntryStatus.POSTED)

    def test_posting_exception_dismiss(self):
        """Test dismissing a failed queue item removes it."""
        queue_item = PostingQueue.objects.create(
            company=self.company,
            source_module='pos',
            source_ref='ZREP-003',
            payload={},
            status=PostingQueue.STATUS_FAILED,
        )

        resp = self.client.post(reverse('posting_exception_dismiss', kwargs={'pk': queue_item.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(PostingQueue.objects.filter(pk=queue_item.pk).exists())
