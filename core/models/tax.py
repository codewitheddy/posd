"""
Core Tax Rate Models
Provides standardized tax classifications and KRA eTIMS codes for sales, purchasing, and GL accounting.
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models.base import CompanyScopedModel, TimeStampedModel


class TaxRate(CompanyScopedModel, TimeStampedModel):
    """
    Standardized Tax Rate entity configured per Company.
    Supports KRA eTIMS classifications (A=16%, B=0%, C=Exempt, E=8%).
    """
    TAX_TYPE_VAT = 'vat'
    TAX_TYPE_WITHHOLDING = 'withholding'
    TAX_TYPE_EXCISE = 'excise'
    TAX_TYPE_OTHER = 'other'

    TAX_TYPE_CHOICES = [
        (TAX_TYPE_VAT, 'Value Added Tax (VAT)'),
        (TAX_TYPE_WITHHOLDING, 'Withholding Tax'),
        (TAX_TYPE_EXCISE, 'Excise Duty'),
        (TAX_TYPE_OTHER, 'Other Levy / Tax'),
    ]

    name = models.CharField(max_length=100, help_text="e.g. Standard VAT 16%, Zero-Rated 0%, Exempt")
    code = models.CharField(max_length=20, db_index=True, help_text="Short code e.g. VAT-16, VAT-0, EXEMPT")
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text="Tax percentage rate (e.g. 16.00 for 16%)",
    )
    tax_type = models.CharField(max_length=20, choices=TAX_TYPE_CHOICES, default=TAX_TYPE_VAT)
    
    # KRA eTIMS Tax Code Mapping
    kra_etims_code = models.CharField(
        max_length=10,
        blank=True,
        help_text="KRA eTIMS Code: 'A' (16%), 'B' (0%), 'C' (Exempt), 'D' (Non-VAT), 'E' (8%)",
    )
    
    is_default = models.BooleanField(default=False, help_text="Default tax rate applied to new products")
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Tax Rate'
        verbose_name_plural = 'Tax Rates'
        ordering = ['-rate', 'name']
        unique_together = [['company', 'code']]
        constraints = [
            models.CheckConstraint(
                check=models.Q(rate__gte=0) & models.Q(rate__lte=100),
                name='core_tax_rate_percentage_valid_range',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"
