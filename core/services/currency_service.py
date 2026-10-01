"""
Core Currency Service
Handles currency exchange calculations and rate lookups.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from django.utils import timezone
from core.models.currency import Currency, ExchangeRate
from core.models.organization import Company


def convert_currency(
    amount: Decimal,
    from_currency: Currency,
    to_currency: Currency,
    company: Company,
    date_val: Optional[date] = None,
) -> Decimal:
    """
    Convert an amount from one currency to another using the latest exchange rate as of date_val.
    """
    amount = Decimal(str(amount))
    if from_currency.code == to_currency.code:
        return amount

    if not date_val:
        date_val = timezone.now().date()

    # Direct rate
    rate_obj = (
        ExchangeRate.objects.filter(
            company=company,
            from_currency=from_currency,
            to_currency=to_currency,
            effective_date__lte=date_val,
        )
        .order_by('-effective_date')
        .first()
    )
    if rate_obj:
        return (amount * rate_obj.rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Inverse rate
    rate_inv = (
        ExchangeRate.objects.filter(
            company=company,
            from_currency=to_currency,
            to_currency=from_currency,
            effective_date__lte=date_val,
        )
        .order_by('-effective_date')
        .first()
    )
    if rate_inv:
        return (amount / rate_inv.rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    raise ValueError(
        f"No active exchange rate found between {from_currency.code} and {to_currency.code} as of {date_val}"
    )
