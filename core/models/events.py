"""
Platform Event Bus & Outbox Models
Implements transactional Outbox pattern for reliable asynchronous inter-module messaging.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from core.models.base import TimeStampedModel


class OutboxEvent(TimeStampedModel):
    """
    Transactional Outbox Table.
    Events are committed inside the caller's transaction and dispatched asynchronously.
    """
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DISPATCHED = 'dispatched'
    STATUS_FAILED = 'failed'
    STATUS_DEAD_LETTER = 'dead_letter'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Dispatch'),
        (STATUS_PROCESSING, 'Processing Subscribers'),
        (STATUS_DISPATCHED, 'Fully Dispatched'),
        (STATUS_FAILED, 'Retrying'),
        (STATUS_DEAD_LETTER, 'Dead Letter (Exhausted)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='outbox_events',
        db_index=True,
        help_text="Company scoping this event",
    )
    event_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Versioned event name e.g. 'pos.sale_completed.v1', 'hr.employee_hired.v1'",
    )
    payload = models.JSONField(help_text="Serialized event payload dictionary")
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    last_error = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True, db_index=True)
    
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Outbox Event'
        verbose_name_plural = 'Outbox Events'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='core_outbox_status_ts_idx'),
            models.Index(fields=['company', 'event_name']),
        ]

    def __str__(self):
        return f"{self.event_name} [{self.get_status_display()}] (#{str(self.id)[:8]})"


class EventDelivery(models.Model):
    """
    Per-subscriber delivery log for an OutboxEvent.
    Tracks execution status and error logs for each subscriber.
    """
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    event = models.ForeignKey(
        OutboxEvent,
        on_delete=models.CASCADE,
        related_name='deliveries',
        db_index=True,
    )
    subscriber_name = models.CharField(max_length=255, help_text="Dotted function path of the subscriber")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Event Delivery'
        verbose_name_plural = 'Event Deliveries'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.subscriber_name} -> {self.event.event_name} [{self.status}]"
