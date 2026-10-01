"""
Core Party Service
Business logic for managing unified counterparties (Customers, Vendors, Suppliers).
"""
import logging
from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import transaction
from django.core.exceptions import ValidationError
from core.models.party import Party
from core.models.organization import Company

logger = logging.getLogger(__name__)


@transaction.atomic
def create_party(
    company: Company,
    name: str,
    party_type: str = Party.PARTY_TYPE_CUSTOMER,
    code: Optional[str] = None,
    tax_pin: str = '',
    email: str = '',
    phone: str = '',
    credit_limit: Decimal = Decimal('0.00'),
    credit_period_days: int = 0,
    payment_terms: str = Party.PAYMENT_TERMS_IMMEDIATE,
    created_by=None,
    **kwargs,
) -> Party:
    """
    Create a new party with automatic code generation if not provided.
    """
    if not code:
        prefix = 'CUST' if party_type == Party.PARTY_TYPE_CUSTOMER else ('VEND' if party_type == Party.PARTY_TYPE_VENDOR else 'PRT')
        from core.numbering.service import next_document_number
        code = next_document_number(
            document_type=f'party_{party_type}',
            company=company,
            prefix=prefix,
            format_pattern='{prefix}-{seq:05d}',
        )

    party = Party(
        company=company,
        code=code,
        name=name.strip(),
        party_type=party_type,
        tax_pin=tax_pin.strip().upper() if tax_pin else '',
        email=email.strip().lower() if email else '',
        phone=phone.strip() if phone else '',
        credit_limit=Decimal(str(credit_limit)),
        credit_period_days=credit_period_days,
        payment_terms=payment_terms,
        created_by=created_by,
        **kwargs,
    )
    party.full_clean()
    party.save()
    logger.info("Created Party %s (%s) for company %s", party.name, party.code, company.name)
    return party


@transaction.atomic
def update_party(
    party: Party,
    updated_by=None,
    **fields: Any,
) -> Party:
    """
    Update fields on an existing party.
    """
    for field, value in fields.items():
        if hasattr(party, field):
            setattr(party, field, value)
    
    if updated_by:
        party.updated_by = updated_by

    party.full_clean()
    party.save()
    logger.info("Updated Party %s (%s)", party.name, party.code)
    return party


def check_credit_limit(party: Party, requested_amount: Decimal, current_outstanding: Decimal) -> bool:
    """
    Verify if the requested credit sale violates the party's credit limit.
    Returns True if allowed, False if credit limit exceeded.
    """
    if party.credit_limit <= Decimal('0.00'):
        # 0.00 credit limit means cash only
        return False
    
    total_after_sale = current_outstanding + requested_amount
    return total_after_sale <= party.credit_limit
