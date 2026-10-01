"""
Core Unit of Measure Service
Handles unit conversions between compatible units of measure.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from core.models.uom import UnitOfMeasure, UOMConversion
from core.models.organization import Company


def convert_quantity(
    quantity: Decimal,
    from_uom: UnitOfMeasure,
    to_uom: UnitOfMeasure,
    company: Company,
) -> Decimal:
    """
    Convert a quantity from one UOM to another.
    If same UOM, returns quantity directly.
    Checks direct conversion, inverse conversion, or base unit bridging.
    """
    quantity = Decimal(str(quantity))
    if from_uom.id == to_uom.id:
        return quantity

    if from_uom.category != to_uom.category:
        raise ValueError(
            f"Cannot convert between incompatible UOM categories: {from_uom.category} and {to_uom.category}"
        )

    # 1. Direct Conversion
    conv = UOMConversion.objects.filter(
        company=company,
        from_uom=from_uom,
        to_uom=to_uom,
    ).first()
    if conv:
        return (quantity * conv.conversion_factor).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    # 2. Inverse Conversion
    conv_inv = UOMConversion.objects.filter(
        company=company,
        from_uom=to_uom,
        to_uom=from_uom,
    ).first()
    if conv_inv:
        return (quantity / conv_inv.conversion_factor).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    raise ValueError(f"No conversion rule defined between {from_uom.code} and {to_uom.code}")
