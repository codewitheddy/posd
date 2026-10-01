"""
Core Unit of Measure (UOM) Models
Provides standardized units of measure and dynamic unit conversions for inventory and purchasing.
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from core.models.base import CompanyScopedModel, TimeStampedModel


class UnitOfMeasure(CompanyScopedModel, TimeStampedModel):
    """
    Standardized unit of measure (e.g. PCS, KG, LTR, BOX, CTN).
    """
    CATEGORY_UNIT = 'unit'
    CATEGORY_WEIGHT = 'weight'
    CATEGORY_VOLUME = 'volume'
    CATEGORY_LENGTH = 'length'
    CATEGORY_TIME = 'time'

    CATEGORY_CHOICES = [
        (CATEGORY_UNIT, 'Unit / Quantity (e.g. PCS, Box, Carton)'),
        (CATEGORY_WEIGHT, 'Weight (e.g. Kg, Gram, Ton)'),
        (CATEGORY_VOLUME, 'Volume (e.g. Liter, Milliliter, Gallon)'),
        (CATEGORY_LENGTH, 'Length (e.g. Meter, Centimeter, Foot)'),
        (CATEGORY_TIME, 'Time / Duration (e.g. Hour, Day, Month)'),
    ]

    name = models.CharField(max_length=50, help_text="e.g. Piece, Kilogram, Carton")
    code = models.CharField(max_length=20, db_index=True, help_text="e.g. PCS, KG, CTN")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_UNIT)
    is_base_unit = models.BooleanField(
        default=False,
        help_text="If True, this is the reference unit for this category (conversion factor = 1.0)",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Unit of Measure'
        verbose_name_plural = 'Units of Measure'
        ordering = ['category', 'name']
        unique_together = [['company', 'code']]

    def __str__(self):
        return f"{self.name} ({self.code})"


class UOMConversion(CompanyScopedModel, TimeStampedModel):
    """
    Conversion factor between units of measure within a company.
    Formula: target_qty = source_qty * conversion_factor
    e.g. 1 CTN (from) = 24 PCS (to) => conversion_factor = 24.000000
    """
    from_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.CASCADE,
        related_name='conversions_from',
        help_text="Source unit (e.g. Carton)",
    )
    to_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.CASCADE,
        related_name='conversions_to',
        help_text="Target base unit (e.g. Piece)",
    )
    conversion_factor = models.DecimalField(
        max_digits=14,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text="Multiply from_uom quantity by this factor to obtain to_uom quantity",
    )

    class Meta:
        verbose_name = 'UOM Conversion'
        verbose_name_plural = 'UOM Conversions'
        unique_together = [['company', 'from_uom', 'to_uom']]
        constraints = [
            models.CheckConstraint(
                check=models.Q(conversion_factor__gt=0),
                name='core_uom_conversion_factor_positive',
            ),
        ]

    def __str__(self):
        return f"1 {self.from_uom.code} = {self.conversion_factor} {self.to_uom.code}"
