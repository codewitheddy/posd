"""
Model Import Reference - ALWAYS USE THIS FILE FOR IMPORTS
==========================================================

This file provides the correct model names to prevent import errors.
ALWAYS import models from here instead of directly from models.py

Common Mistakes to Avoid:
- ❌ Payment (doesn't exist)
- ✅ SalePayment (correct)

Usage:
    from pos.model_imports import (
        Sale, SaleItem, SalePayment,
        Product, Customer, PaymentMethod
    )
"""

# Re-export only commonly used models
from .models import (
    # Core models for sync
    Sale,
    SaleItem,
    SalePayment,  # ⚠️ NOT "Payment" - use SalePayment
    Product,
    Customer,
    PaymentMethod,
    
    # Business
    Business,
    BusinessMembership,
    
    # POS
    POSSession,
    ZReport,
)

# Aliases for common mistakes (will raise helpful errors)
class _PaymentDoesNotExist:
    def __init__(self, *args, **kwargs):
        raise ImportError(
            "❌ 'Payment' model does not exist!\n"
            "✅ Use 'SalePayment' instead.\n\n"
            "Correct import:\n"
            "    from pos.model_imports import SalePayment\n\n"
            "Or:\n"
            "    from pos.models import SalePayment"
        )

Payment = _PaymentDoesNotExist
