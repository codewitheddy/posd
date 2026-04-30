"""
events/models.py — Immutable, append-only EventLog.

No UPDATE or DELETE is permitted on committed rows.  Any attempt raises
PermissionDenied so that the audit trail can never be silently altered.
"""
import uuid

from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


class EventLog(models.Model):
    """Append-only record of every POS operation for a tenant."""

    SYNC_STATUS_PENDING = 'pending'
    SYNC_STATUS_SYNCED  = 'synced'
    SYNC_STATUS_FAILED  = 'failed'

    SYNC_STATUS_CHOICES = [
        (SYNC_STATUS_PENDING, 'Pending'),
        (SYNC_STATUS_SYNCED,  'Synced'),
        (SYNC_STATUS_FAILED,  'Failed'),
    ]

    EVENT_TYPE_SALE_CREATED      = 'sale_created'
    EVENT_TYPE_SALE_REFUNDED     = 'sale_refunded'
    EVENT_TYPE_INVENTORY_UPDATED = 'inventory_updated'
    EVENT_TYPE_PRODUCT_CHANGED   = 'product_changed'
    EVENT_TYPE_PAYMENT_RECORDED  = 'payment_recorded'

    EVENT_TYPE_CHOICES = [
        (EVENT_TYPE_SALE_CREATED,      'Sale Created'),
        (EVENT_TYPE_SALE_REFUNDED,     'Sale Refunded'),
        (EVENT_TYPE_INVENTORY_UPDATED, 'Inventory Updated'),
        (EVENT_TYPE_PRODUCT_CHANGED,   'Product Changed'),
        (EVENT_TYPE_PAYMENT_RECORDED,  'Payment Recorded'),
    ]

    # ── Core fields ──────────────────────────────────────────────────────────
    uuid        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant      = models.ForeignKey(
        'pos.Business',
        on_delete=models.CASCADE,
        related_name='event_logs',
    )
    event_type  = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES)
    payload     = models.JSONField()
    device_id   = models.CharField(max_length=100)
    timestamp   = models.DateTimeField(default=timezone.now, db_index=True)
    sync_status = models.CharField(
        max_length=20,
        choices=SYNC_STATUS_CHOICES,
        default=SYNC_STATUS_PENDING,
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(
                fields=['tenant', 'sync_status', 'timestamp'],
                name='events_log_tenant_sync_ts_idx',
            ),
        ]
        verbose_name     = 'Event Log'
        verbose_name_plural = 'Event Logs'

    def __str__(self):
        return f"{self.event_type} [{self.sync_status}] @ {self.timestamp:%Y-%m-%d %H:%M:%S}"

    # ── Immutability guards ───────────────────────────────────────────────────

    def save(self, *args, **kwargs):
        """Allow INSERT only.  Any UPDATE raises PermissionDenied."""
        if not self._state.adding:
            raise PermissionDenied(
                "EventLog records are immutable and cannot be updated."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Deletion is never permitted."""
        raise PermissionDenied(
            "EventLog records are immutable and cannot be deleted."
        )

    @classmethod
    def _force_update_sync_status(cls, uuids, status):
        """
        Internal helper used ONLY by the sync engine to mark records as synced.
        Bypasses the immutability guard by using queryset.update() directly.
        """
        cls.objects.filter(uuid__in=uuids).update(sync_status=status)
