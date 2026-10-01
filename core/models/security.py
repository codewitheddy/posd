"""
Security & Compliance Models for Core Platform
Tracks sensitive data access (Kenya DPA 2019) and authentication security logs.
"""
from django.conf import settings
from django.db import models


class SensitiveDataAccessLog(models.Model):
    """
    Append-only audit trail for viewing or exporting sensitive PII or financial fields.
    Required for Kenya Data Protection Act 2019 compliance.
    """
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sensitive_access_logs',
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
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    action = models.CharField(max_length=50, default='view', help_text="e.g. view, export, decrypt, print")
    entity_type = models.CharField(max_length=100, db_index=True, help_text="e.g. hr.Employee, core.UserProfile")
    entity_id = models.CharField(max_length=100, db_index=True)
    fields_accessed = models.JSONField(default=list, help_text="List of protected fields viewed e.g. ['salary', 'kra_pin']")
    reason = models.CharField(max_length=255, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Sensitive Data Access Log'
        verbose_name_plural = 'Sensitive Data Access Logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} accessed {self.entity_type}#{self.entity_id} @ {self.timestamp:%Y-%m-%d %H:%M}"


class LoginAuditLog(models.Model):
    """
    Tracks all login attempts (success and failure) for security monitoring and lockouts.
    """
    username = models.CharField(max_length=150, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    is_successful = models.BooleanField(default=False, db_index=True)
    failure_reason = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Login Audit Log'
        verbose_name_plural = 'Login Audit Logs'
        ordering = ['-timestamp']

    def __str__(self):
        status = "SUCCESS" if self.is_successful else f"FAILED ({self.failure_reason})"
        return f"{self.username} - {status} from {self.ip_address} @ {self.timestamp:%Y-%m-%d %H:%M:%S}"
