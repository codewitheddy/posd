"""backup/models.py — TenantBackupSettings and BackupSnapshot."""
from django.core.exceptions import ValidationError
from django.db import models


class TenantBackupSettings(models.Model):
    MODE_AUTOMATIC = 'automatic'
    MODE_SCHEDULED = 'scheduled'
    MODE_MANUAL    = 'manual'

    BACKUP_MODE_CHOICES = [
        (MODE_AUTOMATIC, 'Automatic'),
        (MODE_SCHEDULED, 'Scheduled'),
        (MODE_MANUAL,    'Manual'),
    ]

    STORAGE_LOCAL  = 'local_only'
    STORAGE_CLOUD  = 'cloud_only'
    STORAGE_HYBRID = 'hybrid'

    STORAGE_MODE_CHOICES = [
        (STORAGE_LOCAL,  'Local Only'),
        (STORAGE_CLOUD,  'Cloud Only'),
        (STORAGE_HYBRID, 'Hybrid'),
    ]

    VALID_INTERVALS = [6, 12, 24]

    tenant = models.OneToOneField(
        'pos.Business',
        on_delete=models.CASCADE,
        related_name='backup_settings',
    )
    backup_mode             = models.CharField(max_length=20, choices=BACKUP_MODE_CHOICES, default=MODE_AUTOMATIC)
    schedule_interval_hours = models.IntegerField(null=True, blank=True)
    retention_days          = models.IntegerField(default=30)
    local_storage_limit_mb  = models.IntegerField(null=True, blank=True)
    storage_mode            = models.CharField(max_length=20, choices=STORAGE_MODE_CHOICES, default=STORAGE_HYBRID)
    encryption_key_id       = models.CharField(max_length=200, blank=True)
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Tenant Backup Settings'
        verbose_name_plural = 'Tenant Backup Settings'

    def __str__(self):
        return f"{self.tenant.name} — {self.backup_mode}"

    def clean(self):
        if self.backup_mode == self.MODE_SCHEDULED:
            if self.schedule_interval_hours not in self.VALID_INTERVALS:
                raise ValidationError(
                    f"schedule_interval_hours must be one of {self.VALID_INTERVALS} "
                    f"when backup_mode is 'scheduled'."
                )


class BackupSnapshot(models.Model):
    STATUS_PENDING   = 'pending'
    STATUS_UPLOADED  = 'uploaded'
    STATUS_CORRUPTED = 'corrupted'
    STATUS_DELETED   = 'deleted'

    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_UPLOADED,  'Uploaded'),
        (STATUS_CORRUPTED, 'Corrupted'),
        (STATUS_DELETED,   'Deleted'),
    ]

    tenant            = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='backup_snapshots')
    version           = models.IntegerField()
    storage_key       = models.CharField(max_length=500)
    file_size_bytes   = models.BigIntegerField(default=0)
    checksum_sha256   = models.CharField(max_length=64, blank=True)
    encryption_key_id = models.CharField(max_length=200, blank=True)
    event_count       = models.IntegerField(default=0)
    status            = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('tenant', 'version')]
        ordering        = ['tenant', 'version']
        verbose_name        = 'Backup Snapshot'
        verbose_name_plural = 'Backup Snapshots'

    def __str__(self):
        return f"Snapshot v{self.version} — {self.tenant.name} [{self.status}]"

    @classmethod
    def next_version(cls, tenant):
        """Return the next auto-incrementing version number for this tenant."""
        last = cls.objects.filter(tenant=tenant).order_by('-version').first()
        return (last.version + 1) if last else 1
