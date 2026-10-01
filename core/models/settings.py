"""
Typed Key-Value Settings Storage
Supports global defaults, company overrides, and branch overrides per module.
"""
import json
from decimal import Decimal
from django.db import models
from core.models.base import TimeStampedModel


class CoreSetting(TimeStampedModel):
    """
    Hierarchical typed setting store.
    Resolution order: Branch Override -> Company Override -> Global Default.
    """
    TYPE_STRING = 'string'
    TYPE_INTEGER = 'integer'
    TYPE_DECIMAL = 'decimal'
    TYPE_BOOLEAN = 'boolean'
    TYPE_JSON = 'json'

    TYPE_CHOICES = [
        (TYPE_STRING, 'String / Text'),
        (TYPE_INTEGER, 'Integer Number'),
        (TYPE_DECIMAL, 'Decimal / Currency'),
        (TYPE_BOOLEAN, 'Boolean (True/False)'),
        (TYPE_JSON, 'Structured JSON / Object'),
    ]

    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='core_settings',
        db_index=True,
        help_text="Tenant Company (NULL for system-wide defaults)",
    )
    branch = models.ForeignKey(
        'core.Branch',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='core_settings',
        db_index=True,
        help_text="Branch (NULL for company-wide setting)",
    )
    module_key = models.CharField(max_length=50, default='core', db_index=True)
    key = models.CharField(max_length=100, db_index=True)
    value_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_STRING)
    raw_value = models.TextField(blank=True)
    json_value = models.JSONField(null=True, blank=True)
    description = models.CharField(max_length=255, blank=True)
    is_public = models.BooleanField(default=False, help_text="True if safe to expose in client context")

    class Meta:
        verbose_name = 'Core Setting'
        verbose_name_plural = 'Core Settings'
        unique_together = [['company', 'branch', 'module_key', 'key']]
        indexes = [
            models.Index(fields=['module_key', 'key']),
            models.Index(fields=['company', 'module_key', 'key']),
        ]

    def __str__(self):
        scope = f"{self.company.name if self.company else 'GLOBAL'}"
        if self.branch:
            scope += f"/{self.branch.name}"
        return f"[{self.module_key}.{self.key}] = {self.get_value()} ({scope})"

    def get_value(self):
        """Return the casted Python value according to value_type."""
        if self.value_type == self.TYPE_BOOLEAN:
            return self.raw_value.strip().lower() in ('true', '1', 'yes', 't')
        elif self.value_type == self.TYPE_INTEGER:
            try:
                return int(self.raw_value)
            except (ValueError, TypeError):
                return 0
        elif self.value_type == self.TYPE_DECIMAL:
            try:
                return Decimal(self.raw_value)
            except Exception:
                return Decimal('0.00')
        elif self.value_type == self.TYPE_JSON:
            if self.json_value is not None:
                return self.json_value
            try:
                return json.loads(self.raw_value) if self.raw_value else {}
            except Exception:
                return {}
        return self.raw_value

    def set_value(self, val):
        """Set the value and auto-convert to raw_value/json_value."""
        if self.value_type == self.TYPE_BOOLEAN:
            self.raw_value = 'true' if bool(val) else 'false'
        elif self.value_type == self.TYPE_JSON:
            if isinstance(val, (dict, list)):
                self.json_value = val
                self.raw_value = json.dumps(val)
            else:
                self.raw_value = str(val)
        else:
            self.raw_value = str(val) if val is not None else ''
