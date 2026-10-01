"""
DB-Backed Asynchronous / Batch Job Queue Model
Pure Django replacement for Celery workers.
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from core.models.base import TimeStampedModel


class Job(TimeStampedModel):
    """
    Database-backed job record supporting concurrency-safe claiming, progress tracking,
    retry backoff, and administrative inspection.
    """
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='jobs',
        db_index=True,
        help_text="Company scoping this job (NULL for system maintenance)",
    )
    name = models.CharField(max_length=255, db_index=True, help_text="Human-readable job name")
    task_path = models.CharField(max_length=255, help_text="Dotted python path to callable e.g. pos.tasks.generate_report")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    priority = models.PositiveIntegerField(default=100, db_index=True, help_text="Lower number = higher priority")
    
    # Task Arguments & Output
    args = models.JSONField(default=list, blank=True)
    kwargs = models.JSONField(default=dict, blank=True)
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    
    # Progress Tracking (0-100%)
    progress = models.PositiveSmallIntegerField(default=0)
    progress_message = models.CharField(max_length=255, blank=True)
    
    # Retries and Idempotency
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    idempotency_key = models.CharField(max_length=100, blank=True, db_index=True)
    
    # Worker Locking
    locked_by = models.CharField(max_length=100, blank=True, help_text="Worker ID holding lock")
    locked_at = models.DateTimeField(null=True, blank=True)
    
    # Scheduling Timestamps
    scheduled_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    class Meta:
        verbose_name = 'Background Job'
        verbose_name_plural = 'Background Jobs'
        ordering = ['priority', 'scheduled_at']
        indexes = [
            models.Index(fields=['status', 'scheduled_at', 'priority'], name='core_job_queue_idx'),
            models.Index(fields=['company', 'status']),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.name} (#{str(self.id)[:8]})"

    def update_progress(self, percent: int, message: str = ''):
        """Update job progress in-place."""
        self.progress = min(max(percent, 0), 100)
        if message:
            self.progress_message = message
        self.save(update_fields=['progress', 'progress_message', 'updated_at'])
