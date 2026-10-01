"""
Core Selectors
Optimized query helpers for Core models.
"""
from typing import Optional
from django.db.models import QuerySet, Q
from core.models.party import Party
from core.models.tax import TaxRate
from core.models.uom import UnitOfMeasure
from core.models.currency import Currency, ExchangeRate
from core.models.organization import Company


def get_parties(
    company: Company,
    party_type: Optional[str] = None,
    is_active: bool = True,
    search: Optional[str] = None,
) -> QuerySet[Party]:
    """Retrieve parties scoped to company with optional filters."""
    qs = Party.objects.filter(company=company, is_active=is_active)
    if party_type:
        if party_type in [Party.PARTY_TYPE_CUSTOMER, Party.PARTY_TYPE_VENDOR]:
            qs = qs.filter(Q(party_type=party_type) | Q(party_type=Party.PARTY_TYPE_BOTH))
        else:
            qs = qs.filter(party_type=party_type)

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(code__icontains=search) |
            Q(tax_pin__icontains=search) |
            Q(phone__icontains=search)
        )
    return qs.select_related('county', 'bank')


def get_customers(company: Company, is_active: bool = True) -> QuerySet[Party]:
    """Retrieve all customers for a company."""
    return get_parties(company, party_type=Party.PARTY_TYPE_CUSTOMER, is_active=is_active)


def get_vendors(company: Company, is_active: bool = True) -> QuerySet[Party]:
    """Retrieve all suppliers/vendors for a company."""
    return get_parties(company, party_type=Party.PARTY_TYPE_VENDOR, is_active=is_active)


def get_tax_rates(company: Company, is_active: bool = True) -> QuerySet[TaxRate]:
    """Retrieve all tax rates for a company."""
    return TaxRate.objects.filter(company=company, is_active=is_active).order_by('-rate')


def get_units_of_measure(
    company: Company,
    category: Optional[str] = None,
    is_active: bool = True,
) -> QuerySet[UnitOfMeasure]:
    """Retrieve all units of measure for a company."""
    qs = UnitOfMeasure.objects.filter(company=company, is_active=is_active)
    if category:
        qs = qs.filter(category=category)
    return qs.order_by('name')
