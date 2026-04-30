"""sync/models.py — SyncStatus per device per tenant."""
from django.db import models


class SyncStatus(models.Model):
    STATUS_SYNCED  = 'synced'
    STATUS_PENDING = 'pending'
    STATUS_ERROR   = 'error'

    STATUS_CHOICES = [
        (STATUS_SYNCED,  'Synced'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_ERROR,   'Error'),
    ]

    tenant                = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='sync_statuses')
    device_id             = models.CharField(max_length=100)
    last_synced_at        = models.DateTimeField(null=True, blank=True)
    pending_events_count  = models.IntegerField(default=0)
    status                = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message         = models.TextField(blank=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together     = [('tenant', 'device_id')]
        verbose_name        = 'Sync Status'
        verbose_name_plural = 'Sync Statuses'

    def __str__(self):
        return f"{self.tenant.name} / {self.device_id} — {self.status}"
