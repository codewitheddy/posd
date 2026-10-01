"""
Core Tax Service
Provides standard tax calculations, inclusive/exclusive breakdowns, and KRA eTIMS helper calculations.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional
from core.models.tax import TaxRate
from core.models.organization import Company


def calculate_tax(
    amount: Decimal,
    tax_rate: TaxRate,
    is_inclusive: bool = True,
) -> Dict[str, Decimal]:
    """
    Calculate taxable base amount, tax amount, and gross amount.
    
    If is_inclusive=True:
        gross_amount = amount
        base_amount = gross_amount / (1 + rate / 100)
        tax_amount = gross_amount - base_amount
    If is_inclusive=False:
        base_amount = amount
        tax_amount = base_amount * (rate / 100)
        gross_amount = base_amount + tax_amount
    """
    amount = Decimal(str(amount))
    rate = tax_rate.rate

    if rate == Decimal('0.00'):
        return {
            'base_amount': amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'tax_amount': Decimal('0.00'),
            'gross_amount': amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'rate': rate,
        }

    if is_inclusive:
        factor = Decimal('1.00') + (rate / Decimal('100.00'))
        base_amount = (amount / factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tax_amount = (amount - base_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        gross_amount = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        base_amount = amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tax_amount = (base_amount * (rate / Decimal('100.00'))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        gross_amount = (base_amount + tax_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        'base_amount': base_amount,
        'tax_amount': tax_amount,
        'gross_amount': gross_amount,
        'rate': rate,
    }


def get_default_tax_rate(company: Company) -> Optional[TaxRate]:
    """
    Retrieve the default tax rate for a company (or fallback to active 16% standard VAT).
    """
    default = TaxRate.objects.filter(company=company, is_default=True, is_active=True).first()
    if not default:
        default = TaxRate.objects.filter(company=company, is_active=True).first()
    return default
