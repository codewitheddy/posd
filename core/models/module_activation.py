"""
Module Activation Model
Tracks enabled/disabled business modules per company.
"""
from django.conf import settings
from django.db import models
from core.models.base import TimeStampedModel


class ModuleActivation(TimeStampedModel):
    """
    Controls dynamic enablement of business modules (POS, HR, Accounting, etc.) per Company.
    Disabling a module safely removes its menu items, dashboard widgets, and blocks its URLs.
    """
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='module_activations',
        db_index=True,
    )
    module_key = models.CharField(max_length=50, db_index=True, help_text="Unique module key e.g. 'pos', 'hr', 'accounting'")
    is_enabled = models.BooleanField(default=True, db_index=True)
    enabled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    notes = models.TextField(blank=True)
    config = models.JSONField(default=dict, blank=True, help_text="Per-company module configuration overrides")

    class Meta:
        verbose_name = 'Module Activation'
        verbose_name_plural = 'Module Activations'
        unique_together = [['company', 'module_key']]
        indexes = [
            models.Index(fields=['company', 'module_key', 'is_enabled']),
        ]

    def __str__(self):
        status = "Active" if self.is_enabled else "Disabled"
        return f"{self.module_key.upper()} [{status}] - {self.company.name}"
