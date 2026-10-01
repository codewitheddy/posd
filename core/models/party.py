"""
Core Shared Party Model (Customer / Vendor / Counterparty)
Provides a unified counterparty model across POS, Sales, Purchasing, and Accounting.
"""
from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from core.models.base import CompanyScopedModel, AuditedModel, SoftDeleteModel, TimeStampedModel


class Party(CompanyScopedModel, AuditedModel, SoftDeleteModel, TimeStampedModel):
    """
    Unified Party entity representing Customers, Vendors, and Suppliers.
    Replaces isolated customer/vendor tables while maintaining legacy bridge mappings.
    """
    PARTY_TYPE_CUSTOMER = 'customer'
    PARTY_TYPE_VENDOR = 'vendor'
    PARTY_TYPE_BOTH = 'both'
    PARTY_TYPE_INTERNAL = 'internal'

    PARTY_TYPE_CHOICES = [
        (PARTY_TYPE_CUSTOMER, 'Customer / Debtor'),
        (PARTY_TYPE_VENDOR, 'Vendor / Creditor'),
        (PARTY_TYPE_BOTH, 'Customer & Vendor'),
        (PARTY_TYPE_INTERNAL, 'Internal / Inter-Branch'),
    ]

    PAYMENT_TERMS_IMMEDIATE = 'immediate'
    PAYMENT_TERMS_NET15 = 'net_15'
    PAYMENT_TERMS_NET30 = 'net_30'
    PAYMENT_TERMS_NET60 = 'net_60'
    PAYMENT_TERMS_NET90 = 'net_90'

    PAYMENT_TERMS_CHOICES = [
        (PAYMENT_TERMS_IMMEDIATE, 'Immediate / Cash on Delivery'),
        (PAYMENT_TERMS_NET15, 'Net 15 Days'),
        (PAYMENT_TERMS_NET30, 'Net 30 Days'),
        (PAYMENT_TERMS_NET60, 'Net 60 Days'),
        (PAYMENT_TERMS_NET90, 'Net 90 Days'),
    ]

    party_type = models.CharField(
        max_length=20,
        choices=PARTY_TYPE_CHOICES,
        default=PARTY_TYPE_CUSTOMER,
        db_index=True,
    )
    code = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Unique Party Code e.g. CUST-0001, VEND-0001",
    )
    name = models.CharField(max_length=255, db_index=True)
    legal_name = models.CharField(max_length=255, blank=True)
    tax_pin = models.CharField(max_length=50, blank=True, db_index=True, help_text="KRA PIN or Tax Registration ID")
    
    # Contact Details
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True, db_index=True)
    alternate_phone = models.CharField(max_length=50, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    
    # Physical / Billing Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, default='Nairobi')
    county = models.ForeignKey(
        'core.KenyaCounty',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parties',
    )
    postal_code = models.CharField(max_length=20, blank=True)
    
    # Credit & Commercial Terms
    credit_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Maximum allowed credit balance",
    )
    credit_period_days = models.PositiveIntegerField(default=0, help_text="Standard credit terms in days")
    payment_terms = models.CharField(
        max_length=20,
        choices=PAYMENT_TERMS_CHOICES,
        default=PAYMENT_TERMS_IMMEDIATE,
    )
    
    # Banking Info (for vendor disbursements & refunds)
    bank = models.ForeignKey(
        'core.KenyaBank',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parties',
    )
    bank_account_name = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    mpesa_paybill = models.CharField(max_length=30, blank=True)
    mpesa_account_reference = models.CharField(max_length=50, blank=True)

    # Status & Flags
    is_active = models.BooleanField(default=True, db_index=True)
    is_tax_exempt = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    # Legacy Backward-Compatibility Cross-References
    legacy_pos_customer_id = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_pos_supplier_id = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_accounting_customer_id = models.IntegerField(null=True, blank=True, db_index=True)
    legacy_accounting_vendor_id = models.IntegerField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Party'
        verbose_name_plural = 'Parties'
        ordering = ['name']
        unique_together = [['company', 'code']]
        indexes = [
            models.Index(fields=['company', 'party_type', 'is_active']),
            models.Index(fields=['company', 'tax_pin']),
            models.Index(fields=['company', 'phone']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(credit_limit__gte=0),
                name='core_party_credit_limit_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def is_customer(self) -> bool:
        return self.party_type in [self.PARTY_TYPE_CUSTOMER, self.PARTY_TYPE_BOTH]

    @property
    def is_vendor(self) -> bool:
        return self.party_type in [self.PARTY_TYPE_VENDOR, self.PARTY_TYPE_BOTH]
