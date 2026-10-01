"""
Platform Notifications Model
Supports in-app alerts, email dispatch, and pluggable SMS/WhatsApp channels.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """
    User notification record.
    """
    TYPE_INFO = 'info'
    TYPE_WARNING = 'warning'
    TYPE_SUCCESS = 'success'
    TYPE_ACTION = 'action_required'

    TYPE_CHOICES = [
        (TYPE_INFO, 'Information'),
        (TYPE_WARNING, 'Warning'),
        (TYPE_SUCCESS, 'Success'),
        (TYPE_ACTION, 'Action Required'),
    ]

    CHANNEL_IN_APP = 'in_app'
    CHANNEL_EMAIL = 'email'
    CHANNEL_SMS = 'sms'
    CHANNEL_WHATSAPP = 'whatsapp'

    CHANNEL_CHOICES = [
        (CHANNEL_IN_APP, 'In-App Notification'),
        (CHANNEL_EMAIL, 'Email'),
        (CHANNEL_SMS, 'SMS Message'),
        (CHANNEL_WHATSAPP, 'WhatsApp'),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        db_index=True,
    )
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
        db_index=True,
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_INFO)
    link_url = models.CharField(max_length=255, blank=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_IN_APP)
    
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
        ]

    def __str__(self):
        return f"To: {self.recipient.username} - {self.title} [{self.get_channel_display()}]"

    def mark_as_read(self):
        """Mark notification as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])
