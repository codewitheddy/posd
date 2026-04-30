"""
backup/tests/test_integration.py

Integration test: sale → EventLog → sync → BackupSnapshot → restore

Feature: backup-recovery-module
"""
import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from backup.models import BackupSnapshot, TenantBackupSettings
from backup.services import BackupService
from events.models import EventLog
from pos.models import Business, BusinessMembership
from restore.services import RestoreService
from sync.models import SyncStatus


def _make_tenant(name='Test Biz'):
    owner = User.objects.create_user(username=f'owner_{uuid.uuid4().hex[:6]}', password='pw')
    tenant = Business.objects.create(name=name, slug=f'test-{uuid.uuid4().hex[:6]}', owner=owner)
    BusinessMembership.objects.get_or_create(user=owner, business=tenant, defaults={'role': 'owner'})
    return tenant, owner


class EndToEndBackupRestoreTest(TestCase):
    """
    Validates the full pipeline:
      1. EventLog record is created for a POS operation
      2. BackupService.create_snapshot() uploads and records a BackupSnapshot
      3. RestoreService.restore_latest() downloads, decrypts, and replays events
    """

    def setUp(self):
        self.tenant, self.owner = _make_tenant()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _create_event(self, event_type='sale_created', payload=None):
        return EventLog.objects.create(
            tenant=self.tenant,
            event_type=event_type,
            payload=payload or {'sale_id': 1, 'total': '500.00'},
            device_id='test-device',
        )

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_eventlog_created_with_pending_status(self):
        """EventLog records start as pending."""
        event = self._create_event()
        self.assertEqual(event.sync_status, EventLog.SYNC_STATUS_PENDING)
        self.assertIsNotNone(event.uuid)
        self.assertEqual(event.tenant, self.tenant)

    def test_eventlog_immutability_save(self):
        """Updating an existing EventLog raises PermissionDenied."""
        from django.core.exceptions import PermissionDenied
        event = self._create_event()
        with self.assertRaises(PermissionDenied):
            event.save()

    def test_eventlog_immutability_delete(self):
        """Deleting an EventLog raises PermissionDenied."""
        from django.core.exceptions import PermissionDenied
        event = self._create_event()
        with self.assertRaises(PermissionDenied):
            event.delete()

    @patch('backup.cloud.CloudStorageClient.upload')
    @patch('backup.cloud.CloudStorageClient.object_checksum')
    @patch('backup.encryption.EncryptionService.encrypt')
    def test_create_snapshot_produces_backup_snapshot(self, mock_encrypt, mock_checksum, mock_upload):
        """BackupService.create_snapshot() creates a BackupSnapshot record."""
        # Arrange
        self._create_event()
        mock_encrypt.return_value = (b'encrypted_data', 'local')
        mock_checksum.return_value = __import__('hashlib').sha256(b'encrypted_data').hexdigest()

        # Act
        snap = BackupService.create_snapshot(self.tenant, triggered_by=self.owner)

        # Assert
        self.assertIsNotNone(snap)
        self.assertEqual(snap.tenant, self.tenant)
        self.assertEqual(snap.version, 1)
        self.assertEqual(snap.status, BackupSnapshot.STATUS_UPLOADED)
        self.assertGreater(snap.event_count, 0)
        mock_upload.assert_called_once()

    @patch('backup.cloud.CloudStorageClient.upload')
    @patch('backup.cloud.CloudStorageClient.object_checksum')
    @patch('backup.cloud.CloudStorageClient.download')
    @patch('backup.encryption.EncryptionService.encrypt')
    @patch('backup.encryption.EncryptionService.decrypt')
    def test_restore_replays_events(self, mock_decrypt, mock_encrypt, mock_download,
                                    mock_checksum, mock_upload):
        """RestoreService.restore_latest() replays events from the snapshot."""
        import gzip, json
        from events.serializers import EventLogSerializer

        # Arrange: create an event and snapshot
        event = self._create_event(payload={'sale_id': 42, 'total': '999.00'})
        serialized = json.dumps(EventLogSerializer([event], many=True).data, default=str).encode()
        compressed = gzip.compress(serialized)

        mock_encrypt.return_value = (compressed, 'local')
        mock_checksum.return_value = __import__('hashlib').sha256(compressed).hexdigest()
        snap = BackupService.create_snapshot(self.tenant, triggered_by=self.owner)

        # Simulate restore on a fresh tenant (delete events)
        EventLog.objects.filter(tenant=self.tenant).delete()
        self.assertEqual(EventLog.objects.filter(tenant=self.tenant).count(), 0)

        mock_download.return_value = compressed
        mock_decrypt.return_value = compressed  # skip real decryption

        # Act
        result = RestoreService.restore_latest(self.tenant, self.owner)

        # Assert
        self.assertGreater(result['records_restored'], 0)
        self.assertEqual(EventLog.objects.filter(tenant=self.tenant).count(), result['records_restored'])

    @patch('backup.cloud.CloudStorageClient.upload')
    @patch('backup.cloud.CloudStorageClient.object_checksum')
    @patch('backup.encryption.EncryptionService.encrypt')
    def test_snapshot_version_increments(self, mock_encrypt, mock_checksum, mock_upload):
        """Each snapshot gets a strictly incrementing version number."""
        mock_encrypt.return_value = (b'data', 'local')
        mock_checksum.return_value = __import__('hashlib').sha256(b'data').hexdigest()

        for i in range(1, 4):
            self._create_event()
            snap = BackupService.create_snapshot(self.tenant)
            self.assertEqual(snap.version, i)

    def test_sync_status_updated_after_snapshot(self):
        """SyncStatus is created/updated when upload_pending_events runs."""
        from sync.tasks import _update_sync_status
        self._create_event()
        _update_sync_status(self.tenant, 'test-device', SyncStatus.STATUS_SYNCED, 0)
        status = SyncStatus.objects.get(tenant=self.tenant, device_id='test-device')
        self.assertEqual(status.status, SyncStatus.STATUS_SYNCED)

    def test_tenant_backup_settings_auto_created(self):
        """TenantBackupSettings is auto-created with correct defaults for new Business."""
        new_owner = User.objects.create_user(username=f'o_{uuid.uuid4().hex[:6]}', password='pw')
        new_tenant = Business.objects.create(
            name='Auto Settings Biz',
            slug=f'auto-{uuid.uuid4().hex[:6]}',
            owner=new_owner,
        )
        settings = TenantBackupSettings.objects.filter(tenant=new_tenant).first()
        self.assertIsNotNone(settings)
        self.assertEqual(settings.backup_mode, TenantBackupSettings.MODE_AUTOMATIC)
        self.assertEqual(settings.retention_days, 30)
        self.assertEqual(settings.storage_mode, TenantBackupSettings.STORAGE_HYBRID)

    def test_uuid_deduplication_in_sync_api(self):
        """Submitting the same event UUID twice results in only one record."""
        event = self._create_event()
        initial_count = EventLog.objects.filter(tenant=self.tenant).count()

        # Attempt to create the same UUID again via bulk_create with ignore_conflicts
        duplicate = EventLog(
            uuid=event.uuid,
            tenant=self.tenant,
            event_type='sale_created',
            payload={'sale_id': 99},
            device_id='device-2',
        )
        EventLog.objects.bulk_create([duplicate], ignore_conflicts=True)

        self.assertEqual(EventLog.objects.filter(tenant=self.tenant).count(), initial_count)
