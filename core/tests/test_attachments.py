"""
Unit Tests for Attachments Service
"""
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from core.models.organization import Company, Branch
from core.attachments.service import attach_file, get_attachments_for_object


class AttachmentsTests(TestCase):
    """Test suite for generic file attachments and validation."""

    def setUp(self):
        self.company = Company.objects.create(name='Global Corp', slug='global-corp')
        self.branch = Branch.objects.create(company=self.company, name='Main Branch', code='MAIN')

    def test_attach_file_to_model_instance(self):
        """Test attaching a valid PDF document to a model instance."""
        pdf_file = SimpleUploadedFile(
            'receipt.pdf',
            b'%PDF-1.4 test document content',
            content_type='application/pdf',
        )

        attachment = attach_file(
            instance=self.branch,
            file_obj=pdf_file,
            company=self.company,
            description='Branch lease agreement',
        )

        self.assertIsNotNone(attachment.pk)
        self.assertEqual(attachment.original_filename, 'receipt.pdf')
        self.assertEqual(attachment.mime_type, 'application/pdf')

        # Retrieve attachments
        attachments = get_attachments_for_object(self.branch)
        self.assertEqual(attachments.count(), 1)
        self.assertEqual(attachments.first(), attachment)

    def test_disallowed_file_extension_rejected(self):
        """Test that executable or disallowed extensions are rejected."""
        exe_file = SimpleUploadedFile(
            'malicious.exe',
            b'binary payload',
            content_type='application/x-msdownload',
        )

        with self.assertRaises(ValidationError):
            attach_file(
                instance=self.branch,
                file_obj=exe_file,
                company=self.company,
            )
