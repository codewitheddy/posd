"""
Unit Tests for Unified Audit Logging and Immutability Guards
"""
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase, RequestFactory
from core.models.audit import AuditLog
from core.models.organization import Company, Branch
from core.audit.service import log_audit, AuditedModelMixin


class AuditLogTests(TestCase):
    """Test suite for audit logging and tamper-evident immutability."""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='auditor', email='auditor@example.com')
        self.company = Company.objects.create(name='Acme Corp', slug='acme-corp')
        self.branch = Branch.objects.create(company=self.company, name='CBD Branch', code='CBD')

    def test_log_audit_entry_creation(self):
        """Test creating an audit entry with model reference and changes."""
        request = self.factory.post('/branches/edit/')
        request.user = self.user
        request.company = self.company

        log = log_audit(
            action=AuditLog.ACTION_UPDATE,
            instance=self.branch,
            changes={'name': {'old': 'Old CBD', 'new': 'CBD Branch'}},
            request=request,
            metadata={'reason': 'Annual branch rebrand'},
        )

        self.assertIsNotNone(log.pk)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.company, self.company)
        self.assertEqual(log.action, AuditLog.ACTION_UPDATE)
        self.assertEqual(log.object_id, str(self.branch.pk))
        self.assertEqual(log.changes['name']['new'], 'CBD Branch')

    def test_audit_log_immutability_blocks_updates(self):
        """Verify that updating an existing AuditLog row raises PermissionDenied."""
        log = AuditLog.objects.create(
            company=self.company,
            user=self.user,
            action=AuditLog.ACTION_CREATE,
            object_repr='Test Object',
        )

        log.object_repr = 'Tampered Object Name'
        with self.assertRaises(PermissionDenied):
            log.save()

    def test_audit_log_immutability_blocks_deletion(self):
        """Verify that deleting an AuditLog row raises PermissionDenied."""
        log = AuditLog.objects.create(
            company=self.company,
            user=self.user,
            action=AuditLog.ACTION_CREATE,
            object_repr='Test Object',
        )

        with self.assertRaises(PermissionDenied):
            log.delete()
