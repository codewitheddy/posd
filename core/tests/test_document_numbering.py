"""
Unit Tests for Document Numbering Engine
"""
from datetime import date
from django.test import TestCase
from core.models.organization import Company, Branch
from core.numbering.service import next_document_number


class DocumentNumberingTests(TestCase):
    """Test suite for atomic, gap-aware document numbering sequences."""

    def setUp(self):
        self.company = Company.objects.create(name='Marid Retail', slug='marid-retail')
        self.branch_nbi = Branch.objects.create(company=self.company, name='Nairobi Branch', code='NBI')
        self.branch_msa = Branch.objects.create(company=self.company, name='Mombasa Branch', code='MSA')
        self.test_date = date(2026, 9, 30)

    def test_sequential_document_number_generation(self):
        """Test generating sequential invoice numbers."""
        num1 = next_document_number(
            document_type='sale_invoice',
            company=self.company,
            branch=self.branch_nbi,
            date_val=self.test_date,
            prefix='INV',
        )
        self.assertEqual(num1, 'INV-NBI-202609-0001')

        num2 = next_document_number(
            document_type='sale_invoice',
            company=self.company,
            branch=self.branch_nbi,
            date_val=self.test_date,
            prefix='INV',
        )
        self.assertEqual(num2, 'INV-NBI-202609-0002')

    def test_branch_sequence_isolation(self):
        """Test that different branches maintain independent sequences."""
        num_nbi = next_document_number(
            document_type='sale_invoice',
            company=self.company,
            branch=self.branch_nbi,
            date_val=self.test_date,
        )
        num_msa = next_document_number(
            document_type='sale_invoice',
            company=self.company,
            branch=self.branch_msa,
            date_val=self.test_date,
        )

        self.assertEqual(num_nbi, 'INV-NBI-202609-0001')
        self.assertEqual(num_msa, 'INV-MSA-202609-0001')

    def test_custom_format_pattern(self):
        """Test custom document format patterns."""
        num = next_document_number(
            document_type='purchase_order',
            company=self.company,
            branch=self.branch_nbi,
            date_val=self.test_date,
            prefix='PO',
            format_pattern='{prefix}/{year}/{branch_code}/{seq:06d}',
        )
        self.assertEqual(num, 'PO/2026/NBI/000001')
