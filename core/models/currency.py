"""
Core Currency & Exchange Rate Models
Provides multi-currency support, exchange rate histories, and standard ISO 4217 currencies.
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from core.models.base import CompanyScopedModel, TimeStampedModel


class Currency(TimeStampedModel):
    """
    Global ISO 4217 Currency Definition (KES, USD, EUR, GBP, etc.).
    """
    code = models.CharField(max_length=3, unique=True, db_index=True, help_text="ISO 4217 3-letter code (e.g. KES)")
    name = models.CharField(max_length=50, help_text="e.g. Kenyan Shilling, US Dollar")
    symbol = models.CharField(max_length=10, default='KSh', help_text="e.g. KSh, $, €, £")
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Currency'
        verbose_name_plural = 'Currencies'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name} ({self.symbol})"


class ExchangeRate(CompanyScopedModel, TimeStampedModel):
    """
    Historical exchange rate between two currencies for a specific company.
    Formula: target_amount_kes = source_amount * rate
    """
    from_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name='rates_from',
        help_text="Source currency (e.g. USD)",
    )
    to_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name='rates_to',
        help_text="Base currency (e.g. KES)",
    )
    rate = models.DecimalField(
        max_digits=16,
        decimal_places=6,
        validators=[MinValueValidator(Decimal('0.000001'))],
        help_text="Exchange rate to multiply from_currency by to get to_currency",
    )
    effective_date = models.DateField(default=timezone.now, db_index=True)
    source = models.CharField(max_length=100, blank=True, default='Manual', help_text="e.g. Central Bank of Kenya / Manual")

    class Meta:
        verbose_name = 'Exchange Rate'
        verbose_name_plural = 'Exchange Rates'
        ordering = ['-effective_date']
        unique_together = [['company', 'from_currency', 'to_currency', 'effective_date']]
        constraints = [
            models.CheckConstraint(
                check=models.Q(rate__gt=0),
                name='core_exchange_rate_positive',
            ),
        ]

    def __str__(self):
        return f"1 {self.from_currency.code} = {self.rate} {self.to_currency.code} ({self.effective_date})"
