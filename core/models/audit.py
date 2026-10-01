"""
Unified Append-Only Audit Log Model
Tamper-evident audit trail for all operations across the platform.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import models


class AuditLog(models.Model):
    """
    Unified, immutable audit record.
    Tracks who did what, when, before/after diffs, and network metadata.
    """
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_APPROVE = 'approve'
    ACTION_REJECT = 'reject'
    ACTION_VOID = 'void'
    ACTION_LOGIN = 'login'
    ACTION_EXPORT = 'export'
    ACTION_CUSTOM = 'custom'

    ACTION_CHOICES = [
        (ACTION_CREATE, 'Created'),
        (ACTION_UPDATE, 'Updated'),
        (ACTION_DELETE, 'Deleted'),
        (ACTION_APPROVE, 'Approved'),
        (ACTION_REJECT, 'Rejected'),
        (ACTION_VOID, 'Voided'),
        (ACTION_LOGIN, 'Login'),
        (ACTION_EXPORT, 'Data Export'),
        (ACTION_CUSTOM, 'Custom Action'),
    ]

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_logs',
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        db_index=True,
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    
    # Generic Relation to Audited Entity
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )
    object_id = models.CharField(max_length=100, blank=True, db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    object_repr = models.CharField(max_length=255, blank=True)
    
    # Field Changes Diff: {field_name: {'old': v1, 'new': v2}}
    changes = models.JSONField(default=dict, blank=True)
    
    # Network and Client Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['company', 'timestamp']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else 'System'
        return f"[{self.get_action_display()}] {self.object_repr or self.entity_name} by {user_str} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"

    @property
    def entity_name(self):
        return f"{self.content_type.model} #{self.object_id}" if self.content_type else f"Object #{self.object_id}"

    # ── Immutability Guards ──────────────────────────────────────────────────

    def save(self, *args, **kwargs):
        """Allow INSERT only. Any UPDATE is blocked."""
        if not self._state.adding and self.pk:
            raise PermissionDenied("AuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Deletion is forbidden."""
        raise PermissionDenied("AuditLog entries are immutable and cannot be deleted.")
