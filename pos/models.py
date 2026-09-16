from django.db import models
from django.utils import timezone
from decimal import Decimal
from datetime import time
from django.db.models import Sum
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from .image_utils import ImageOptimizer, generate_upload_path
import uuid
import threading
import re

# Thread-local storage for current request (used by AuditModelMixin)
_audit_request = threading.local()


def set_audit_request(request):
    """Call this in middleware or views to attach request to audit logs"""
    _audit_request.value = request


def get_audit_request():
    return getattr(_audit_request, 'value', None)


class AuditModelMixin:
    """
    Mixin that auto-logs create/update/delete to ActivityLog.
    Add to any model that needs full audit trails.
    Usage: class MyModel(AuditModelMixin, models.Model): ...
    """
    _audit_exclude_fields = {'updated_at', 'created_at'}

    def _get_audit_description(self, action):
        return f"{action.capitalize()} {self.__class__.__name__}: {self}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        action = 'create' if is_new else 'update'
        super().save(*args, **kwargs)
        try:
            from .models import ActivityLog
            request = get_audit_request()
            user = getattr(request, 'user', None) if request else None
            business = getattr(self, 'business', None)
            ActivityLog.log_activity(
                user=user if (user and getattr(user, 'is_authenticated', False)) else None,
                action_type=action,
                description=self._get_audit_description(action),
                model_name=self.__class__.__name__,
                object_id=self.pk,
                request=request,
                business=business,
                entity_type=self.__class__.__name__,
                entity_id=str(self.pk),
            )
        except Exception:
            pass  # Never let audit logging break the main operation

    def delete(self, *args, **kwargs):
        description = self._get_audit_description('delete')
        pk = self.pk
        business = getattr(self, 'business', None)
        super().delete(*args, **kwargs)
        try:
            from .models import ActivityLog
            request = get_audit_request()
            user = getattr(request, 'user', None) if request else None
            ActivityLog.log_activity(
                user=user if (user and getattr(user, 'is_authenticated', False)) else None,
                action_type='delete',
                description=description,
                model_name=self.__class__.__name__,
                object_id=pk,
                request=request,
                business=business,
                entity_type=self.__class__.__name__,
                entity_id=str(pk),
            )
        except Exception:
            pass


class CacheInvalidationMixin:
    """
    Mixin that invalidates relevant cache keys after save/delete.
    Apply to Product, Category, BusinessSettings, PaymentMethod, LoyaltyReward, Sale.
    """
    _cache_fn_map = {
        'product': 'invalidate_products',
        'category': 'invalidate_categories',
        'businesssettings': 'invalidate_business_settings',
        'paymentmethod': 'invalidate_payment_methods',
        'loyaltyreward': 'invalidate_loyalty_rewards',
        'sale': 'invalidate_dashboard',
    }

    def _invalidate_cache(self):
        try:
            import importlib
            cu = importlib.import_module('pos.cache_utils')
            business = getattr(self, 'business', None)
            if not business:
                return
            business_id = business.pk if hasattr(business, 'pk') else business
            fn_name = self._cache_fn_map.get(self.__class__.__name__.lower())
            if fn_name:
                getattr(cu, fn_name)(business_id)
        except Exception:
            pass

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._invalidate_cache()

    def delete(self, *args, **kwargs):
        self._invalidate_cache()
        super().delete(*args, **kwargs)


from django.utils.text import slugify
from django.core.exceptions import ValidationError


# ==================== MULTI-TENANCY MODELS ====================

class Business(models.Model):
    """
    Business/Tenant model - each business operates independently
    """
    name = models.CharField(max_length=200, help_text="Business name")
    slug = models.SlugField(max_length=200, unique=True, help_text="URL-friendly identifier")
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name='owned_businesses')

    # Business details
    description = models.TextField(blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=True, help_text="Trial period active")
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    # Subscription (for future billing)
    subscription_plan = models.CharField(
        max_length=50,
        choices=[
            ('trial', 'Free Trial (30 Days)'),
            ('paid', 'Annual Subscription'),
        ],
        default='trial'
    )
    
    # License Management
    license_expires_at = models.DateTimeField(null=True, blank=True, help_text='License expiration date')
    license_status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('suspended', 'Suspended'),
        ],
        default='active',
        help_text='Current license status'
    )
    
    # KRA Tax Compliance (Kenya)
    kra_pin = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="KRA PIN Number (e.g., A001234567X)"
    )
    cu_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text="Control Unit Number from KRA TIMS"
    )
    cu_serial_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="CU Device Serial Number"
    )
    tims_enabled = models.BooleanField(
        default=False,
        help_text="Whether TIMS integration is enabled"
    )
    tims_last_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last successful TIMS sync timestamp"
    )

    # Setup
    setup_completed = models.BooleanField(default=False, help_text="Whether initial business setup has been completed")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Businesses"
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure unique slug
            original_slug = self.slug
            counter = 1
            while Business.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        
        super().save(*args, **kwargs)
        
        # Create default data for new business
        if is_new:
            self._create_defaults()

    def get_absolute_url(self):
        return f"/b/{self.slug}/"

    @property
    def is_trial_expired(self):
        if not self.is_trial or not self.trial_ends_at:
            return False
        return timezone.now() > self.trial_ends_at
    
    @property
    def is_license_expired(self):
        """Check if license has expired"""
        if not self.license_expires_at:
            return False
        return timezone.now() > self.license_expires_at
    
    @property
    def days_until_expiry(self):
        """Get number of days until license expires"""
        if not self.license_expires_at:
            return None
        delta = self.license_expires_at - timezone.now()
        return delta.days
    
    def extend_license(self, days):
        """Extend license by specified number of days"""
        from datetime import timedelta
        if self.license_expires_at:
            self.license_expires_at += timedelta(days=days)
        else:
            self.license_expires_at = timezone.now() + timedelta(days=days)
        self.license_status = 'active'
        self.save()
    
    @property
    def plan_display_name(self):
        """Get user-friendly plan name"""
        plan_names = {
            'trial': 'Free Trial (30 Days)',
            'paid': 'Annual Subscription',
        }
        return plan_names.get(self.subscription_plan, self.subscription_plan.title())
    
    def _create_defaults(self):
        """Create default payment method, unit, and category for new business"""
        # Import here to avoid circular imports
        from pos.models import PaymentMethod, UnitOfMeasurement, Category
        
        # Create default payment method: CASH
        PaymentMethod.objects.get_or_create(
            business=self,
            code='CASH',
            defaults={
                'name': 'Cash',
                'is_active': True,
                'requires_reference': False,
                'icon': 'bi-cash',
            }
        )

        # Create default payment method: M-Pesa
        PaymentMethod.objects.get_or_create(
            business=self,
            code='MPESA',
            defaults={
                'name': 'M-Pesa',
                'is_active': True,
                'requires_reference': True,
                'icon': 'bi-phone',
            }
        )
        
        # Create default unit: Pieces
        UnitOfMeasurement.objects.get_or_create(
            business=self,
            name='Pieces',
            defaults={
                'abbreviation': 'pcs',
                'is_active': True,
            }
        )
        
        # Create default category: GENERAL
        Category.objects.get_or_create(
            business=self,
            name='GENERAL',
        )


# ==================== USER MANAGEMENT CONSTANTS ====================

PERMISSION_CODES = [
    'can_create_sale',
    'can_print_receipt',
    'can_refund_sale',
    'can_void_sale',
    'can_edit_price',
    'can_view_cost_price',
    'can_apply_discount',
    'can_exceed_max_discount',
    'can_manage_users',
    'can_view_reports',
    'can_manage_stock',
    'can_record_banking',
    'can_reconcile_banking',
    'can_request_cash_pickup',
    'can_authorize_cash_pickup',
    'can_request_cash_paid_out',
    'can_authorize_cash_paid_out',
    'can_manage_paid_out_receipts',
    'can_manage_supplier_invoices',
    'can_create_supplier_payment',
    'can_authorize_supplier_payment',
    'can_manage_supplier_credits',
]

DEFAULT_PERMISSIONS = {
    'owner':         list(PERMISSION_CODES),
    'admin':         list(PERMISSION_CODES),
    'manager':       ['can_create_sale', 'can_print_receipt', 'can_refund_sale', 'can_void_sale', 'can_edit_price',
                      'can_view_cost_price', 'can_apply_discount',
                      'can_exceed_max_discount', 'can_view_reports', 'can_manage_stock',
                      'can_record_banking', 'can_reconcile_banking',
                      'can_request_cash_pickup', 'can_authorize_cash_pickup',
                      'can_request_cash_paid_out', 'can_authorize_cash_paid_out', 'can_manage_paid_out_receipts',
                      'can_manage_supplier_invoices', 'can_create_supplier_payment', 'can_authorize_supplier_payment', 'can_manage_supplier_credits'],
    'stock_manager': ['can_manage_stock', 'can_view_reports', 'can_view_cost_price', 'can_manage_supplier_invoices', 'can_create_supplier_payment', 'can_manage_supplier_credits'],
    'cashier':       ['can_create_sale', 'can_print_receipt', 'can_view_reports', 'can_apply_discount', 'can_refund_sale', 'can_record_banking', 'can_request_cash_pickup', 'can_request_cash_paid_out', 'can_manage_paid_out_receipts'],
    'sales':         ['can_create_sale', 'can_print_receipt', 'can_view_reports', 'can_apply_discount', 'can_request_cash_paid_out'],
    'viewer':        ['can_view_reports'],
}

DEFAULT_MAX_DISCOUNT = {
    'owner':         Decimal('100.00'),
    'admin':         Decimal('100.00'),
    'manager':       Decimal('50.00'),
    'cashier':       Decimal('20.00'),
    'sales':         Decimal('20.00'),
    'stock_manager': Decimal('0.00'),
    'viewer':        Decimal('0.00'),
}


PERMISSION_LABELS = {
    'can_create_sale': 'Create Sales',
    'can_print_receipt': 'Print Receipts',
    'can_refund_sale': 'Process Refunds',
    'can_void_sale': 'Void Sales',
    'can_edit_price': 'Override Item Price',
    'can_view_cost_price': 'View Cost Price',
    'can_apply_discount': 'Apply Discounts',
    'can_exceed_max_discount': 'Exceed Discount Limit',
    'can_manage_users': 'Manage Team Members',
    'can_view_reports': 'View Reports',
    'can_manage_stock': 'Manage Stock & Purchases',
    'can_record_banking': 'Record Cash Banking & Slips',
    'can_reconcile_banking': 'Reconcile Bank Statements',
    'can_request_cash_pickup': 'Request Till Cash Pickup',
    'can_authorize_cash_pickup': 'Authorize Dual-Custody Cash Pickup',
    'can_request_cash_paid_out': 'Request Till Cash Paid-Out (Petty Expense)',
    'can_authorize_cash_paid_out': 'Authorize Cash Paid-Out (Over-Threshold Approval)',
    'can_manage_paid_out_receipts': 'Attach Paid-Out Receipts & Exceptions',
    'can_manage_supplier_invoices': 'Manage Supplier Invoices (AP Bills)',
    'can_create_supplier_payment': 'Record Supplier Payments',
    'can_authorize_supplier_payment': 'Authorize Supplier Payments (Threshold Sign-off)',
    'can_manage_supplier_credits': 'Manage Supplier Credits & Claims',
}


def get_default_permissions(role):
    """Return (permissions_list, max_discount_pct) for a given role."""
    return (
        list(DEFAULT_PERMISSIONS.get(role, [])),
        DEFAULT_MAX_DISCOUNT.get(role, Decimal('0.00')),
    )


class BusinessMembership(models.Model):
    """
    User membership in a business with role
    """
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Administrator'),
        ('manager', 'Manager'),
        ('stock_manager', 'Stock Manager'),
        ('cashier', 'Cashier'),
        ('sales', 'Sales Associate'),
        ('viewer', 'Viewer'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='business_memberships')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    is_active = models.BooleanField(default=True)
    permissions = models.JSONField(default=list, blank=True, help_text="Granular permission codes for this member")
    max_discount_pct = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))],
        help_text="Maximum discount percentage this member can apply at POS"
    )

    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'business')
        ordering = ['business', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.business.name} ({self.role})"

    def has_permission(self, permission):
        """Check if user has specific permission in this business.
        Supports both legacy broad codes and new granular permission codes."""
        if not self.is_active:
            return False
        # Owners, Administrators, and Superusers have all permissions
        if self.role in ['owner', 'admin'] or (getattr(self, 'user', None) and self.user.is_superuser):
            return True
        # Granular permission check
        if permission in PERMISSION_CODES:
            if self.permissions:
                if permission in self.permissions:
                    return True
                # Essential capabilities fallback for roles where it is a default
                if permission in ['can_create_sale', 'can_print_receipt'] and permission in DEFAULT_PERMISSIONS.get(self.role, []):
                    return True
                return False
            # If permissions field is empty/unset, fall back to role defaults
            return permission in DEFAULT_PERMISSIONS.get(self.role, [])
        # Legacy broad permission check (backward compatibility)
        legacy_map = {
            'owner': ['all'],
            'admin': ['all'],
            'manager': ['view', 'create', 'edit', 'reports', 'users'],
            'stock_manager': ['view', 'create', 'edit', 'stock'],
            'cashier': ['view', 'create', 'pos'],
            'sales': ['view', 'create', 'pos'],
            'viewer': ['view'],
        }
        perms = legacy_map.get(self.role, [])
        return 'all' in perms or permission in perms

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_role = None
        if not is_new:
            try:
                old_role = BusinessMembership.objects.filter(pk=self.pk).values_list('role', flat=True).first()
            except Exception:
                pass
        if is_new or old_role != self.role:
            perms, max_disc = get_default_permissions(self.role)
            self.permissions = perms
            self.max_discount_pct = max_disc
            # If caller passed update_fields, ensure new fields are included
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = list(update_fields) + ['permissions', 'max_discount_pct']
        super().save(*args, **kwargs)


class SubscriptionPayment(models.Model):
    """
    Track subscription payments from businesses
    """
    PAYMENT_METHOD_CHOICES = [
        ('mpesa', 'M-Pesa'),
        ('bank_transfer', 'Bank Transfer'),
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('paypal', 'PayPal'),
        ('other', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    PLAN_CHOICES = [
        ('trial', 'Free Trial'),
        ('paid', 'Annual Subscription'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='subscription_payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Payment amount')
    currency = models.CharField(max_length=10, default='KES')
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES, default='mpesa')
    payment_reference = models.CharField(max_length=200, blank=True, help_text='Transaction ID or reference number')
    payment_date = models.DateTimeField(help_text='Date payment was received')
    
    # Subscription period
    period_start = models.DateField(help_text='Subscription period start date')
    period_end = models.DateField(help_text='Subscription period end date')
    plan = models.CharField(max_length=50, choices=PLAN_CHOICES)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    notes = models.TextField(blank=True, help_text='Additional notes about this payment')
    
    # Audit
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Subscription Payment'
        verbose_name_plural = 'Subscription Payments'
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['business', '-payment_date']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.business.name} - {self.currency} {self.amount} ({self.payment_date.strftime('%Y-%m-%d')})"
    
    def save(self, *args, **kwargs):
        # Auto-update business license expiry when payment is completed
        if self.status == 'completed' and self.period_end:
            self.business.license_expires_at = timezone.make_aware(
                timezone.datetime.combine(self.period_end, timezone.datetime.max.time())
            )
            self.business.license_status = 'active'
            self.business.subscription_plan = self.plan
            self.business.save()
        super().save(*args, **kwargs)


class Category(CacheInvalidationMixin, models.Model):
    """Product categories for organization"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
        unique_together = [['business', 'name']]

    def __str__(self):
        return self.name


class Brand(models.Model):
    """Product brands"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='brands')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = [['business', 'name']]

    def __str__(self):
        return self.name


class UnitOfMeasurement(models.Model):
    """Units of measurement for products (kg, L, m, etc.)"""
    UNIT_TYPE_CHOICES = [
        ('weight', 'Weight'),
        ('volume', 'Volume'),
        ('length', 'Length'),
        ('area', 'Area'),
        ('count', 'Count/Pieces'),
        ('other', 'Other'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='units')
    name = models.CharField(max_length=50, help_text="Unit name (e.g., Kilogram, Liter)")
    abbreviation = models.CharField(max_length=10, help_text="Short form (e.g., kg, L, m)")
    unit_type = models.CharField(max_length=20, choices=UNIT_TYPE_CHOICES, default='count')
    base_unit = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                   help_text="Base unit for conversion (e.g., kg for g)")
    conversion_factor = models.DecimalField(max_digits=10, decimal_places=4, default=1,
                                           help_text="Factor to convert to base unit (e.g., 0.001 for g to kg)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['unit_type', 'name']
        unique_together = [['business', 'abbreviation']]
        verbose_name_plural = "Units of Measurement"
    
    def __str__(self):
        return f"{self.name} ({self.abbreviation})"
    
    def convert_to_base(self, quantity):
        """Convert quantity to base unit"""
        return quantity * self.conversion_factor
    
    def convert_from_base(self, quantity):
        """Convert quantity from base unit to this unit"""
        if self.conversion_factor == 0:
            return 0
        return quantity / self.conversion_factor


def product_image_path(instance, filename):
    """Generate upload path for product images"""
    from .image_utils import generate_upload_path
    return generate_upload_path(instance, filename, 'products')


# ==================== HS CODES ====================

class HSCode(models.Model):
    """
    Harmonized System (HS) Code library — global, shared across all businesses.
    Based on the WCO HS 2022 nomenclature used by Kenya Revenue Authority (KRA).

    Structure:
      chapter   — 2-digit  e.g. "09"
      heading   — 4-digit  e.g. "0901"
      subheading— 6-digit  e.g. "090121"
      code      — full code with optional dots e.g. "0901.21"
    """

    UNIT_CHOICES = [
        ('kg',  'Kilogram (kg)'),
        ('g',   'Gram (g)'),
        ('l',   'Litre (l)'),
        ('ml',  'Millilitre (ml)'),
        ('m',   'Metre (m)'),
        ('m2',  'Square Metre (m²)'),
        ('m3',  'Cubic Metre (m³)'),
        ('pcs', 'Pieces (pcs)'),
        ('doz', 'Dozen'),
        ('u',   'Unit'),
        ('t',   'Tonne (t)'),
        ('',    'No unit'),
    ]

    # Core fields
    code        = models.CharField(max_length=20, unique=True, db_index=True,
                                   help_text="Full HS code e.g. 0901.21 or 090121")
    description = models.CharField(max_length=500,
                                   help_text="Official WCO/KRA description")
    chapter     = models.CharField(max_length=2, db_index=True,
                                   help_text="2-digit chapter e.g. 09")
    heading     = models.CharField(max_length=4, db_index=True,
                                   help_text="4-digit heading e.g. 0901")

    # Tax / duty info
    vat_rate    = models.DecimalField(max_digits=5, decimal_places=2, default=16,
                                      help_text="Standard VAT rate for this code (%)")
    excise_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                      help_text="Excise duty rate (%)")
    import_duty = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                      help_text="Import duty rate (%)")
    is_excisable= models.BooleanField(default=False)
    unit        = models.CharField(max_length=10, choices=UNIT_CHOICES, default='',
                                   blank=True, help_text="Standard unit of quantity")

    # Notes
    notes       = models.TextField(blank=True,
                                   help_text="Additional notes, KRA-specific guidance")
    is_active   = models.BooleanField(default=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'HS Code'
        verbose_name_plural = 'HS Codes'
        indexes = [
            models.Index(fields=['chapter']),
            models.Index(fields=['heading']),
        ]

    def __str__(self):
        return f"{self.code} — {self.description}"

    def save(self, *args, **kwargs):
        # Auto-derive chapter and heading from code
        clean = self.code.replace('.', '').replace(' ', '')
        self.chapter = clean[:2] if len(clean) >= 2 else clean
        self.heading = clean[:4] if len(clean) >= 4 else clean
        super().save(*args, **kwargs)

    @property
    def display_code(self):
        """Return code formatted with dot e.g. 0901.21"""
        clean = self.code.replace('.', '')
        if len(clean) >= 6:
            return f"{clean[:4]}.{clean[4:]}"
        if len(clean) == 4:
            return clean
        return self.code


# ==================== VAT CODES ====================

class VATCode(CacheInvalidationMixin, AuditModelMixin, models.Model):
    """
    VAT Code for grouping products with the same tax treatment.
    Each business can define custom VAT codes for their products.
    
    Examples:
    - Standard Rated (16%)
    - Zero Rated (0%)
    - Exempt (0%)
    - Special Rate (varies by product type)
    """
    
    RATE_CHOICES = [
        (Decimal('0.00'), '0% (Zero Rated)'),
        (Decimal('8.00'), '8% (Half Rate)'),
        (Decimal('14.00'), '14% (Reduced Rate)'),
        (Decimal('16.00'), '16% (Standard Rate)'),
        (Decimal('20.00'), '20% (High Rate)'),
    ]
    
    business = models.ForeignKey(
        'Business',
        on_delete=models.CASCADE,
        related_name='vat_codes',
        help_text="Business/tenant this VAT code belongs to"
    )
    code = models.CharField(
        max_length=20,
        help_text="Unique VAT code identifier (e.g., VAT-STD, VAT-ZERO, VAT-EXEMPT)"
    )
    name = models.CharField(
        max_length=100,
        help_text="Descriptive name (e.g., 'Standard Rated (16%)')"
    )
    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('16.00'),
        help_text="VAT rate as percentage (e.g., 16.00 for 16%)"
    )
    description = models.TextField(
        blank=True,
        help_text="Additional details about when this VAT code applies"
    )
    
    # HS Code mapping (optional)
    hs_code_chapter = models.CharField(
        max_length=2,
        blank=True,
        null=True,
        help_text="HS Code chapter (2-digit) this VAT code typically applies to (e.g., '09')"
    )
    
    # Excise duty information (optional)
    excise_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Excise duty rate percentage (if applicable)"
    )
    is_excisable = models.BooleanField(
        default=False,
        help_text="Whether products with this VAT code are subject to excise duty"
    )
    
    # Import duty (for imported goods)
    import_duty = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Import duty rate percentage (if applicable)"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive VAT codes cannot be assigned to new products"
    )
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'VAT Code'
        verbose_name_plural = 'VAT Codes'
        ordering = ['code']
        unique_together = [['business', 'code']]
        indexes = [
            models.Index(fields=['business', 'is_active']),
            models.Index(fields=['business', 'vat_rate']),
            models.Index(fields=['business', 'hs_code_chapter']),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name} ({self.vat_rate}%)"
    
    def get_display_name(self):
        """Get formatted display name with rate"""
        return f"{self.name} ({self.vat_rate}%)"
    
    def get_total_tax_rate(self):
        """Get total tax rate (VAT + excise + import duty)"""
        return self.vat_rate + self.excise_rate + self.import_duty
    
    def save(self, *args, **kwargs):
        # Validate VAT rate is between 0 and 100
        if not (Decimal('0') <= self.vat_rate <= Decimal('100')):
            raise ValidationError("VAT rate must be between 0 and 100")
        
        # Validate excise rate
        if not (Decimal('0') <= self.excise_rate <= Decimal('100')):
            raise ValidationError("Excise rate must be between 0 and 100")
        
        # Validate import duty
        if not (Decimal('0') <= self.import_duty <= Decimal('100')):
            raise ValidationError("Import duty must be between 0 and 100")
        
        super().save(*args, **kwargs)


class Product(CacheInvalidationMixin, models.Model):
    """Products available for sale"""
    TAX_CLASS_CHOICES = [
        ('standard', 'Standard (16% VAT)'),
        ('zero_rated', 'Zero Rated (0% VAT)'),
        ('exempt', 'Exempt (No VAT)'),
    ]

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Product description")
    product_code = models.CharField(max_length=50, blank=True, null=True, help_text="Internal product code or SKU")
    barcode = models.CharField(max_length=100, blank=True, help_text="Barcode for scanning (EAN, UPC, etc.)")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    brand = models.ForeignKey('Brand', on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    unit = models.ForeignKey(UnitOfMeasurement, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name='products', help_text="Unit of measurement (e.g., kg, L, pcs)")
    is_active = models.BooleanField(default=True, help_text="Active products appear in POS and reports")
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Cost price (what you pay to stock the product) - REQUIRED"
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Selling price (what customers pay)")
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Wholesale / bulk customer price")
    minimum_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Minimum allowed selling price")
    tax_class = models.CharField(max_length=20, choices=TAX_CLASS_CHOICES, default='standard', help_text="Tax classification for this product")
    vat_code = models.ForeignKey(
        'VATCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        help_text="VAT Code for tax treatment (if not set, uses tax_class)"
    )
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=0, help_text="Current stock quantity")
    low_stock_threshold = models.DecimalField(max_digits=10, decimal_places=3, default=10, help_text="Alert when stock falls below this level")
    reorder_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=0, blank=True, help_text="Suggested reorder quantity")
    preferred_supplier = models.ForeignKey('Supplier', on_delete=models.SET_NULL, null=True, blank=True,
                                           related_name='preferred_products', help_text="Default supplier for reordering")
    lead_time_days = models.PositiveIntegerField(default=0, blank=True, help_text="Expected lead time from supplier in days")
    expiry_date = models.DateField(blank=True, null=True, help_text="Product expiry date (optional)")
    expiry_alert_days = models.IntegerField(default=7, help_text="Alert X days before expiry")

    # Multi-unit selling (e.g., sell by piece or by carton)
    bulk_unit_name = models.CharField(max_length=50, blank=True, help_text="Name of bulk unit (e.g., Carton, Box, Sack)")
    bulk_unit_quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True,
                                             validators=[MinValueValidator(Decimal('0.001'))],
                                             help_text="How many base units in one bulk unit (e.g., 12 pieces in a carton)")
    bulk_unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                          validators=[MinValueValidator(Decimal('0'))],
                                          help_text="Selling price for one bulk unit")
    unit_barcode = models.CharField(max_length=100, blank=True, help_text="Barcode for the individual base unit (distinct from bulk barcode)")
    bulk_low_stock_threshold = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True,
                                                   validators=[MinValueValidator(Decimal('0'))],
                                                   help_text="Alert when stock falls below this many bulk units")
    bulk_discount_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                              validators=[MinValueValidator(Decimal('0'))],
                                              help_text="Per-unit price when customer buys at least one full bulk unit quantity")

    # Variable pricing (for items sold by weight/volume)
    is_variable_price = models.BooleanField(default=False, help_text="Enable variable pricing (price calculated by weight/quantity)")
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                         help_text="Price per unit (e.g., price per 100g, per kg, per liter)")
    pricing_unit_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('1.000'),
                                                help_text="Quantity for pricing unit (e.g., 100 for 'per 100g', 1 for 'per kg')")
    
    # Image field with optimization
    image = models.ImageField(
        upload_to=product_image_path,
        blank=True,
        null=True,
        help_text="Product image (will be automatically optimized)"
    )
    
    # Kenyan Tax Compliance Fields
    hs_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Harmonized System Code for tax classification (e.g., 0901.21)"
    )
    hs_code_description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Description of HS Code category"
    )
    # Structured FK to the HS Code library (preferred over free-text fields above)
    hs_code_ref = models.ForeignKey(
        'HSCode',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='products',
        help_text="Link to the HS Code library entry"
    )
    is_excisable = models.BooleanField(
        default=False,
        help_text="Whether this product is subject to excise duty"
    )
    excise_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Excise duty rate percentage"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['business', 'product_code']]
        ordering = ['name']

    @property
    def sku(self):
        return self.product_code or ''

    @property
    def selling_price(self):
        return self.unit_price

    def __str__(self):
        return f"{self.name} - KES {self.unit_price}"
    
    def get_tax_rate(self):
        """Get the tax rate for this product based on tax class"""
        tax_rates = {
            'standard': Decimal('16.00'),
            'zero_rated': Decimal('0.00'),
            'exempt': Decimal('0.00'),
        }
        return tax_rates.get(self.tax_class, Decimal('16.00'))
    
    def save(self, *args, **kwargs):
        # Validate cost_price is provided and greater than 0
        if self.cost_price is None or self.cost_price <= 0:
            raise ValueError("Cost price is required and must be greater than 0")
        
        # Validate unit_price is greater than 0
        if self.unit_price is None or self.unit_price <= 0:
            raise ValueError("Selling price is required and must be greater than 0")
        
        # Auto-generate product_code if not provided
        if not self.product_code:
            # Generate format: PRD-XXXX (sequential number per business)
            last_product = Product.objects.filter(
                business=self.business,
                product_code__startswith='PRD-'
            ).order_by('-product_code').first()
            
            if last_product and last_product.product_code:
                try:
                    last_num = int(last_product.product_code.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            
            self.product_code = f'PRD-{new_num:04d}'
        
        # Optimize image on upload — only for new uploads, not existing saved images
        if self.image and hasattr(self.image, 'file'):
            # Only process if it's a newly uploaded file (not an existing ImageFieldFile)
            from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
            is_new_upload = isinstance(self.image.file, (InMemoryUploadedFile, TemporaryUploadedFile))
            if not is_new_upload:
                # Check if the underlying file object is an upload type
                try:
                    is_new_upload = hasattr(self.image.file, 'content_type')
                except Exception:
                    is_new_upload = False
            if is_new_upload:
                try:
                    is_valid, error = ImageOptimizer.validate_image(self.image)
                    if not is_valid:
                        raise ValueError(error)
                    self.image = ImageOptimizer.optimize_image(self.image)
                except (FileNotFoundError, IOError, OSError):
                    pass
        
        super().save(*args, **kwargs)
    
    def get_image_url(self):
        """Get image URL or placeholder (handles missing files gracefully)"""
        if self.image:
            try:
                # Try to get the URL
                return self.image.url
            except (ValueError, FileNotFoundError, IOError, OSError):
                # File doesn't exist, return placeholder
                pass
        return '/static/images/no-image.png'  # Placeholder
    
    @property
    def sku(self):
        """Return product code or barcode as SKU identifier"""
        return self.product_code or self.barcode or ''

    def is_low_stock(self):
        """Check if product is low on stock"""
        return self.stock_quantity <= self.low_stock_threshold

    def bulk_stock_level(self):
        """Current stock expressed in bulk units (None if not a bulk product)."""
        if self.bulk_unit_quantity:
            return self.stock_quantity / self.bulk_unit_quantity
        return None

    def is_bulk_low_stock(self):
        """True when bulk_low_stock_threshold is set and bulk stock level is at or below it."""
        if self.bulk_low_stock_threshold and self.bulk_unit_quantity:
            return self.bulk_stock_level() <= self.bulk_low_stock_threshold
        return False

    def is_out_of_stock(self):
        """Check if product is out of stock"""
        return self.stock_quantity <= 0
    
    def has_sufficient_stock(self, quantity):
        """Check if there's enough stock for a sale"""
        return self.stock_quantity >= quantity
    
    def deduct_stock(self, quantity):
        """Deduct stock after a sale"""
        if self.has_sufficient_stock(quantity):
            self.stock_quantity -= quantity
            self.save()
            return True
        return False
    
    def add_stock(self, quantity):
        """Add stock (for restocking)"""
        self.stock_quantity += quantity
        self.save()
    
    @property
    def stock_status(self):
        """Get stock status as string"""
        if self.is_out_of_stock():
            return "Out of Stock"
        elif self.is_low_stock():
            return "Low Stock"
        else:
            return "In Stock"
    
    def is_expired(self):
        """Check if product has expired"""
        if not self.expiry_date:
            return False
        from django.utils import timezone
        return self.expiry_date < timezone.now().date()
    
    def is_expiring_soon(self):
        """Check if product is expiring soon"""
        if not self.expiry_date or self.is_expired():
            return False
        from django.utils import timezone
        from datetime import timedelta
        alert_date = timezone.now().date() + timedelta(days=self.expiry_alert_days)
        return self.expiry_date <= alert_date
    
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if not self.expiry_date:
            return None
        from django.utils import timezone
        delta = self.expiry_date - timezone.now().date()
        return delta.days
    
    @property
    def expiry_status(self):
        """Get expiry status as string"""
        if not self.expiry_date:
            return "No Expiry"
        elif self.is_expired():
            return "Expired"
        elif self.is_expiring_soon():
            days = self.days_until_expiry()
            return f"Expires in {days} day{'s' if days != 1 else ''}"
        else:
            return "Good"
    
    def get_profit_per_unit(self):
        """Calculate profit per unit"""
        return self.unit_price - self.cost_price
    
    def get_profit_margin_percentage(self):
        """Calculate profit margin as percentage"""
        if self.unit_price == 0:
            return 0
        profit = self.get_profit_per_unit()
        return (profit / self.unit_price) * 100
    
    def get_markup_percentage(self):
        """Calculate markup percentage (profit / cost)"""
        if self.cost_price == 0:
            return 0
        profit = self.get_profit_per_unit()
        return (profit / self.cost_price) * 100

    @property
    def total_cost_value(self):
        """Total valuation based on cost price"""
        if self.stock_quantity and self.cost_price:
            return self.stock_quantity * self.cost_price
        return Decimal('0.00')

    @property
    def total_retail_value(self):
        """Total valuation based on selling price"""
        if self.stock_quantity and self.unit_price:
            return self.stock_quantity * self.unit_price
        return Decimal('0.00')
    
    # Multi-unit selling methods
    def has_bulk_unit(self):
        """Check if product has bulk unit configured"""
        return bool(self.bulk_unit_name and self.bulk_unit_quantity and self.bulk_unit_price)
    
    def get_base_unit_name(self):
        """Get base unit name for display"""
        if self.unit:
            return self.unit.abbreviation
        return "unit"
    
    def get_bulk_units_available(self):
        """Calculate how many bulk units are available in stock"""
        if not self.has_bulk_unit():
            return 0
        return int(self.stock_quantity / self.bulk_unit_quantity)
    
    def convert_bulk_to_base(self, bulk_quantity):
        """Convert bulk unit quantity to base units"""
        if not self.has_bulk_unit():
            return bulk_quantity
        return bulk_quantity * self.bulk_unit_quantity
    
    def has_sufficient_stock_bulk(self, bulk_quantity):
        """Check if there's enough stock for bulk unit sale"""
        base_quantity = self.convert_bulk_to_base(bulk_quantity)
        return self.has_sufficient_stock(base_quantity)
    
    # Variable pricing methods
    def calculate_price_for_quantity(self, quantity):
        """Calculate price for a given quantity (for variable pricing)"""
        if not self.is_variable_price or not self.price_per_unit:
            return self.unit_price
        
        # Calculate price based on quantity
        # Formula: (quantity / pricing_unit_quantity) * price_per_unit
        # Example: 110g / 100g * 200 = 220
        price = (Decimal(str(quantity)) / self.pricing_unit_quantity) * self.price_per_unit
        return price.quantize(Decimal('0.01'))
    
    def get_pricing_display(self):
        """Get pricing display string for variable pricing products"""
        if not self.is_variable_price or not self.price_per_unit:
            return f"KES {self.unit_price}"
        
        unit_name = self.unit.abbreviation if self.unit else "unit"
        return f"KES {self.price_per_unit} per {self.pricing_unit_quantity}{unit_name}"


class Sale(AuditModelMixin, CacheInvalidationMixin, models.Model):
    """Sales transactions"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='sales')
    invoice_number = models.CharField(max_length=20, editable=False)
    date = models.DateTimeField(default=timezone.now)
    cashier = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='sales', null=True, blank=True)
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=16)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(max_length=10, choices=[('percentage', 'Percentage'), ('fixed', 'Fixed'), ('points', 'Loyalty Points')], default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Payment tracking
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    change_given = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Credit sale tracking
    is_credit_sale = models.BooleanField(default=False, help_text="Sale made on credit")
    credit_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Amount paid against credit")
    
    # Promotion tracking
    promotion = models.ForeignKey('Promotion', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Shift tracking
    shift = models.ForeignKey('Shift', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    
    # NEW Z-REPORT SYSTEM: Session and locking
    session = models.ForeignKey('POSSession', on_delete=models.PROTECT, null=True, blank=True, related_name='sales', help_text="POS session this sale belongs to")
    is_locked = models.BooleanField(default=False, db_index=True, help_text="Locked after Z-Report generation")
    locked_at = models.DateTimeField(null=True, blank=True, help_text="When this sale was locked")
    
    # TIMS Integration (Kenya)
    tims_invoice_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="TIMS-generated invoice number"
    )
    tims_qr_code = models.TextField(
        blank=True,
        null=True,
        help_text="TIMS QR code data for receipt"
    )
    tims_verification_url = models.URLField(
        blank=True,
        null=True,
        help_text="URL for customer to verify invoice on KRA portal"
    )
    tims_synced = models.BooleanField(
        default=False,
        help_text="Whether this sale has been synced to TIMS"
    )
    tims_sync_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this sale was synced to TIMS"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    branch = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='sales')
    terminal = models.ForeignKey('POSTerminal', null=True, blank=True, on_delete=models.SET_NULL, related_name='sales', help_text="POS Terminal that originated this sale")
    idempotency_key = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Client-generated UUID for offline sync idempotency")
    is_offline_sync = models.BooleanField(default=False, help_text="True if recorded offline and synced later")
    client_created_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when sale was recorded locally on terminal")

    class Meta:
        ordering = ['-date']
        unique_together = [['business', 'invoice_number']]
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'idempotency_key'],
                name='unique_business_sale_idempotency_key',
                condition=models.Q(idempotency_key__isnull=False)
            )
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - KES {self.total}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number: INV-YYYYMMDD-XXXX
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_sale = Sale.objects.filter(business=self.business, invoice_number__startswith=f'INV-{date_str}').order_by('-invoice_number').first()
            if last_sale:
                try:
                    last_num = int(last_sale.invoice_number.split('-')[-1])
                except (ValueError, IndexError):
                    last_num = Sale.objects.filter(business=self.business).count()
                new_num = last_num + 1
            else:
                new_num = 1
            self.invoice_number = f'INV-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)


class SaleItem(models.Model):
    """Individual items in a sale"""
    UNIT_TYPE_CHOICES = [
        ('base', 'Base Unit'),
        ('bulk', 'Bulk Unit'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='sale_items')
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, validators=[MinValueValidator(Decimal('0.001'))])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=255, blank=True, default='', help_text='Per-item note (e.g. no onions, gift wrap)')
    
    # COGS snapshot — cost price at the time of sale (immutable historical record)
    cost_price_at_sale = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cost price snapshotted at time of sale for accurate COGS reporting"
    )

    # Multi-unit tracking
    unit_type = models.CharField(max_length=10, choices=UNIT_TYPE_CHOICES, default='base',
                                 help_text="Which unit was sold")
    unit_name = models.CharField(max_length=50, blank=True,
                                help_text="Name of unit sold (for display)")

    def __str__(self):
        unit_display = f" {self.unit_name}" if self.unit_name else ""
        return f"{self.product.name} x {self.quantity}{unit_display}"

    def save(self, *args, **kwargs):
        self.total_price = Decimal(self.quantity) * self.unit_price
        if not self.business_id and self.sale:
            self.business = self.sale.business
        super().save(*args, **kwargs)


class StockAdjustment(AuditModelMixin, models.Model):
    """Track stock adjustments and changes"""
    ADJUSTMENT_TYPES = [
        ('restock', 'Restock'),
        ('damage', 'Damage/Loss'),
        ('expired', 'Expired Items'),
        ('return', 'Customer Return'),
        ('correction', 'Stock Correction'),
        ('sale', 'Sale'),
        ('bulk_break', 'Bulk Break'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='stock_adjustments')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_adjustments')
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)
    quantity_change = models.IntegerField(help_text="Positive for additions, negative for deductions")
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    branch = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='stock_adjustments')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.product.name} - {self.adjustment_type} ({self.quantity_change:+d})"
    
    def save(self, *args, **kwargs):
        if not self.business_id and self.product:
            self.business = self.product.business
        super().save(*args, **kwargs)


class Supplier(models.Model):
    """Suppliers who provide products"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text="Additional notes about the supplier")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        unique_together = [['business', 'name']]
    
    def __str__(self):
        return self.name
    
    def total_purchases(self):
        """Calculate total amount of all purchases from this supplier based on received quantities"""
        total = Decimal('0.00')
        for purchase in self.purchases.filter(status__in=('received', 'partially_received', 'closed')):
            # Calculate actual received amount
            actual_amount = Decimal('0.00')
            for item in purchase.items.all():
                # Use quantity_received if available, otherwise use ordered quantity
                qty = item.quantity_received if item.quantity_received > 0 else item.quantity
                actual_amount += Decimal(qty) * item.unit_cost
            
            # If no items or all zero, fall back to total_amount
            if actual_amount == Decimal('0.00'):
                actual_amount = purchase.total_amount
            
            total += actual_amount
        
        return total
    
    def purchase_count(self):
        """Count number of purchases from this supplier"""
        return self.purchases.count()
    
    def outstanding_balance(self):
        """Calculate outstanding balance as sum of remaining balances on unpaid purchases"""
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        from django.db.models.functions import Coalesce
        purchases = self.purchases.filter(status__in=('received', 'partially_received', 'closed')).annotate(
            allocated=Coalesce(Sum('payment_allocations__amount'), Decimal('0.00')),
            remaining=ExpressionWrapper(
                F('total_amount') - Coalesce(Sum('payment_allocations__amount'), Decimal('0.00')),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        ).filter(remaining__gt=Decimal('0.00'))
        result = purchases.aggregate(total=Sum('remaining'))['total'] or Decimal('0.00')
        return result
    
    def total_payments(self):
        """Calculate total payments made to this supplier"""
        return self.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def has_received_purchases(self):
        """Check if supplier has any received purchases"""
        return self.purchases.filter(status__in=('received', 'partially_received', 'closed')).exists()


class Purchase(models.Model):
    """Purchase orders from suppliers"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('sent', 'Sent to Supplier'),
        ('pending', 'Pending'),          # legacy / backward compat
        ('ordered', 'Ordered'),          # legacy / backward compat
        ('partially_received', 'Partially Received'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
        ('closed', 'Closed'),
    ]

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='purchases')
    purchase_number = models.CharField(max_length=20, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchases')
    date = models.DateTimeField(default=timezone.now)
    expected_delivery = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    received_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Workflow tracking
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='created_purchases',
    )
    submitted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='submitted_purchases',
    )
    submitted_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_purchases',
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    # Cancellation tracking
    cancellation_reason = models.TextField(blank=True, help_text='Reason for cancelling this purchase order')
    cancelled_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cancelled_purchases',
        help_text='User who cancelled this purchase order'
    )
    cancelled_at = models.DateTimeField(blank=True, null=True, help_text='When this purchase order was cancelled')
    branch = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='purchases')
    
    class Meta:
        ordering = ['-date']
        unique_together = [['business', 'purchase_number']]
    
    def __str__(self):
        return f"{self.purchase_number} - {self.supplier.name}"
    
    def save(self, *args, **kwargs):
        if not self.purchase_number:
            # Generate purchase number: PO-YYYYMMDD-XXXX
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_purchase = Purchase.objects.filter(
                business=self.business,
                purchase_number__startswith=f'PO-{date_str}'
            ).order_by('-purchase_number').first()
            if last_purchase:
                last_num = int(last_purchase.purchase_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.purchase_number = f'PO-{date_str}-{new_num:04d}'
        
        # Validate amounts are not negative
        if self.subtotal < 0 or self.tax_amount < 0 or self.total_amount < 0:
            from django.core.exceptions import ValidationError
            raise ValidationError('Purchase amounts cannot be negative!')
        
        super().save(*args, **kwargs)
    
    def mark_as_received(self, receiving_data=None):
        """
        Mark purchase as received and update stock
        
        Args:
            receiving_data: Optional dict with item-level receiving details
                Format: {
                    'items': [
                        {
                            'item_id': 1,
                            'quantity_received': 95,
                            'quantity_damaged': 5,
                            'notes': 'Broken bottles'
                        },
                        ...
                    ]
                }
        """
        from django.db import transaction

        if self.status in ('received', 'closed', 'cancelled'):
            return False

        has_any_receipt = False

        with transaction.atomic():
            locked_purchase = Purchase.objects.select_for_update().get(pk=self.pk)
            if locked_purchase.status in ('received', 'closed', 'cancelled'):
                return False

            for item in locked_purchase.items.select_related('product').all():
                item_data = None
                if receiving_data and 'items' in receiving_data:
                    item_data = next(
                        (d for d in receiving_data['items'] if d.get('item_id') == item.id),
                        None
                    )

                remaining_before = max(item.quantity - item.quantity_received - item.quantity_damaged, 0)
                if remaining_before <= 0:
                    continue

                if item_data:
                    qty_received = int(item_data.get('quantity_received', 0) or 0)
                    qty_damaged = int(item_data.get('quantity_damaged', 0) or 0)
                    notes = item_data.get('notes', '')
                    expiry_date = item_data.get('expiry_date')
                    batch_number = item_data.get('batch_number', '')
                else:
                    # Backward compatibility: receive only what is still outstanding.
                    qty_received = remaining_before
                    qty_damaged = 0
                    notes = ''
                    expiry_date = None
                    batch_number = ''

                if qty_received < 0 or qty_damaged < 0:
                    return False
                if qty_received + qty_damaged > remaining_before:
                    return False
                if qty_received == 0 and qty_damaged == 0:
                    continue

                has_any_receipt = True
                product = item.product

                item.quantity_received += qty_received
                item.quantity_damaged += qty_damaged
                item.receiving_notes = notes

                update_item_fields = ['quantity_received', 'quantity_damaged', 'receiving_notes']

                if expiry_date:
                    from datetime import datetime
                    try:
                        expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                        item.expiry_date = expiry_date_obj
                        update_item_fields.append('expiry_date')

                        product.expiry_date = expiry_date_obj
                        if product.expiry_alert_days <= 3:
                            product.expiry_alert_days = 7
                    except ValueError:
                        pass

                if batch_number:
                    item.batch_number = batch_number
                    update_item_fields.append('batch_number')

                item.save(update_fields=update_item_fields)

                previous_qty = product.stock_quantity
                if qty_received > 0:
                    product.stock_quantity += Decimal(qty_received)

                product_update_fields = ['stock_quantity']
                if item.expiry_date:
                    product_update_fields.extend(['expiry_date', 'expiry_alert_days'])
                product.save(update_fields=product_update_fields)

                if qty_received > 0:
                    StockAdjustment.objects.create(
                        business=locked_purchase.business,
                        product=product,
                        adjustment_type='restock',
                        quantity_change=qty_received,
                        previous_quantity=int(previous_qty),
                        new_quantity=int(product.stock_quantity),
                        reason=f'Received from {locked_purchase.purchase_number} ({qty_received} of {item.quantity} ordered)'
                    )

                if qty_damaged > 0:
                    StockAdjustment.objects.create(
                        business=locked_purchase.business,
                        product=product,
                        adjustment_type='damage',
                        quantity_change=-qty_damaged,
                        previous_quantity=int(product.stock_quantity),
                        new_quantity=int(product.stock_quantity),
                        reason=f'Damaged on delivery - {locked_purchase.purchase_number}: {notes}'
                    )

            if not has_any_receipt:
                return False

            has_pending_items = locked_purchase.items.filter(
                quantity_received__lt=models.F('quantity') - models.F('quantity_damaged')
            ).exists()

            locked_purchase.status = 'partially_received' if has_pending_items else 'received'
            locked_purchase.received_date = timezone.now()
            locked_purchase.save(update_fields=['status', 'received_date', 'updated_at'])

            self.status = locked_purchase.status
            self.received_date = locked_purchase.received_date

        return True
    
    def total_allocated(self):
        """Returns total amount allocated from payments"""
        return self.payment_allocations.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def remaining_balance(self):
        """Returns unpaid balance"""
        return self.total_amount - self.total_allocated()
    
    def is_fully_paid(self):
        """Check if purchase is fully paid"""
        return self.remaining_balance() <= Decimal('0.00')
    
    def days_outstanding(self):
        """Calculate days since purchase date"""
        if self.status != 'received' or self.is_fully_paid():
            return 0
        return (timezone.now().date() - self.date.date()).days
    
    def aging_category(self):
        """Return aging category: current, 30, 60, 90+"""
        days = self.days_outstanding()
        if days <= 30:
            return 'current'
        elif days <= 60:
            return '30_days'
        elif days <= 90:
            return '60_days'
        else:
            return '90_plus'


class PurchaseItem(models.Model):
    """Individual items in a purchase order"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='purchase_items')
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True, help_text='Optional item description / override')
    quantity = models.PositiveIntegerField(help_text='Quantity ordered')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text='Discount percentage (0-100)')
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField(blank=True, null=True, help_text='Expiry date for this batch of products')
    batch_number = models.CharField(max_length=100, blank=True, help_text='Batch or lot number for tracking')
    
    # Receiving details
    quantity_received = models.PositiveIntegerField(default=0, help_text='Actual quantity received (good items)')
    quantity_damaged = models.PositiveIntegerField(default=0, help_text='Quantity damaged or missing')
    receiving_notes = models.TextField(blank=True, help_text='Notes about receiving (damage details, etc.)')
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        discount_factor = Decimal('1') - (self.discount / Decimal('100'))
        self.total_cost = Decimal(self.quantity) * self.unit_cost * discount_factor
        if not self.business_id and self.purchase:
            self.business = self.purchase.business
        super().save(*args, **kwargs)
    
    @property
    def is_fully_received(self):
        """Check if all ordered items were received"""
        return self.quantity_received + self.quantity_damaged >= self.quantity
    
    @property
    def has_discrepancy(self):
        """Check if there's a discrepancy in receiving"""
        return self.quantity_damaged > 0 or (self.quantity_received + self.quantity_damaged) < self.quantity
    
    def is_expired(self):
        """Check if this batch has expired"""
        if not self.expiry_date:
            return False
        from django.utils import timezone
        return self.expiry_date < timezone.now().date()
    
    def is_expiring_soon(self, alert_days=7):
        """Check if this batch is expiring soon"""
        if not self.expiry_date or self.is_expired():
            return False
        from django.utils import timezone
        from datetime import timedelta
        alert_date = timezone.now().date() + timedelta(days=alert_days)
        return self.expiry_date <= alert_date
    
    def days_until_expiry(self):
        """Calculate days until expiry"""
        if not self.expiry_date:
            return None
        from django.utils import timezone
        delta = self.expiry_date - timezone.now().date()
        return delta.days


# ==================== ACCOUNTS PAYABLE & SUPPLIER INVOICES ====================

class SupplierInvoice(models.Model):
    """
    Accounts Payable invoice received from a supplier.
    Represents accrual-based recognition of goods/services expenses before payment.
    """
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partially_paid', 'Partially Paid'),
        ('paid', 'Paid'),
        ('disputed', 'Disputed'),
        ('cancelled', 'Cancelled'),
    ]

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='supplier_invoices')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='invoices')
    invoice_number = models.CharField(max_length=60, db_index=True, help_text="Supplier's original invoice number or internal reference")
    invoice_date = models.DateField(default=timezone.now, db_index=True, help_text="Date invoice was issued by supplier")
    due_date = models.DateField(db_index=True, help_text="Payment due date")
    
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid', db_index=True)
    purchase = models.ForeignKey(Purchase, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    goods_received_note = models.ForeignKey('GoodsReceivedNote', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    
    attachment = models.FileField(upload_to='supplier_invoices/%Y/%m/', null=True, blank=True, help_text="PDF / scan of supplier bill")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_invoices_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-created_at']
        unique_together = [['business', 'supplier', 'invoice_number']]
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['supplier', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]

    def __str__(self):
        return f"{self.invoice_number} ({self.supplier.name}) - KES {self.amount:,.2f}"

    def total_paid(self):
        """Sum of payment allocations made to this invoice"""
        return self.payment_allocations.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

    def total_credited(self):
        """Sum of supplier credit note applications applied to this invoice"""
        return self.credit_applications.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')

    def remaining_balance(self):
        """Returns unpaid remaining balance taking both payments and credits into account"""
        rem = self.amount - self.total_paid() - self.total_credited()
        return max(Decimal('0.00'), rem)

    def is_overdue(self):
        """Check if invoice is past due date with an outstanding balance"""
        if self.status in ('paid', 'cancelled'):
            return False
        return self.due_date < timezone.now().date() and self.remaining_balance() > Decimal('0.00')

    def days_overdue(self):
        """Calculate overdue days"""
        if not self.is_overdue():
            return 0
        return (timezone.now().date() - self.due_date).days

    def recalculate_status(self):
        """Updates status based on remaining balance"""
        if self.status in ('cancelled', 'disputed'):
            return self.status
        rem = self.remaining_balance()
        if rem <= Decimal('0.00'):
            self.status = 'paid'
        elif self.total_paid() > Decimal('0.00') or self.total_credited() > Decimal('0.00'):
            self.status = 'partially_paid'
        else:
            self.status = 'unpaid'
        self.save(update_fields=['status', 'updated_at'])
        return self.status


# ==================== SUPPLIER PAYMENTS ====================

class SupplierPayment(models.Model):
    """Records outgoing disbursements and payments made to suppliers"""
    SOURCE_TYPE_CHOICES = [
        ('bank_account', 'Bank Account / Transfer'),
        ('cash_drawer', 'Cash Drawer (Till)'),
        ('petty_cash', 'Petty Cash Fund'),
        ('direct', 'Direct / Other'),
    ]

    PAYMENT_METHOD_TYPE_CHOICES = [
        ('bank_transfer', 'Bank Transfer / EFT'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Approval / Transit'),
        ('sent', 'Sent / Outstanding'),
        ('cleared', 'Cleared on Bank Statement'),
        ('reversed', 'Reversed'),
    ]

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='supplier_payments')
    payment_number = models.CharField(max_length=30, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='payments')
    payment_date = models.DateField(default=timezone.now, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    
    payment_method_type = models.CharField(max_length=20, choices=PAYMENT_METHOD_TYPE_CHOICES, default='bank_transfer')
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default='bank_account')
    
    bank_account = models.ForeignKey('BankAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_payments')
    cash_paid_out = models.ForeignKey('CashPaidOut', on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_payments')
    reference_number = models.CharField(max_length=100, blank=True, help_text="EFT reference, Cheque #, Mobile Money Tx ID")
    
    bank_statement_line = models.ForeignKey('BankStatementLine', on_delete=models.SET_NULL, null=True, blank=True, related_name='matched_payments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent', db_index=True)
    authorized_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_payments_authorized')
    
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reversal_reason = models.TextField(blank=True)
    
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='supplier_payments_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date', '-created_at']
        unique_together = [['business', 'payment_number']]
        indexes = [
            models.Index(fields=['supplier', 'payment_date']),
            models.Index(fields=['business', 'status']),
            models.Index(fields=['payment_date']),
        ]
    
    def __str__(self):
        return f"{self.payment_number} - {self.supplier.name} - KES {self.amount:,.2f}"
    
    def save(self, *args, **kwargs):
        # Auto-populate business from supplier
        if not self.business_id and self.supplier:
            self.business = self.supplier.business
        
        # Generate payment number: PAY-YYYYMMDD-XXXX
        if not self.payment_number:
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_payment = SupplierPayment.objects.filter(
                business=self.business,
                payment_number__startswith=f'PAY-{date_str}'
            ).order_by('-payment_number').first()
            if last_payment:
                last_num = int(last_payment.payment_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.payment_number = f'PAY-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)
    
    def total_allocated(self):
        """Returns the total amount allocated to invoices and purchases"""
        return self.allocations.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def unallocated_amount(self):
        """Returns the amount not yet allocated to specific bills"""
        return max(Decimal('0.00'), self.amount - self.total_allocated())


class PaymentAllocation(models.Model):
    """Tracks allocation of payments to specific supplier invoices or legacy purchases"""
    payment = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE, related_name='allocations')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_allocations')
    purchase = models.ForeignKey(Purchase, on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_allocations')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['payment']),
            models.Index(fields=['invoice']),
            models.Index(fields=['purchase']),
        ]
    
    def __str__(self):
        target = self.invoice.invoice_number if self.invoice else (self.purchase.purchase_number if self.purchase else "Unlinked")
        return f"{self.payment.payment_number} -> {target}: KES {self.amount:,.2f}"


# ==================== SUPPLIER CREDITS / DEBIT NOTES ====================

class SupplierCredit(models.Model):
    """
    Claims raised against a supplier (e.g. goods returns, damaged goods, overcharges, rebates).
    Can be resolved by offsetting against future invoices or receiving a cash/bank refund.
    """
    STATUS_CHOICES = [
        ('pending_approval', 'Pending Approval'),
        ('approved_by_supplier', 'Approved by Supplier'),
        ('applied_to_invoice', 'Applied to Invoice'),
        ('refunded', 'Refunded by Supplier'),
        ('partially_resolved', 'Partially Resolved'),
        ('rejected', 'Rejected'),
    ]

    REASON_CHOICES = [
        ('return', 'Goods Returned'),
        ('damaged_goods', 'Damaged Goods on Delivery'),
        ('overcharge', 'Invoice Overcharge'),
        ('discount', 'Discount / Price Rebate'),
        ('other', 'Other Claim Reason'),
    ]

    RESOLUTION_CHOICES = [
        ('offset_invoice', 'Offset Future Invoice'),
        ('cash_refund', 'Cash Refund'),
        ('bank_refund', 'Bank Refund'),
        ('mixed', 'Mixed Offset & Refund'),
        ('unresolved', 'Unresolved'),
    ]

    credit_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='supplier_credits')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='credits')
    
    related_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_notes')
    related_purchase = models.ForeignKey(Purchase, on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_credits')
    related_grn = models.ForeignKey('GoodsReturnedNote', on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_credits')
    
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    reason = models.CharField(max_length=30, choices=REASON_CHOICES, default='return')
    date_raised = models.DateField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending_approval', db_index=True)
    resolution_type = models.CharField(max_length=30, choices=RESOLUTION_CHOICES, default='unresolved')
    resolution_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_credits')
    
    notes = models.TextField(blank=True)
    attachment = models.FileField(upload_to='supplier_credits/%Y/%m/', null=True, blank=True)
    authorized_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_credits_authorized')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='supplier_credits_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_raised', '-created_at']
        unique_together = [['business', 'credit_number']]
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['supplier', 'status']),
        ]

    def __str__(self):
        return f"{self.credit_number} ({self.supplier.name}) - KES {self.amount:,.2f}"

    def save(self, *args, **kwargs):
        if not self.credit_number:
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_credit = SupplierCredit.objects.filter(
                business=self.business,
                credit_number__startswith=f'SCR-{date_str}'
            ).order_by('-credit_number').first()
            if last_credit:
                last_num = int(last_credit.credit_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.credit_number = f'SCR-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)

    def remaining_credit(self):
        """Unused credit balance remaining for future invoices or refunds"""
        return max(Decimal('0.00'), self.amount - self.allocated_amount)

    def is_fully_resolved(self):
        return self.remaining_credit() <= Decimal('0.00')

    def recalculate_resolution(self):
        """Recalculates allocated amount and updates status"""
        applied_total = self.applications.aggregate(t=models.Sum('amount'))['t'] or Decimal('0.00')
        refunded_total = self.refunds.aggregate(t=models.Sum('amount'))['t'] or Decimal('0.00')
        self.allocated_amount = applied_total + refunded_total
        
        if self.allocated_amount >= self.amount:
            if applied_total > 0 and refunded_total > 0:
                self.resolution_type = 'mixed'
                self.status = 'applied_to_invoice'
            elif refunded_total > 0:
                self.resolution_type = 'bank_refund' if self.refunds.filter(received_via='bank_transfer').exists() else 'cash_refund'
                self.status = 'refunded'
            else:
                self.resolution_type = 'offset_invoice'
                self.status = 'applied_to_invoice'
        elif self.allocated_amount > Decimal('0.00'):
            self.status = 'partially_resolved'
        
        self.save(update_fields=['allocated_amount', 'resolution_type', 'status', 'updated_at'])


class SupplierCreditApplication(models.Model):
    """Junction applying a supplier credit to reduce/offset a specific supplier invoice"""
    credit = models.ForeignKey(SupplierCredit, on_delete=models.CASCADE, related_name='applications')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.CASCADE, related_name='credit_applications')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    applied_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')
    applied_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['applied_at']
        indexes = [
            models.Index(fields=['credit']),
            models.Index(fields=['invoice']),
        ]

    def __str__(self):
        return f"{self.credit.credit_number} applied to {self.invoice.invoice_number}: KES {self.amount:,.2f}"


class SupplierRefund(models.Model):
    """
    Incoming funds returned by a supplier to settle a supplier credit.
    Reconciled against bank statement credits or cash register counts.
    """
    VIA_CHOICES = [
        ('bank_transfer', 'Bank Transfer / EFT'),
        ('cash', 'Cash (Drawer / Safe)'),
        ('mobile_money', 'Mobile Money'),
    ]

    DEST_CHOICES = [
        ('bank_account', 'Bank Account'),
        ('cash_drawer', 'Till Cash Drawer'),
        ('petty_cash', 'Petty Cash Fund'),
    ]

    refund_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='supplier_refunds')
    supplier_credit = models.ForeignKey(SupplierCredit, on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    received_date = models.DateField(default=timezone.now, db_index=True)
    
    received_via = models.CharField(max_length=20, choices=VIA_CHOICES, default='bank_transfer')
    destination_account = models.ForeignKey('BankAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_refunds')
    destination_type = models.CharField(max_length=20, choices=DEST_CHOICES, default='bank_account')
    reference = models.CharField(max_length=100, blank=True)
    
    bank_statement_line = models.ForeignKey('BankStatementLine', on_delete=models.SET_NULL, null=True, blank=True, related_name='matched_refunds')
    status = models.CharField(max_length=20, choices=[('pending', 'Pending Statement Match'), ('matched', 'Matched & Reconciled')], default='pending', db_index=True)
    
    received_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='supplier_refunds_received')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-received_date', '-created_at']
        unique_together = [['business', 'refund_number']]
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['received_date']),
        ]

    def __str__(self):
        return f"{self.refund_number} ({self.supplier_credit.supplier.name}) - KES {self.amount:,.2f}"

    def save(self, *args, **kwargs):
        if not self.refund_number:
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_ref = SupplierRefund.objects.filter(
                business=self.business,
                refund_number__startswith=f'SRF-{date_str}'
            ).order_by('-refund_number').first()
            if last_ref:
                last_num = int(last_ref.refund_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.refund_number = f'SRF-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)



# ==================== USER PROFILE ====================

class UserProfile(models.Model):
    """Extended user profile with additional information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    employee_id = models.CharField(max_length=50, unique=True, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    hire_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text="Additional notes about the user")
    pin_hash = models.CharField(max_length=128, blank=True, null=True, help_text="Hashed PIN for POS quick login")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - Profile"
    
    def get_role_display(self):
        """Get user's primary role"""
        if self.user.is_superuser:
            return "Administrator"
        groups = self.user.groups.all()
        if groups:
            return groups[0].name
        return "No Role"

    @property
    def has_pin_set(self):
        """Returns True if a PIN has been set for this user."""
        return bool(self.pin_hash)

    def set_pin(self, raw_pin, business=None):
        """
        Validate, ensure uniqueness, and hash a 4-6 digit PIN.
        Raises ValidationError if the PIN is invalid or already in use by another cashier.
        """
        import re
        from django.core.exceptions import ValidationError
        from django.contrib.auth.hashers import make_password, check_password

        raw_str = str(raw_pin or '').strip()
        if not re.fullmatch(r'\d{4,6}', raw_str):
            raise ValidationError('PIN must be 4 to 6 digits (numbers only).')

        other_profiles = UserProfile.objects.filter(
            user__is_active=True
        ).exclude(pk=self.pk).exclude(pin_hash__isnull=True).exclude(pin_hash='').select_related('user')

        for other in other_profiles:
            if other.check_pin(raw_str):
                other_name = other.user.get_full_name() or other.user.username
                raise ValidationError(
                    f'This PIN is already assigned to {other_name}. '
                    'Each cashier must have a unique PIN.'
                )

        self.pin_hash = make_password(raw_str)
        self.save(update_fields=['pin_hash'])

    def check_pin(self, raw_pin):
        """Returns True if raw_pin matches the stored hash."""
        if not self.pin_hash or not raw_pin:
            return False
        from django.contrib.auth.hashers import check_password
        return check_password(str(raw_pin).strip(), self.pin_hash)

    def clear_pin(self):
        """Remove the stored PIN hash."""
        self.pin_hash = None
        self.save(update_fields=['pin_hash'])

    @classmethod
    def find_by_pin(cls, raw_pin, business=None):
        """
        Find the unique active UserProfile matching raw_pin within the business/store.
        Returns the UserProfile instance if a match is found, otherwise None.
        """
        raw_str = str(raw_pin or '').strip()
        if not raw_str or not (4 <= len(raw_str) <= 6) or not raw_str.isdigit():
            return None

        # Fetch active profiles that have a PIN configured
        profiles = list(cls.objects.filter(
            user__is_active=True
        ).exclude(pin_hash__isnull=True).exclude(pin_hash='').select_related('user'))

        # If business provided, check matching business profiles first
        if business:
            for p in profiles:
                has_biz_membership = p.user.business_memberships.filter(business=business, is_active=True).exists()
                if has_biz_membership and p.check_pin(raw_str):
                    return p

        # Fallback to any active profile matching the PIN
        for p in profiles:
            if p.check_pin(raw_str):
                return p

        return None


# ==================== BUSINESS SETTINGS ====================

class BusinessSettings(CacheInvalidationMixin, models.Model):
    """Per-business settings - each business has its own settings"""
    
    # Link to business (OneToOne)
    business = models.OneToOneField('Business', on_delete=models.CASCADE, related_name='settings')
    
    # Business Information (can override Business model fields)
    business_name = models.CharField(max_length=200, blank=True, help_text="Override business name for receipts")
    business_address = models.TextField(blank=True)
    business_phone = models.CharField(max_length=20, blank=True)
    business_email = models.EmailField(blank=True)
    business_website = models.URLField(blank=True)
    tax_id = models.CharField(max_length=50, blank=True, help_text="Tax/VAT registration number")
    
    # Logo
    logo = models.ImageField(
        upload_to='business/logos/',
        blank=True,
        null=True,
        help_text="Company logo (will be automatically optimized)"
    )
    
    # Tax Settings
    vat_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=16,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="VAT/Tax rate in percentage"
    )
    vat_enabled = models.BooleanField(default=True, help_text="Enable VAT calculation")
    
    # Receipt Settings
    receipt_header = models.TextField(blank=True, help_text="Custom header text for receipts")
    receipt_footer = models.TextField(blank=True, help_text="Custom footer text for receipts")
    show_logo_on_receipt = models.BooleanField(default=False)
    
    # Thermal Receipt Settings
    thermal_receipt_width = models.IntegerField(
        default=80,
        choices=[(58, '58mm'), (80, '80mm')],
        help_text="Thermal printer paper width"
    )
    thermal_font_size = models.CharField(
        max_length=10,
        choices=[('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')],
        default='medium',
        help_text="Font size for thermal receipts"
    )
    thermal_print_logo = models.BooleanField(default=True, help_text="Print logo on thermal receipts")
    thermal_print_barcode = models.BooleanField(default=True, help_text="Print barcode on thermal receipts")
    thermal_auto_cut = models.BooleanField(default=True, help_text="Auto-cut paper after printing")
    thermal_copies = models.IntegerField(default=1, help_text="Number of receipt copies to print")
    thermal_show_tax_breakdown = models.BooleanField(default=True, help_text="Show VAT breakdown on receipt")
    
    # Currency Settings
    currency_symbol = models.CharField(max_length=10, default="KES")
    currency_position = models.CharField(
        max_length=10,
        choices=[('before', 'Before Amount'), ('after', 'After Amount')],
        default='before'
    )
    
    # Low Stock Settings
    default_low_stock_threshold = models.IntegerField(default=10)
    enable_low_stock_alerts = models.BooleanField(default=True)
    
    # Expiry Settings
    default_expiry_alert_days = models.IntegerField(default=7)
    enable_expiry_alerts = models.BooleanField(default=True)
    
    # Loyalty Program Settings
    loyalty_enabled = models.BooleanField(default=True, help_text="Enable loyalty program")
    
    # Points Earning Rules
    loyalty_points_per_currency = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100,
        help_text="Amount spent to earn 1 point (e.g., KES 100 = 1 point)"
    )
    
    # Tier-specific earning rates (multipliers)
    loyalty_regular_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.0,
        help_text="Points multiplier for Regular customers (1.0 = normal rate)"
    )
    loyalty_silver_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=1.5,
        help_text="Points multiplier for Silver customers (1.5 = 50% bonus)"
    )
    loyalty_gold_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.0,
        help_text="Points multiplier for Gold customers (2.0 = double points)"
    )
    loyalty_platinum_multiplier = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=3.0,
        help_text="Points multiplier for Platinum customers (3.0 = triple points)"
    )
    
    # Points Redemption
    loyalty_points_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        help_text="Value of 1 point in currency (e.g., 1 point = KES 1)"
    )
    loyalty_min_points_redeem = models.IntegerField(
        default=100,
        help_text="Minimum points required to redeem"
    )
    loyalty_max_redeem_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Maximum percentage of sale that can be paid with points"
    )
    
    # Points Expiry
    loyalty_points_expire = models.BooleanField(
        default=False,
        help_text="Enable points expiry"
    )
    loyalty_points_expiry_months = models.IntegerField(
        default=12,
        help_text="Months until points expire (if expiry enabled)"
    )
    
    # Tier Thresholds (lifetime spending)
    loyalty_silver_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=10000,
        help_text="Lifetime spending to reach Silver tier"
    )
    loyalty_gold_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=50000,
        help_text="Lifetime spending to reach Gold tier"
    )
    loyalty_platinum_threshold = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100000,
        help_text="Lifetime spending to reach Platinum tier"
    )
    
    # System Settings
    allow_negative_stock = models.BooleanField(default=False, help_text="Allow sales when stock is 0")
    require_product_code = models.BooleanField(default=False, help_text="Make product code mandatory")
    auto_generate_product_code = models.BooleanField(default=False)

    # Attendance / Working Hours Settings
    workday_start_time = models.TimeField(
        default=time(8, 0),
        help_text="Official workday start time used to determine lateness"
    )
    workday_end_time = models.TimeField(
        default=time(17, 0),
        help_text="Official workday end time used to determine overtime"
    )
    late_grace_minutes = models.PositiveIntegerField(
        default=15,
        validators=[MinValueValidator(0), MaxValueValidator(180)],
        help_text="Grace period in minutes after start time before marking late"
    )
    overtime_rate_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal('1.50'),
        validators=[MinValueValidator(Decimal('1.00')), MaxValueValidator(Decimal('5.00'))],
        help_text="Overtime pay rate multiplier against hourly rate (e.g. 1.5 = time-and-a-half)"
    )
    
    # Theme Customization
    theme_primary = models.CharField(
        max_length=7,
        default='#224195',
        help_text="Primary brand color (hex code, e.g., #224195)"
    )
    theme_dark = models.CharField(
        max_length=7,
        default='#1a1514',
        help_text="Dark color for sidebar/headers (hex code, e.g., #1a1514)"
    )
    theme_light = models.CharField(
        max_length=7,
        default='#d5d3d4',
        help_text="Light color for text/backgrounds (hex code, e.g., #d5d3d4)"
    )
    theme_accent = models.CharField(
        max_length=7,
        default='#cd8a4c',
        help_text="Accent color for highlights (hex code, e.g., #cd8a4c)"
    )

    # ── M-Pesa Configuration ──────────────────────────────────────────────
    mpesa_enabled = models.BooleanField(
        default=False,
        help_text="Show M-Pesa payment details on POS and receipts"
    )
    mpesa_type = models.CharField(
        max_length=10,
        choices=[('paybill', 'Paybill'), ('till', 'Buy Goods (Till)'), ('phone', 'Phone Number (Send Money)')],
        default='paybill',
        help_text="Type of M-Pesa number"
    )
    mpesa_shortcode = models.CharField(
        max_length=20,
        blank=True,
        help_text="Paybill number or Till number"
    )
    mpesa_phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="M-Pesa phone number for Send Money (e.g. 0712345678)"
    )
    mpesa_account_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Account name shown to customers (for Paybill)"
    )
    mpesa_account_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Default account reference / prompt shown to cashier (e.g. invoice number)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "Business Settings"
        verbose_name_plural = "Business Settings"
    
    def __str__(self):
        return f"Settings for {self.business.name}"
    
    def save(self, *args, **kwargs):
        # Optimize logo on upload
        if self.logo and hasattr(self.logo, 'file'):
            is_valid, error = ImageOptimizer.validate_image(self.logo)
            if not is_valid:
                raise ValueError(error)
            self.logo = ImageOptimizer.optimize_image(self.logo, max_size=(500, 500))
        
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls, business):
        """Get or create settings for a business"""
        settings, created = cls.objects.get_or_create(
            business=business,
            defaults={
                'business_name': business.name,
                'business_address': business.address,
                'business_phone': business.phone,
                'business_email': business.email,
            }
        )
        return settings
    
    def get_business_name(self):
        """Get business name (use override if set, otherwise use business.name)"""
        return self.business_name or (self.business.name if self.business_id else '')

    @property
    def name(self):
        return self.get_business_name()

    @property
    def address(self):
        return self.business_address or (self.business.address if self.business_id else '')

    @property
    def phone(self):
        return self.business_phone or (self.business.phone if self.business_id else '')

    @property
    def email(self):
        return self.business_email or (self.business.email if self.business_id else '')

    @property
    def website(self):
        return self.business_website or (self.business.website if self.business_id else '')
    
    def format_currency(self, amount):
        """Format amount with currency symbol"""
        formatted_amount = f"{amount:,.2f}"
        if self.currency_position == 'before':
            return f"{self.currency_symbol} {formatted_amount}"
        else:
            return f"{formatted_amount} {self.currency_symbol}"
    
    # Loyalty Program Helper Methods
    def calculate_points_earned(self, amount_spent, customer_tier='regular'):
        """
        Calculate loyalty points earned for a purchase
        
        Args:
            amount_spent: Amount spent in currency
            customer_tier: Customer tier (regular, silver, gold, platinum)
        
        Returns:
            Number of points earned (integer)
        """
        if not self.loyalty_enabled or amount_spent <= 0:
            return 0
        
        # Get tier multiplier
        multipliers = {
            'regular': self.loyalty_regular_multiplier,
            'silver': self.loyalty_silver_multiplier,
            'gold': self.loyalty_gold_multiplier,
            'platinum': self.loyalty_platinum_multiplier,
        }
        multiplier = multipliers.get(customer_tier, Decimal('1.0'))
        
        # Calculate base points
        base_points = amount_spent / self.loyalty_points_per_currency
        
        # Apply tier multiplier
        total_points = base_points * multiplier
        
        # Return as integer
        return int(total_points)
    
    def calculate_points_value(self, points):
        """
        Calculate currency value of loyalty points
        
        Args:
            points: Number of points
        
        Returns:
            Currency value of points
        """
        return Decimal(points) * self.loyalty_points_value
    
    def can_redeem_points(self, points, sale_total):
        """
        Check if points can be redeemed for a sale
        
        Args:
            points: Number of points to redeem
            sale_total: Total sale amount
        
        Returns:
            (can_redeem: bool, reason: str)
        """
        if not self.loyalty_enabled:
            return False, "Loyalty program is disabled"
        
        if points < self.loyalty_min_points_redeem:
            return False, f"Minimum {self.loyalty_min_points_redeem} points required"
        
        # Calculate maximum redeemable amount
        max_redeem_amount = (sale_total * self.loyalty_max_redeem_percentage) / 100
        points_value = self.calculate_points_value(points)
        
        if points_value > max_redeem_amount:
            return False, f"Can only redeem up to {self.loyalty_max_redeem_percentage}% of sale total"
        
        return True, "OK"
    
    def get_tier_for_spending(self, lifetime_spending):
        """
        Determine customer tier based on lifetime spending
        
        Args:
            lifetime_spending: Total lifetime spending amount
        
        Returns:
            Tier name (regular, silver, gold, platinum)
        """
        if lifetime_spending >= self.loyalty_platinum_threshold:
            return 'platinum'
        elif lifetime_spending >= self.loyalty_gold_threshold:
            return 'gold'
        elif lifetime_spending >= self.loyalty_silver_threshold:
            return 'silver'
        else:
            return 'regular'
    
    def get_loyalty_summary(self):
        """Get a summary of loyalty program settings"""
        return {
            'enabled': self.loyalty_enabled,
            'earning_rate': f"{self.currency_symbol} {self.loyalty_points_per_currency} = 1 point",
            'tier_multipliers': {
                'regular': f"{self.loyalty_regular_multiplier}x",
                'silver': f"{self.loyalty_silver_multiplier}x",
                'gold': f"{self.loyalty_gold_multiplier}x",
                'platinum': f"{self.loyalty_platinum_multiplier}x",
            },
            'point_value': f"1 point = {self.format_currency(self.loyalty_points_value)}",
            'min_redeem': f"{self.loyalty_min_points_redeem} points",
            'max_redeem': f"{self.loyalty_max_redeem_percentage}% of sale",
            'expiry': f"{self.loyalty_points_expiry_months} months" if self.loyalty_points_expire else "No expiry",
            'tier_thresholds': {
                'silver': self.format_currency(self.loyalty_silver_threshold),
                'gold': self.format_currency(self.loyalty_gold_threshold),
                'platinum': self.format_currency(self.loyalty_platinum_threshold),
            }
        }

    # Theme Customization
    theme_primary = models.CharField(
        max_length=7,
        default='#224195',
        help_text="Primary brand color (hex code, e.g., #224195)"
    )
    theme_dark = models.CharField(
        max_length=7,
        default='#1a1514',
        help_text="Dark color for sidebar/headers (hex code, e.g., #1a1514)"
    )
    theme_light = models.CharField(
        max_length=7,
        default='#d5d3d4',
        help_text="Light color for text/backgrounds (hex code, e.g., #d5d3d4)"
    )
    theme_accent = models.CharField(
        max_length=7,
        default='#cd8a4c',
        help_text="Accent color for highlights (hex code, e.g., #cd8a4c)"
    )




# ==================== ACTIVITY LOG ====================

class ActivityLog(models.Model):
    """Track user activities in the system"""
    ACTION_TYPES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('sale', 'Sale'),
        ('refund', 'Refund'),
        ('stock_adjust', 'Stock Adjustment'),
        ('purchase', 'Purchase'),
        ('settings', 'Settings Change'),
        ('backup', 'Data Backup'),
        ('restore', 'Data Restore'),
        ('export', 'Export'),
        ('password_change', 'Password Change'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('rollback', 'Rollback')
    ]
    
    # Core fields
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    business = models.ForeignKey('Business', on_delete=models.CASCADE, null=True, blank=True, related_name='activity_logs')
    branch = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='activity_logs')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    
    # Enhanced tracking fields
    operation_type = models.CharField(max_length=50, db_index=True)
    entity_type = models.CharField(max_length=100, db_index=True, default='')
    entity_id = models.CharField(max_length=100, db_index=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success', db_index=True)
    
    # Legacy fields (kept for backward compatibility)
    model_name = models.CharField(max_length=50, blank=True)
    object_id = models.IntegerField(blank=True, null=True)
    description = models.TextField()
    
    # Request tracking
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, default='')
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    
    # Data fields
    request_data = models.JSONField(null=True, blank=True)
    response_data = models.JSONField(null=True, blank=True)
    error_details = models.JSONField(null=True, blank=True)
    
    # Performance tracking
    execution_time_ms = models.IntegerField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['business', 'timestamp'], name='pos_actlog_bus_time_idx'),
            models.Index(fields=['business', 'operation_type', 'timestamp'], name='pos_actlog_bus_op_tm_idx'),
            models.Index(fields=['business', 'entity_type', 'entity_id'], name='pos_actlog_bus_ent_idx'),
            models.Index(fields=['business', 'user', 'timestamp'], name='pos_actlog_bus_usr_tm_idx'),
            models.Index(fields=['correlation_id'], name='pos_actlog_corr_idx'),
        ]
    
    def __str__(self):
        username = self.user.username if self.user else "Unknown"
        return f"{username} - {self.action_type} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def log_activity(cls, user, action_type, description, model_name='', object_id=None, request=None, 
                     business=None, operation_type=None, entity_type='', entity_id='', status='success',
                     request_data=None, response_data=None, error_details=None, execution_time_ms=None):
        """Helper method to create activity log"""
        ip_address = None
        user_agent = ''
        
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')
            
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Try to get business from request if not provided
            if not business and hasattr(request, 'business'):
                business = request.business
        
        # Use action_type as operation_type if not provided
        if not operation_type:
            operation_type = action_type
        
        return cls.objects.create(
            user=user,
            business=business,
            action_type=action_type,
            operation_type=operation_type,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            model_name=model_name,
            object_id=object_id,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            request_data=request_data,
            response_data=response_data,
            error_details=error_details,
            execution_time_ms=execution_time_ms
        )


# ==================== PASSWORD HISTORY ====================

class PasswordHistory(models.Model):
    """Track previous password hashes to prevent reuse"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @classmethod
    def record(cls, user, raw_password):
        """Save current password hash before it changes"""
        from django.contrib.auth.hashers import make_password
        cls.objects.create(user=user, password_hash=make_password(raw_password))
        # Keep only last 10 entries
        old_ids = cls.objects.filter(user=user).order_by('-created_at').values_list('id', flat=True)[10:]
        cls.objects.filter(id__in=list(old_ids)).delete()


# ==================== GOODS RECEIVED NOTE ====================

class GoodsReceivedNote(models.Model):
    """Formal document generated when goods are received from a supplier"""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('discrepancy', 'Discrepancy Noted'),
    ]

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='goods_received_notes')
    grn_number = models.CharField(max_length=20, editable=False)
    purchase = models.OneToOneField('Purchase', on_delete=models.PROTECT, related_name='goods_received_note')
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT, related_name='goods_received_notes')

    received_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')

    # Delivery reference
    delivery_note_number = models.CharField(max_length=100, blank=True, help_text='Supplier delivery note / waybill number')
    vehicle_number = models.CharField(max_length=50, blank=True)
    driver_name = models.CharField(max_length=100, blank=True)

    # Totals (denormalised for fast reporting)
    total_ordered_qty = models.PositiveIntegerField(default=0)
    total_received_qty = models.PositiveIntegerField(default=0)
    total_damaged_qty = models.PositiveIntegerField(default=0)
    total_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    notes = models.TextField(blank=True)

    received_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='goods_received_notes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-received_date', '-created_at']
        unique_together = [['business', 'grn_number']]
        verbose_name = 'Goods Received Note'
        verbose_name_plural = 'Goods Received Notes'

    def __str__(self):
        return f"{self.grn_number} — {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.grn_number:
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last = GoodsReceivedNote.objects.filter(
                business=self.business,
                grn_number__startswith=f'GRNR-{date_str}'
            ).order_by('-grn_number').first()
            new_num = (int(last.grn_number.split('-')[-1]) + 1) if last else 1
            self.grn_number = f'GRNR-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)

    @property
    def has_discrepancy(self):
        return self.total_damaged_qty > 0 or self.total_received_qty < self.total_ordered_qty


class GoodsReceivedNoteItem(models.Model):
    """Line items on a Goods Received Note"""

    grn = models.ForeignKey(GoodsReceivedNote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.PROTECT)
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField()
    quantity_damaged = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.product.name} — {self.quantity_received}/{self.quantity_ordered}"

    def save(self, *args, **kwargs):
        self.total_cost = Decimal(self.quantity_received) * self.unit_cost
        super().save(*args, **kwargs)

    @property
    def has_discrepancy(self):
        return self.quantity_damaged > 0 or self.quantity_received < self.quantity_ordered

    @property
    def quantity_missing(self):
        return max(0, self.quantity_ordered - self.quantity_received - self.quantity_damaged)


# ==================== GOODS RETURNED NOTE (GRN) ====================

class GoodsReturnedNote(models.Model):
    """Formal document for returning goods to supplier"""
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted to Supplier'),
        ('acknowledged', 'Acknowledged by Supplier'),
        ('collected', 'Goods Collected'),
        ('credited', 'Credit Note Received'),
        ('replaced', 'Replacement Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    RETURN_REASON_CHOICES = [
        ('damaged', 'Damaged on Delivery'),
        ('wrong_item', 'Wrong Item Delivered'),
        ('expired', 'Expired Product'),
        ('quality', 'Quality Issue'),
        ('overstock', 'Overstock Return'),
        ('recall', 'Product Recall'),
        ('other', 'Other'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='goods_returned_notes')
    grn_number = models.CharField(max_length=20, editable=False)
    supplier = models.ForeignKey('Supplier', on_delete=models.PROTECT, related_name='goods_returned_notes')
    related_purchase = models.ForeignKey('Purchase', null=True, blank=True, on_delete=models.SET_NULL, related_name='goods_returned_notes')
    
    return_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    return_reason = models.CharField(max_length=20, choices=RETURN_REASON_CHOICES)
    reason_details = models.TextField(help_text='Detailed explanation of return reason')
    
    # Financial
    total_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    credit_note_number = models.CharField(max_length=50, blank=True, help_text='Credit note number from supplier')
    credit_note_date = models.DateField(null=True, blank=True)
    credit_note_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Tracking
    collection_date = models.DateField(null=True, blank=True, help_text='Date goods were collected by supplier')
    collection_notes = models.TextField(blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='grns_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-return_date', '-created_at']
        unique_together = [['business', 'grn_number']]
        verbose_name = 'Goods Returned Note'
        verbose_name_plural = 'Goods Returned Notes'
    
    def __str__(self):
        return f"{self.grn_number} - {self.supplier.name}"
    
    def save(self, *args, **kwargs):
        if not self.grn_number:
            # Generate GRN number: GRN-YYYYMMDD-XXXX
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_grn = GoodsReturnedNote.objects.filter(
                business=self.business,
                grn_number__startswith=f'GRN-{date_str}'
            ).order_by('-grn_number').first()
            if last_grn:
                last_num = int(last_grn.grn_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.grn_number = f'GRN-{date_str}-{new_num:04d}'
        
        # Calculate total value from items
        if self.pk:
            self.total_value = self.items.aggregate(
                total=models.Sum('total_cost')
            )['total'] or Decimal('0.00')
        
        super().save(*args, **kwargs)
    
    def submit_to_supplier(self):
        """Mark GRN as submitted to supplier"""
        if self.status == 'draft':
            self.status = 'submitted'
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False
    
    def mark_collected(self, collection_date=None, notes=''):
        """Mark goods as collected by supplier"""
        if self.status not in ('submitted', 'acknowledged'):
            return False
        self.status = 'collected'
        self.collection_date = collection_date or timezone.now().date()
        self.collection_notes = notes
        self.save(update_fields=['status', 'collection_date', 'collection_notes', 'updated_at'])
        return True
    
    def apply_credit_note(self, credit_note_number, amount, date=None):
        """Record credit note received from supplier"""
        if self.status not in ('submitted', 'acknowledged', 'collected'):
            return False

        amount = Decimal(amount)
        if amount <= 0:
            return False
        if self.total_value and amount > self.total_value:
            return False

        self.status = 'credited'
        self.credit_note_number = credit_note_number
        self.credit_note_amount = amount
        self.credit_note_date = date or timezone.now().date()
        self.save(update_fields=[
            'status',
            'credit_note_number',
            'credit_note_amount',
            'credit_note_date',
            'updated_at',
        ])
        return True
    
    def cancel(self):
        """Cancel the GRN"""
        if self.status in ['draft', 'submitted', 'acknowledged']:
            self.status = 'cancelled'
            self.save(update_fields=['status', 'updated_at'])
            return True
        return False


class GoodsReturnedNoteItem(models.Model):
    """Individual items in a GRN"""
    
    grn = models.ForeignKey(GoodsReturnedNote, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('Product', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Traceability
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
    # Reason specific to this item
    item_notes = models.TextField(blank=True, help_text='Specific notes about this item')
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        self.total_cost = Decimal(self.quantity) * self.unit_cost
        super().save(*args, **kwargs)
        
        # Update GRN total
        if self.grn_id:
            self.grn.save()


# ==================== CUSTOMER MANAGEMENT ====================

class Customer(AuditModelMixin, models.Model):
    """Customer information and loyalty tracking"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='customers')
    customer_code = models.CharField(max_length=20, editable=False)
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    
    # Loyalty Program
    loyalty_points = models.IntegerField(default=0, help_text="Current available loyalty points")
    lifetime_points = models.IntegerField(default=0, help_text="Total points earned all time")
    total_purchases = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    visit_count = models.IntegerField(default=0)
    
    # Customer Tier (based on lifetime points)
    TIER_CHOICES = [
        ('bronze', 'Bronze'),
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'),
    ]
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='bronze')
    
    # Customer Type
    CUSTOMER_TYPES = [
        ('regular', 'Regular'),
        ('vip', 'VIP'),
        ('wholesale', 'Wholesale'),
    ]
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPES, default='regular')
    
    # Status
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")

    # Credit Management
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Maximum credit allowed")
    credit_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Current outstanding credit balance")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = [['business', 'customer_code']]
    
    def __str__(self):
        return f"{self.name} ({self.customer_code})"

    @staticmethod
    def normalize_phone(phone):
        """Normalize customer phone numbers for duplicate detection and storage."""
        raw_phone = (phone or '').strip()
        if not raw_phone:
            return ''

        digits = re.sub(r'\D', '', raw_phone)
        if not digits:
            return raw_phone

        if digits.startswith('254') and len(digits) == 12:
            return f"0{digits[3:]}"
        if len(digits) == 9 and digits[0] in ('7', '1'):
            return f"0{digits}"
        return digits

    @property
    def normalized_phone(self):
        return self.normalize_phone(self.phone)

    @classmethod
    def find_duplicate_by_phone(cls, business, phone, exclude_pk=None):
        normalized_phone = cls.normalize_phone(phone)
        if not normalized_phone:
            return None

        candidates = cls.objects.filter(business=business)
        if exclude_pk is not None:
            candidates = candidates.exclude(pk=exclude_pk)

        for candidate in candidates.order_by('name'):
            if candidate.normalized_phone == normalized_phone:
                return candidate
        return None

    @classmethod
    def get_same_phone_customers(cls, business, phone, exclude_pk=None, is_active=None):
        normalized_phone = cls.normalize_phone(phone)
        if not normalized_phone:
            return []

        candidates = cls.objects.filter(business=business)
        if exclude_pk is not None:
            candidates = candidates.exclude(pk=exclude_pk)
        if is_active is not None:
            candidates = candidates.filter(is_active=is_active)

        return [candidate for candidate in candidates.order_by('name') if candidate.normalized_phone == normalized_phone]
    
    def save(self, *args, **kwargs):
        self.name = (self.name or '').strip()
        self.email = (self.email or '').strip()
        self.phone = self.normalize_phone(self.phone)
        if not self.customer_code:
            # Generate customer code: CUST-XXXXXX
            last_customer = Customer.objects.filter(business=self.business).order_by('-id').first()
            if last_customer and last_customer.customer_code:
                last_num = int(last_customer.customer_code.split('-')[1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.customer_code = f'CUST-{new_num:06d}'
        
        # Update tier based on lifetime points
        self.tier = self.calculate_tier()
        
        super().save(*args, **kwargs)
    
    def calculate_tier(self):
        """Calculate customer tier based on lifetime points"""
        if self.lifetime_points >= 10000:  # 1,000,000 KES spent
            return 'platinum'
        elif self.lifetime_points >= 5000:  # 500,000 KES spent
            return 'gold'
        elif self.lifetime_points >= 2000:  # 200,000 KES spent
            return 'silver'
        else:
            return 'bronze'
    
    def get_tier_multiplier(self):
        """Get points multiplier based on tier"""
        multipliers = {
            'bronze': 1.0,
            'silver': 1.2,
            'gold': 1.5,
            'platinum': 2.0,
        }
        return multipliers.get(self.tier, 1.0)
    
    def add_loyalty_points(self, amount, sale=None, description="Purchase"):
        """Add loyalty points based on purchase amount with tier multiplier"""
        # Base: 1 point per 100 KES spent
        base_points = int(amount / 100)
        
        # Apply tier multiplier
        multiplier = self.get_tier_multiplier()
        points = int(base_points * multiplier)
        
        if points > 0:
            self.loyalty_points += points
            self.lifetime_points += points
            self.save()
        
        # Always create transaction record, even for 0 points (for tracking)
        LoyaltyTransaction.objects.create(
            customer=self,
            transaction_type='earn',
            points=points,
            amount=amount,
            sale=sale,
            description=description
        )
        
        return points
    
    def redeem_points(self, points, sale=None, description="Points Redemption"):
        """Redeem loyalty points for discount"""
        if points <= self.loyalty_points and points > 0:
            self.loyalty_points -= points
            self.save()
            
            # Create transaction record
            LoyaltyTransaction.objects.create(
                customer=self,
                transaction_type='redeem',
                points=-points,
                amount=Decimal(points),  # 1 point = 1 KES
                sale=sale,
                description=description
            )
            
            # 1 point = 1 KES discount
            return Decimal(points)
        return Decimal(0)
    
    def get_points_value(self):
        """Get monetary value of current points (1 point = 1 KES)"""
        return Decimal(self.loyalty_points)
    
    def get_tier_display_info(self):
        """Get tier display information"""
        tier_info = {
            'bronze': {'color': '#CD7F32', 'icon': 'bi-award', 'next': 2000, 'next_tier': 'Silver'},
            'silver': {'color': '#C0C0C0', 'icon': 'bi-award-fill', 'next': 5000, 'next_tier': 'Gold'},
            'gold': {'color': '#FFD700', 'icon': 'bi-trophy', 'next': 10000, 'next_tier': 'Platinum'},
            'platinum': {'color': '#E5E4E2', 'icon': 'bi-trophy-fill', 'next': None, 'next_tier': None},
        }
        return tier_info.get(self.tier, tier_info['bronze'])

    def get_available_credit(self):
        """How much more credit the customer can use"""
        return max(Decimal('0'), self.credit_limit - self.credit_balance)

    def can_use_credit(self, amount):
        """Check if customer can make a credit purchase of given amount"""
        return self.credit_limit > 0 and self.get_available_credit() >= amount

    def get_tags_list(self):
        """Return tags as a list"""
        return [t.strip() for t in self.tags.split(',') if t.strip()] if self.tags else []


class LoyaltyTransaction(models.Model):
    """Track all loyalty point transactions"""
    TRANSACTION_TYPES = [
        ('earn', 'Points Earned'),
        ('redeem', 'Points Redeemed'),
        ('adjust', 'Manual Adjustment'),
        ('expire', 'Points Expired'),
        ('bonus', 'Bonus Points'),
    ]
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='loyalty_transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    points = models.IntegerField(help_text="Positive for earning, negative for redemption")
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Purchase amount or discount value")
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True, related_name='loyalty_transactions')
    description = models.CharField(max_length=200)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.customer.name} - {self.transaction_type} - {self.points:+d} points"


class LoyaltyReward(CacheInvalidationMixin, models.Model):
    """Rewards that customers can redeem with points"""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='loyalty_rewards', null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField()
    points_required = models.IntegerField(help_text="Points needed to redeem this reward")
    reward_type = models.CharField(max_length=20, choices=[
        ('discount', 'Discount'),
        ('product', 'Free Product'),
        ('voucher', 'Voucher'),
    ], default='discount')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Discount amount in KES")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, help_text="Free product reward")
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    max_redemptions = models.IntegerField(default=0, help_text="0 = unlimited")
    redemption_count = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['points_required']
    
    def __str__(self):
        return f"{self.name} ({self.points_required} points)"
    
    def is_available(self):
        """Check if reward is currently available"""
        if not self.is_active:
            return False
        
        from django.utils import timezone
        today = timezone.now().date()
        
        if self.valid_from and today < self.valid_from:
            return False
        
        if self.valid_until and today > self.valid_until:
            return False
        
        if self.max_redemptions > 0 and self.redemption_count >= self.max_redemptions:
            return False
        
        return True
    
    def can_redeem(self, customer):
        """Check if customer can redeem this reward"""
        return self.is_available() and customer.loyalty_points >= self.points_required


class LoyaltyRedemption(models.Model):
    """Track reward redemptions"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='reward_redemptions')
    reward = models.ForeignKey(LoyaltyReward, on_delete=models.PROTECT, related_name='redemptions')
    points_used = models.IntegerField()
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True)
    redeemed_at = models.DateTimeField(auto_now_add=True)
    redeemed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-redeemed_at']
    
    def __str__(self):
        return f"{self.customer.name} - {self.reward.name}"


# ==================== PAYMENT METHODS ====================

class PaymentMethod(CacheInvalidationMixin, models.Model):
    """Payment methods available in the system"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='payment_methods')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    requires_reference = models.BooleanField(default=False, help_text="Requires transaction reference (e.g., M-Pesa code)")
    icon = models.CharField(max_length=50, blank=True, help_text="Bootstrap icon class")
    
    class Meta:
        ordering = ['name']
        unique_together = [['business', 'code']]
    
    def __str__(self):
        return self.name


class SalePayment(AuditModelMixin, models.Model):
    """Track multiple payment methods for a single sale"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='sale_payments')
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference_number = models.CharField(max_length=100, blank=True, help_text="Transaction reference (M-Pesa, card, etc.)")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.sale.invoice_number} - {self.payment_method.name}: {self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.business_id and self.sale:
            self.business = self.sale.business
        super().save(*args, **kwargs)


# ==================== SHIFT MANAGEMENT ====================

class Shift(models.Model):
    """Track cashier shifts and cash drawer"""
    shift_number = models.CharField(max_length=20, unique=True, editable=False)
    cashier = models.ForeignKey(User, on_delete=models.PROTECT, related_name='shifts')
    
    # Shift timing
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(blank=True, null=True)
    
    # Cash drawer
    opening_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    closing_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0, blank=True)
    expected_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_difference = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Shift summary
    total_sales = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Status
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-start_time']
    
    def __str__(self):
        return f"{self.shift_number} - {self.cashier.username}"
    
    def save(self, *args, **kwargs):
        if not self.shift_number:
            # Generate shift number: SHIFT-YYYYMMDD-XXXX
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_shift = Shift.objects.filter(
                shift_number__startswith=f'SHIFT-{date_str}'
            ).order_by('-shift_number').first()
            if last_shift:
                last_num = int(last_shift.shift_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.shift_number = f'SHIFT-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)
    
    def close_shift(self, closing_cash):
        """Close the shift and calculate differences"""
        self.end_time = timezone.now()
        self.closing_cash = closing_cash
        
        # Calculate expected cash (opening + cash sales)
        cash_sales = SalePayment.objects.filter(
            sale__date__gte=self.start_time,
            sale__date__lte=self.end_time,
            sale__cashier=self.cashier,
            payment_method__code='CASH'
        ).aggregate(total=Sum('amount'))['total'] or Decimal(0)
        
        self.expected_cash = self.opening_cash + cash_sales
        self.cash_difference = self.closing_cash - self.expected_cash
        
        # Calculate shift summary
        shift_sales = Sale.objects.filter(
            date__gte=self.start_time,
            date__lte=self.end_time,
            cashier=self.cashier
        )
        self.total_sales = shift_sales.count()
        self.total_revenue = shift_sales.aggregate(total=Sum('total'))['total'] or Decimal(0)
        
        self.status = 'closed'
        self.save()


class DayClosureReport(models.Model):
        """
        Track official end-of-day Z-Report closures
        Ensures only one official closure per business per day
        Implements blind cash declaration for security
        """
        business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='day_closures')
        report_date = models.DateField(help_text='Date of the closure')

        # Closure metadata
        closed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='day_closures')
        closed_at = models.DateTimeField(auto_now_add=True)

        # Cash reconciliation (blind declaration)
        opening_cash = models.DecimalField(max_digits=12, decimal_places=2, help_text='Opening cash/floats')
        cash_sales = models.DecimalField(max_digits=12, decimal_places=2, help_text='Total cash sales for the day')
        expected_cash = models.DecimalField(max_digits=12, decimal_places=2, help_text='Opening + Cash sales')
        declared_cash = models.DecimalField(max_digits=12, decimal_places=2, help_text='Cash declared by cashier (blind)')
        variance = models.DecimalField(max_digits=12, decimal_places=2, help_text='Declared - Expected')

        # Sales summary
        total_transactions = models.IntegerField(default=0)
        total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
        total_discounts = models.DecimalField(max_digits=12, decimal_places=2, default=0)

        # Operational data
        shifts_closed = models.IntegerField(default=0, help_text='Number of shifts closed')
        floats_reconciled = models.IntegerField(default=0, help_text='Number of cash floats reconciled')

        notes = models.TextField(blank=True)

        class Meta:
            ordering = ['-report_date', '-closed_at']
            unique_together = [['business', 'report_date']]
            indexes = [
                models.Index(fields=['business', 'report_date']),
                models.Index(fields=['business', '-closed_at']),
            ]
            verbose_name = 'Day Closure Report'
            verbose_name_plural = 'Day Closure Reports'

        def __str__(self):
            return f"{self.business.name} - {self.report_date.strftime('%Y-%m-%d')} - Closed by {self.closed_by.username}"

        @property
        def is_balanced(self):
            """Check if cash is balanced (no variance)"""
            return self.variance == Decimal('0.00')

        @property
        def is_over(self):
            """Check if cash is over"""
            return self.variance > Decimal('0.00')

        @property
        def is_short(self):
            """Check if cash is short"""
            return self.variance < Decimal('0.00')

        @property
        def variance_status(self):
            """Get human-readable variance status"""
            if self.is_balanced:
                return 'Balanced'
            elif self.is_over:
                return f'Over by KES {self.variance:.2f}'
            else:
                return f'Short by KES {abs(self.variance):.2f}'



# ==================== RETURNS & REFUNDS ====================

class SaleReturn(models.Model):
    """Handle product returns and refunds"""
    return_number = models.CharField(max_length=20, unique=True, editable=False)
    original_sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Return details
    return_date = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    
    # Financial
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_refund = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Reason
    RETURN_REASONS = [
        ('defective', 'Defective Product'),
        ('wrong_item', 'Wrong Item'),
        ('not_satisfied', 'Customer Not Satisfied'),
        ('expired', 'Expired Product'),
        ('other', 'Other'),
    ]
    reason = models.CharField(max_length=20, choices=RETURN_REASONS)
    notes = models.TextField(blank=True)
    
    # Refund method
    refund_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    refund_reference = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['-return_date']
    
    def __str__(self):
        return f"{self.return_number} - {self.original_sale.invoice_number}"
    
    def save(self, *args, **kwargs):
        if not self.return_number:
            # Generate return number: RET-YYYYMMDD-XXXX
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_return = SaleReturn.objects.filter(
                return_number__startswith=f'RET-{date_str}'
            ).order_by('-return_number').first()
            if last_return:
                last_num = int(last_return.return_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            self.return_number = f'RET-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)


class SaleReturnItem(models.Model):
    """Individual items in a return"""
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Track if stock was returned
    stock_returned = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        self.total_price = Decimal(self.quantity) * self.unit_price
        super().save(*args, **kwargs)
        
        # Return stock if applicable
        if self.stock_returned:
            self.product.add_stock(self.quantity)
            
            # Create stock adjustment record
            StockAdjustment.objects.create(
                product=self.product,
                adjustment_type='return',
                quantity_change=self.quantity,
                previous_quantity=self.product.stock_quantity - self.quantity,
                new_quantity=self.product.stock_quantity,
                reason=f'Return: {self.sale_return.return_number}'
            )


# ==================== PROMOTIONS & DISCOUNTS ====================

class Promotion(models.Model):
    """
    Promotional campaigns — multi-tenant, per-business.

    Supported types:
      percentage   — X% off the cart total or qualifying items
      fixed        — KES X off the cart total
      buy_x_get_y  — Buy X qty of a product, get Y qty free (BOGO = buy 1 get 1)
      price_cut    — Override unit price to a fixed amount for qualifying products
      bundle       — Buy a set of products together at a reduced total price
      happy_hour   — Any discount type but only active during a daily time window
    """

    PROMO_TYPES = [
        ('percentage',  'Percentage Off'),
        ('fixed',       'Fixed Amount Off'),
        ('buy_x_get_y', 'Buy X Get Y Free'),
        ('price_cut',   'Price Cut (Fixed Price)'),
        ('bundle',      'Bundle Deal'),
        ('happy_hour',  'Happy Hour'),
    ]

    APPLIES_TO = [
        ('cart',     'Entire Cart'),
        ('products', 'Specific Products'),
        ('category', 'Specific Category'),
    ]

    # Multi-tenancy
    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='promotions',
        null=True, blank=True,  # nullable for migration; enforced at app level
    )

    # Identity
    name        = models.CharField(max_length=200)
    code        = models.CharField(
        max_length=50, blank=True,
        help_text="Optional promo code cashier/customer can enter. Leave blank for auto-apply."
    )
    description = models.TextField(blank=True)
    promo_type  = models.CharField(max_length=20, choices=PROMO_TYPES, default='percentage')

    # Discount value (meaning depends on promo_type)
    discount_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="% for percentage; KES amount for fixed; new price for price_cut; total for bundle"
    )

    # Buy X Get Y
    buy_quantity = models.PositiveIntegerField(
        default=1, help_text="Buy this many (BOGO: 1)"
    )
    get_quantity = models.PositiveIntegerField(
        default=1, help_text="Get this many free (BOGO: 1)"
    )

    # Scope
    applies_to           = models.CharField(max_length=10, choices=APPLIES_TO, default='cart')
    applicable_products  = models.ManyToManyField('Product',  blank=True, related_name='promotions')
    applicable_categories= models.ManyToManyField('Category', blank=True, related_name='promotions')

    # Happy Hour window (daily, in business local time)
    happy_hour_start = models.TimeField(
        null=True, blank=True,
        help_text="Daily start time for happy hour (e.g. 17:00)"
    )
    happy_hour_end = models.TimeField(
        null=True, blank=True,
        help_text="Daily end time for happy hour (e.g. 19:00)"
    )

    # Validity
    start_date = models.DateTimeField()
    end_date   = models.DateTimeField()
    is_active  = models.BooleanField(default=True)

    # Restrictions
    min_purchase_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Minimum cart total to qualify (0 = no minimum)"
    )
    max_uses   = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses_count = models.PositiveIntegerField(default=0, editable=False)

    # Audit
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_promotions'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # Codes must be unique per business (blank codes are allowed to repeat)
        constraints = [
            models.UniqueConstraint(
                fields=['business', 'code'],
                condition=models.Q(code__gt=''),
                name='unique_promo_code_per_business',
            )
        ]

    def __str__(self):
        return f"{self.name} [{self.get_promo_type_display()}]"

    # ── Validity helpers ──────────────────────────────────────────────────

    def is_valid(self, now=None):
        """Return True if the promotion is currently active and within limits."""
        from django.utils import timezone as tz
        now = now or tz.now()
        if not self.is_active:
            return False
        if now < self.start_date or now > self.end_date:
            return False
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False
        if self.promo_type == 'happy_hour':
            if self.happy_hour_start and self.happy_hour_end:
                local_time = now.astimezone().time().replace(second=0, microsecond=0)
                if not (self.happy_hour_start <= local_time <= self.happy_hour_end):
                    return False
        return True

    def can_apply_to_cart(self, cart_total):
        """Return True if the cart total meets the minimum purchase requirement."""
        if not self.is_valid():
            return False
        return cart_total >= self.min_purchase_amount

    def get_status_display_badge(self):
        """Return a CSS class string for the status badge."""
        if not self.is_active:
            return 'secondary'
        from django.utils import timezone as tz
        now = tz.now()
        if now < self.start_date:
            return 'info'       # upcoming
        if now > self.end_date:
            return 'danger'     # expired
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return 'warning'    # exhausted
        return 'success'        # active

    def get_status_label(self):
        if not self.is_active:
            return 'Disabled'
        from django.utils import timezone as tz
        now = tz.now()
        if now < self.start_date:
            return 'Upcoming'
        if now > self.end_date:
            return 'Expired'
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return 'Exhausted'
        return 'Active'



# ==================== EXPENSE TRACKING ====================

class ExpenseCategory(models.Model):
    """Categories for business expenses — per-business"""
    PREDEFINED = [
        'Rent', 'Salaries/Wages', 'Utilities', 'Marketing',
        'Maintenance', 'Packaging', 'Transport', 'Fuel', 'Stationery', 'Staff Welfare', 'Repairs', 'Miscellaneous',
    ]

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='expense_categories', null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    chart_of_accounts_code = models.CharField(max_length=50, blank=True, default='', help_text="Accounting code e.g. 5100, 5200")
    requires_manager_approval_above = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('1000.00'),
        help_text="Payout amount above which manager approval PIN/password is mandatory"
    )
    monthly_budget_cap = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Optional monthly expenditure ceiling for this category"
    )
    is_predefined = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Expense Categories"
        ordering = ['name']
        unique_together = [['business', 'name']]

    def __str__(self):
        return self.name


class Expense(models.Model):
    """Track business expenses — multi-tenant"""
    PAYMENT_CHOICES = [
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('mpesa', 'M-Pesa'),
        ('card', 'Card'),
        ('other', 'Other'),
    ]

    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='expenses')
    expense_number = models.CharField(max_length=20, editable=False)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses')
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    expense_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cash')
    reference_number = models.CharField(max_length=100, blank=True)
    attachment = models.FileField(upload_to='expenses/attachments/%Y/%m/', blank=True, null=True)

    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='recorded_expenses')
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expense_date', '-created_at']
        unique_together = [['business', 'expense_number']]

    def __str__(self):
        return f"{self.expense_number} - {self.description}"

    def save(self, *args, **kwargs):
        if not self.expense_number:
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last = Expense.objects.filter(
                business=self.business,
                expense_number__startswith=f'EXP-{date_str}'
            ).order_by('-expense_number').first()
            new_num = (int(last.expense_number.split('-')[-1]) + 1) if last else 1
            self.expense_number = f'EXP-{date_str}-{new_num:04d}'
        super().save(*args, **kwargs)


# ============================================
# EMAIL NOTIFICATION MODELS
# ============================================

class BusinessEmailSettings(models.Model):
    """Email settings and preferences per business"""
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='email_settings')
    
    # Custom SMTP Settings (optional - override global)
    use_custom_smtp = models.BooleanField(default=False, help_text='Use custom SMTP settings instead of global')
    smtp_host = models.CharField(max_length=200, blank=True)
    smtp_port = models.IntegerField(default=587)
    smtp_username = models.CharField(max_length=200, blank=True)
    smtp_password = models.CharField(max_length=200, blank=True)
    from_email = models.EmailField(blank=True)
    
    # Notification Preferences
    send_purchase_orders = models.BooleanField(default=True, help_text='Send purchase orders to suppliers')
    send_grn_notifications = models.BooleanField(default=True, help_text='Send GRN notifications to suppliers')
    send_payment_confirmations = models.BooleanField(default=True, help_text='Send payment confirmations to suppliers')
    send_license_reminders = models.BooleanField(default=True, help_text='Send license expiry reminders')
    send_low_stock_alerts = models.BooleanField(default=True, help_text='Send low stock alerts')
    send_daily_summaries = models.BooleanField(default=False, help_text='Send daily sales summaries')
    
    # Recipients
    admin_emails = models.TextField(blank=True, help_text='Comma-separated admin emails')
    manager_emails = models.TextField(blank=True, help_text='Comma-separated manager emails')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Business Email Settings'
        verbose_name_plural = 'Business Email Settings'
    
    def __str__(self):
        return f"Email Settings - {self.business.name}"
    
    def get_admin_emails(self):
        """Return list of admin emails"""
        if not self.admin_emails:
            return []
        return [email.strip() for email in self.admin_emails.split(',') if email.strip()]
    
    def get_manager_emails(self):
        """Return list of manager emails"""
        if not self.manager_emails:
            return []
        return [email.strip() for email in self.manager_emails.split(',') if email.strip()]


class EmailTemplate(models.Model):
    """Email templates for different notification types"""
    TEMPLATE_TYPES = [
        ('purchase_order', 'Purchase Order'),
        ('grn', 'Goods Returned Note'),
        ('payment_confirmation', 'Payment Confirmation'),
        ('license_expiry', 'License Expiry'),
        ('sale_receipt', 'Sale Receipt'),
        ('low_stock', 'Low Stock Alert'),
        ('daily_summary', 'Daily Summary'),
    ]
    
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='email_templates')
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES)
    subject = models.CharField(max_length=200)
    body_html = models.TextField(help_text='HTML email body with {variable} placeholders')
    body_text = models.TextField(help_text='Plain text email body with {variable} placeholders')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Email Template'
        verbose_name_plural = 'Email Templates'
        ordering = ['template_type', 'name']
    
    def __str__(self):
        return f"{self.get_template_type_display()} - {self.name}"


class EmailLog(models.Model):
    """Track all sent emails"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='email_logs', null=True, blank=True)
    template_type = models.CharField(max_length=50)
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Email Log'
        verbose_name_plural = 'Email Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'status', '-created_at']),
            models.Index(fields=['template_type', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.template_type} to {self.recipient} - {self.status}"


# ==================== CASH FLOAT MANAGEMENT ====================

class CashFloat(models.Model):
    """Track cash floats given to cashiers for making change"""
    FLOAT_TYPES = [
        ('opening', 'Opening Float'),
        ('additional', 'Additional Float'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('returned', 'Returned'),
        ('reconciled', 'Reconciled'),
    ]
    
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='cash_floats')
    float_number = models.CharField(max_length=50, unique=True)
    cashier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cash_floats')
    given_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='floats_given')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    float_type = models.CharField(max_length=20, choices=FLOAT_TYPES, default='opening')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    given_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    returned_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text='Difference between expected and returned amount'
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-given_at']
        indexes = [
            models.Index(fields=['business', 'cashier', '-given_at']),
            models.Index(fields=['business', 'status']),
        ]
    
    def __str__(self):
        return f"{self.float_number} - {self.cashier.username} - KES {self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.float_number:
            # Generate float number: FLT-YYYYMMDD-XXXX
            from django.utils import timezone
            today = timezone.now().strftime('%Y%m%d')
            last_float = CashFloat.objects.filter(
                float_number__startswith=f'FLT-{today}'
            ).order_by('-float_number').first()
            
            if last_float:
                last_num = int(last_float.float_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
            
            self.float_number = f'FLT-{today}-{new_num:04d}'
        
        super().save(*args, **kwargs)
    
    def return_float(self, returned_amount, notes=''):
        """Mark float as returned and calculate variance"""
        from django.utils import timezone
        self.returned_at = timezone.now()
        self.returned_amount = returned_amount
        self.variance = returned_amount - self.amount
        self.status = 'returned'
        if notes:
            self.notes = notes
        self.save()
    
    def reconcile(self):
        """Mark float as reconciled"""
        self.status = 'reconciled'
        self.save()
    
    @property
    def is_active(self):
        return self.status == 'active'
    
    @property
    def expected_return(self):
        """Calculate expected return amount (float + sales - change given)"""
        # This would need to be calculated based on sales made during the float period
        return self.amount


# ==================== IDEMPOTENCY KEY MANAGEMENT ====================

class IdempotencyKey(models.Model):
    """
    Idempotency keys for preventing duplicate request processing.
    
    Stores request fingerprints to detect and prevent duplicate operations
    within a configurable time window (default 24 hours).
    """
    key = models.CharField(max_length=255, unique=True, db_index=True)
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='idempotency_keys')
    operation_type = models.CharField(max_length=50)
    request_data = models.JSONField()
    response_data = models.JSONField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['business', 'operation_type', 'created_at'], name='pos_idempot_busines_idx'),
            models.Index(fields=['expires_at'], name='pos_idempot_expires_idx'),
        ]
    
    def __str__(self):
        return f"{self.operation_type} - {self.key} ({self.status})"
    
    def is_expired(self):
        """Check if this idempotency key has expired."""
        from django.utils import timezone
        return timezone.now() > self.expires_at


class SupportAccessRequest(models.Model):
    """
    Support access request system for platform admins to access business dashboards
    with explicit permission from business owners.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='support_access_requests')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_requests_made')
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
        ('expired', 'Expired'),
        ('revoked', 'Revoked')
    ], default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='support_approvals')
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(help_text="Reason for requesting access")
    notes = models.TextField(blank=True, help_text="Additional notes from business owner")

    class Meta:
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['requested_by', 'status']),
        ]

    def __str__(self):
        return f"Support Access: {self.requested_by.username} -> {self.business.name} ({self.status})"

    def is_active(self):
        """Check if access is currently active"""
        if self.status != 'approved':
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            self.status = 'expired'
            self.save()
            return False
        return True

    def approve(self, approver, duration_hours=24):
        """Approve the access request"""
        self.status = 'approved'
        self.approved_by = approver
        self.approved_at = timezone.now()
        self.expires_at = timezone.now() + timezone.timedelta(hours=duration_hours)
        self.save()

    def deny(self, approver, notes=''):
        """Deny the access request"""
        self.status = 'denied'
        self.approved_by = approver
        self.approved_at = timezone.now()
        self.notes = notes
        self.save()

    def revoke(self):
        """Revoke active access"""
        self.status = 'revoked'
        self.save()

        def approve(self, approver, duration_hours=24):
            """Approve the access request"""
            self.status = 'approved'
            self.approved_by = approver
            self.approved_at = timezone.now()
            self.expires_at = timezone.now() + timezone.timedelta(hours=duration_hours)
            self.save()

        def deny(self, approver, notes=''):
            """Deny the access request"""
            self.status = 'denied'
            self.approved_by = approver
            self.approved_at = timezone.now()
            self.notes = notes
            self.save()

        def revoke(self):
            """Revoke active access"""
            self.status = 'revoked'
            self.save()




# ============================================================================
# NEW Z-REPORT SYSTEM - Production-Ready Financial Reporting
# ============================================================================

class POSSession(models.Model):
    """
    Represents a single POS session (business day).
    Immutable once closed. One session per business day.
    """
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name='pos_sessions')
    session_number = models.IntegerField(help_text="Sequential number per business")
    
    # Session lifecycle
    opened_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sessions_opened')
    cashier = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='cashier_sessions')
    opened_at = models.DateTimeField(auto_now_add=True)
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Starting cash in drawer")
    
    status = models.CharField(max_length=20, choices=[
        ('open', 'Open'),
        ('closed', 'Closed'),
    ], default='open', db_index=True)
    
    closed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name='sessions_closed')
    closed_at = models.DateTimeField(null=True, blank=True)
    closing_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Counted cash at close")
    cash_difference = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Difference between expected and counted cash")
    
    # Metadata
    notes = models.TextField(blank=True, help_text="Optional notes about this session")
    branch = models.ForeignKey('Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='pos_sessions')
    terminal = models.ForeignKey('POSTerminal', null=True, blank=True, on_delete=models.SET_NULL, related_name='sessions')
    terminal_identifier = models.CharField(max_length=128, blank=True, help_text="Snapshot of terminal identifier/code")
    
    class Meta:
        unique_together = [['business', 'session_number']]
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['business', 'opened_at']),
            models.Index(fields=['status', 'opened_at']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status='open') | (models.Q(status='closed') & models.Q(closed_at__isnull=False)),
                name='pos_session_closed_requires_timestamp'
            ),
            models.CheckConstraint(
                condition=models.Q(opening_cash__gte=0),
                name='pos_session_opening_cash_non_negative'
            ),
        ]
        verbose_name = 'POS Session'
        verbose_name_plural = 'POS Sessions'
    
    def __str__(self):
        return f"{self.business.name} - Session #{self.session_number} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        # Auto-generate session number if not set
        if not self.session_number:
            last_session = POSSession.objects.filter(business=self.business).order_by('-session_number').first()
            self.session_number = (last_session.session_number + 1) if last_session else 1
        super().save(*args, **kwargs)
    
    def can_close(self):
        """Check if session can be closed"""
        return self.status == 'open'
    
    def get_sales_count(self):
        """Get number of sales in this session"""
        return self.sales.count()
    
    def get_total_sales(self):
        """Get total sales amount"""
        from django.db.models import Sum
        return self.sales.aggregate(total=Sum('total'))['total'] or Decimal('0.00')


class ZReport(models.Model):
    """
    Immutable end-of-day financial report.
    Once created, cannot be edited or deleted - only voided.
    """
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name='z_reports')
    z_number = models.IntegerField(editable=False, help_text="Sequential Z-Report number")
    session = models.OneToOneField(POSSession, on_delete=models.PROTECT, related_name='z_report')
    
    # Creation metadata (immutable)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, editable=False, related_name='z_reports_created')
    
    # Financial snapshot (immutable JSON)
    report_data = models.JSONField(editable=False, help_text="Complete immutable financial snapshot")
    
    # Integrity verification
    data_hash = models.CharField(max_length=64, editable=False, help_text="SHA256 hash of report_data")
    
    # Void handling (never delete, only void)
    is_voided = models.BooleanField(default=False, db_index=True)
    voided_at = models.DateTimeField(null=True, blank=True, editable=False)
    voided_by = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        related_name='z_reports_voided', 
        editable=False
    )
    void_reason = models.TextField(blank=True, editable=False)
    
    class Meta:
        unique_together = [['business', 'z_number']]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'z_number']),
            models.Index(fields=['business', 'created_at']),
            models.Index(fields=['is_voided']),
            models.Index(fields=['business', 'is_voided', 'created_at']),
        ]
        permissions = [
            ('can_close_session', 'Can close POS session and generate Z-Report'),
            ('can_void_zreport', 'Can void Z-Report'),
            ('can_export_zreport', 'Can export Z-Report'),
            ('can_verify_zreport', 'Can verify Z-Report integrity'),
        ]
        verbose_name = 'Z-Report'
        verbose_name_plural = 'Z-Reports'
    
    def __str__(self):
        status = " (VOIDED)" if self.is_voided else ""
        return f"Z-{self.z_number:05d} - {self.business.name}{status}"
    
    def save(self, *args, **kwargs):
        if self.pk:
            original = ZReport.objects.get(pk=self.pk)
            immutable_fields = [
                'business_id',
                'z_number',
                'session_id',
                'created_by_id',
                'report_data',
                'data_hash',
            ]
            for field_name in immutable_fields:
                if getattr(self, field_name) != getattr(original, field_name):
                    raise ValidationError(f"Z-Report field '{field_name}' cannot be modified after creation")

        # Auto-generate Z-number if not set
        if not self.z_number:
            last_report = ZReport.objects.filter(business=self.business).order_by('-z_number').first()
            self.z_number = (last_report.z_number + 1) if last_report else 1
        
        # Generate hash if not set
        if not self.data_hash and self.report_data:
            import hashlib
            import json
            data_string = json.dumps(self.report_data, sort_keys=True)
            self.data_hash = hashlib.sha256(data_string.encode()).hexdigest()
        
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Z-Reports cannot be deleted")
    
    def verify_integrity(self):
        """Verify that report data hasn't been tampered with"""
        import hashlib
        import json
        data_string = json.dumps(self.report_data, sort_keys=True)
        computed_hash = hashlib.sha256(data_string.encode()).hexdigest()
        return computed_hash == self.data_hash
    
    def can_void(self):
        """Check if report can be voided"""
        return not self.is_voided
    
    def get_gross_sales(self):
        """Get gross sales from report data"""
        return Decimal(str(self.report_data.get('sales_summary', {}).get('gross_sales', 0)))
    
    def get_net_sales(self):
        """Get net sales from report data"""
        return Decimal(str(self.report_data.get('sales_summary', {}).get('net_sales', 0)))
    
    def get_cash_difference(self):
        """Get cash difference (over/short)"""
        return Decimal(str(self.report_data.get('cash_management', {}).get('difference', 0)))


class ZReportAuditLog(models.Model):
    """
    Immutable audit trail for all Z-Report operations.
    Every action on a Z-Report is logged here.
    """
    zreport = models.ForeignKey(ZReport, on_delete=models.PROTECT, related_name='audit_logs')
    action = models.CharField(max_length=50, choices=[
        ('created', 'Created'),
        ('viewed', 'Viewed'),
        ('exported_pdf', 'Exported PDF'),
        ('exported_csv', 'Exported CSV'),
        ('exported_json', 'Exported JSON'),
        ('voided', 'Voided'),
        ('integrity_verified', 'Integrity Verified'),
        ('integrity_failed', 'Integrity Check Failed'),
        ('printed', 'Printed'),
    ], db_index=True)
    
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    performed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # Request metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Additional details
    details = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-performed_at']
        indexes = [
            models.Index(fields=['zreport', 'performed_at']),
            models.Index(fields=['performed_by', 'performed_at']),
            models.Index(fields=['action', 'performed_at']),
        ]
        verbose_name = 'Z-Report Audit Log'
        verbose_name_plural = 'Z-Report Audit Logs'
    
    def __str__(self):
        return f"{self.zreport} - {self.get_action_display()} by {self.performed_by.username}"
    
    def save(self, *args, **kwargs):
        # Audit logs are immutable - prevent updates
        if self.pk:
            raise ValueError("Audit logs cannot be modified")
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        # Audit logs cannot be deleted
        raise ValueError("Audit logs cannot be deleted")


# ============================================================================
# REGISTRATION CONTROL MODELS
# ============================================================================

class InvitationCode(models.Model):
    """Invitation codes for controlled registration"""
    
    code = models.CharField(max_length=20, unique=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='invitation_codes_created')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Usage limits
    max_uses = models.IntegerField(default=1, help_text="Maximum number of times this code can be used")
    uses_count = models.IntegerField(default=0, help_text="Number of times this code has been used")
    
    # Validity
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True, help_text="Leave blank for no expiry")
    is_active = models.BooleanField(default=True)
    
    # Restrictions
    allowed_email_domains = models.TextField(
        blank=True,
        help_text="Comma-separated list of allowed email domains (e.g., company.com, partner.co.ke)"
    )
    notes = models.TextField(blank=True, help_text="Internal notes about this code")
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code', 'is_active']),
            models.Index(fields=['valid_until']),
        ]
    
    def __str__(self):
        return f"{self.code} ({self.uses_count}/{self.max_uses})"
    
    def is_valid(self):
        """Check if code is currently valid"""
        now = timezone.now()
        
        # Check if active
        if not self.is_active:
            return False, "This invitation code has been deactivated"
        
        # Check usage limit
        if self.uses_count >= self.max_uses:
            return False, "This invitation code has reached its usage limit"
        
        # Check validity period
        if now < self.valid_from:
            return False, "This invitation code is not yet valid"
        
        if self.valid_until and now > self.valid_until:
            return False, "This invitation code has expired"
        
        return True, "Valid"
    
    def can_use_with_email(self, email):
        """Check if email domain is allowed"""
        if not self.allowed_email_domains:
            return True, "Valid"
        
        email_domain = email.split('@')[1].lower()
        allowed_domains = [d.strip().lower() for d in self.allowed_email_domains.split(',')]
        
        if email_domain in allowed_domains:
            return True, "Valid"
        
        return False, f"Email domain {email_domain} is not allowed for this invitation code"
    
    def use(self):
        """Increment usage count"""
        self.uses_count += 1
        self.save()


class BusinessRegistration(models.Model):
    """Track business registration requests"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('email_verified', 'Email Verified'),
        ('pending_approval', 'Pending Admin Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    # User info
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    
    # Business info
    business_name = models.CharField(max_length=200)
    business_type = models.CharField(max_length=100, blank=True)
    kra_pin = models.CharField(max_length=20, blank=True)
    
    # Registration tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    invitation_code = models.ForeignKey(InvitationCode, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Verification
    email_verification_token = models.CharField(max_length=100, unique=True, null=True, blank=True)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    
    # Approval
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='registrations_reviewed')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    
    # Completion
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='registration')
    business = models.OneToOneField(Business, on_delete=models.SET_NULL, null=True, blank=True, related_name='registration')
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"{self.business_name} - {self.email} ({self.get_status_display()})"
    
    def generate_verification_token(self):
        """Generate email verification token"""
        import secrets
        self.email_verification_token = secrets.token_urlsafe(32)
        self.save()
        return self.email_verification_token
    
    def verify_email(self):
        """Mark email as verified"""
        self.email_verified_at = timezone.now()
        self.status = 'email_verified'
        self.save()


class RegistrationSettings(models.Model):
    """Global registration control settings"""
    
    # Invitation codes
    require_invitation_code = models.BooleanField(
        default=False,
        help_text="Require invitation code for registration"
    )
    
    # Email verification
    require_email_verification = models.BooleanField(
        default=True,
        help_text="Require email verification before activation"
    )
    
    # Admin approval
    require_admin_approval = models.BooleanField(
        default=False,
        help_text="Require admin approval for new registrations"
    )
    
    # Rate limiting
    max_registrations_per_ip_per_day = models.IntegerField(
        default=3,
        help_text="Maximum registrations from same IP per day"
    )
    max_registrations_per_email_domain_per_day = models.IntegerField(
        default=10,
        help_text="Maximum registrations from same email domain per day"
    )
    
    # Blocked domains
    blocked_email_domains = models.TextField(
        blank=True,
        help_text="Comma-separated list of blocked email domains (e.g., tempmail.com, guerrillamail.com)"
    )
    
    # Allowed domains (whitelist)
    allowed_email_domains = models.TextField(
        blank=True,
        help_text="If set, only these domains are allowed (comma-separated)"
    )
    
    # Business validation
    require_kra_pin = models.BooleanField(
        default=False,
        help_text="Require KRA PIN for registration"
    )
    require_phone_verification = models.BooleanField(
        default=False,
        help_text="Require phone number verification (SMS)"
    )
    
    # Notifications
    notify_admin_on_registration = models.BooleanField(
        default=True,
        help_text="Send email to admins on new registration"
    )
    admin_notification_emails = models.TextField(
        blank=True,
        help_text="Comma-separated list of admin emails for notifications"
    )
    
    # Messages
    registration_closed_message = models.TextField(
        blank=True,
        default="Registration is currently closed. Please contact support for access.",
        help_text="Message shown when registration is disabled"
    )
    
    # Status
    registration_enabled = models.BooleanField(
        default=True,
        help_text="Enable/disable all registrations"
    )
    
    class Meta:
        verbose_name = "Registration Settings"
        verbose_name_plural = "Registration Settings"
    
    def __str__(self):
        return "Registration Settings"
    
    @classmethod
    def get_settings(cls):
        """Get or create settings singleton"""
        settings, created = cls.objects.get_or_create(pk=1)
        return settings
    
    def is_email_allowed(self, email):
        """Check if email domain is allowed"""
        domain = email.split('@')[1].lower()
        
        # Check blocked domains
        if self.blocked_email_domains:
            blocked = [d.strip().lower() for d in self.blocked_email_domains.split(',')]
            if domain in blocked:
                return False, f"Email domain {domain} is not allowed"
        
        # Check whitelist
        if self.allowed_email_domains:
            allowed = [d.strip().lower() for d in self.allowed_email_domains.split(',')]
            if domain not in allowed:
                return False, f"Email domain {domain} is not in the allowed list"
        
        return True, "Valid"
    
    def check_rate_limit_ip(self, ip_address):
        """Check if IP has exceeded rate limit"""
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(days=1)
        
        count = BusinessRegistration.objects.filter(
            ip_address=ip_address,
            created_at__gte=cutoff
        ).count()
        
        if count >= self.max_registrations_per_ip_per_day:
            return False, f"Too many registrations from this IP address. Please try again later."
        
        return True, "Valid"
    
    def check_rate_limit_domain(self, email):
        """Check if email domain has exceeded rate limit"""
        from datetime import timedelta
        domain = email.split('@')[1].lower()
        cutoff = timezone.now() - timedelta(days=1)
        
        count = BusinessRegistration.objects.filter(
            email__iendswith=f'@{domain}',
            created_at__gte=cutoff
        ).count()
        
        if count >= self.max_registrations_per_email_domain_per_day:
            return False, f"Too many registrations from {domain}. Please try again later."
        
        return True, "Valid"


# ==================== CUSTOMER CREDIT ====================

class CustomerPayment(models.Model):
    """Payments made by customers against their credit balance"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='customer_payments')
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='credit_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.SET_NULL, null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True, help_text="Cheque/M-Pesa reference")
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.customer.name} - KES {self.amount} on {self.created_at.date()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Reduce customer credit balance
        self.customer.credit_balance = max(
            Decimal('0'),
            self.customer.credit_balance - self.amount
        )
        self.customer.save(update_fields=['credit_balance'])


# ==================== MARKETING / CAMPAIGNS ====================

class CustomerSegment(models.Model):
    """Dynamic customer segments for targeting"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='customer_segments')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Segment criteria
    CRITERIA_CHOICES = [
        ('all', 'All Customers'),
        ('vip', 'VIP Customers'),
        ('wholesale', 'Wholesale Customers'),
        ('high_value', 'High Value (Top Spenders)'),
        ('inactive', 'Inactive (No purchase in 90 days)'),
        ('loyalty_tier', 'By Loyalty Tier'),
        ('credit_overdue', 'Credit Overdue'),
    ]
    criteria = models.CharField(max_length=30, choices=CRITERIA_CHOICES, default='all')
    criteria_value = models.CharField(max_length=100, blank=True, help_text="e.g. tier name or threshold")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_customers(self):
        """Return queryset of customers matching this segment"""
        qs = Customer.objects.filter(business=self.business, is_active=True)
        if self.criteria == 'vip':
            return qs.filter(customer_type='vip')
        elif self.criteria == 'wholesale':
            return qs.filter(customer_type='wholesale')
        elif self.criteria == 'high_value':
            return qs.order_by('-total_purchases')[:50]
        elif self.criteria == 'inactive':
            from django.utils import timezone
            cutoff = timezone.now() - timezone.timedelta(days=90)
            active_ids = Sale.objects.filter(
                business=self.business, date__gte=cutoff
            ).values_list('customer_id', flat=True)
            return qs.exclude(id__in=active_ids)
        elif self.criteria == 'loyalty_tier' and self.criteria_value:
            return qs.filter(tier=self.criteria_value)
        elif self.criteria == 'credit_overdue':
            return qs.filter(credit_balance__gt=0)
        return qs


# ==============================
# Backup & Security Models
# ==============================

class BackupAuditLog(models.Model):
    """Audit trail for all backup and restore operations"""
    
    OPERATION_TYPES = [
        ('backup_database', 'Database Backup'),
        ('backup_media', 'Media Backup'),
        ('backup_business', 'Business Backup'),
        ('restore_database', 'Database Restore'),
        ('restore_media', 'Media Restore'),
        ('restore_business', 'Business Restore'),
        ('verify_backup', 'Backup Verification'),
        ('delete_backup', 'Backup Deletion'),
    ]
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('warning', 'Warning'),
        ('in_progress', 'In Progress'),
    ]
    
    # Who performed it
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='backup_operations'
    )
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, null=True, blank=True,
        related_name='backup_audit_logs'
    )
    
    # What happened
    operation = models.CharField(max_length=30, choices=OPERATION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    
    # Backup file details
    backup_file = models.CharField(max_length=255, help_text='Path or name of backup file')
    backup_size_mb = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Size of backup in MB'
    )
    backup_checksum = models.CharField(
        max_length=64, blank=True, help_text='SHA-256 checksum'
    )
    is_encrypted = models.BooleanField(default=True, help_text='Whether backup was encrypted')
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    
    # Metadata
    details = models.JSONField(default=dict, blank=True, help_text='Additional operation details')
    error_message = models.TextField(blank=True, help_text='If failed, the error details')
    
    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', '-started_at']),
            models.Index(fields=['business', '-started_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.get_operation_display()} ({self.get_status_display()}) - {self.started_at:%Y-%m-%d %H:%M}"
    
    @classmethod
    def log_backup_operation(cls, operation, user=None, business=None, 
                            backup_file='', status='success', error_message='', **kwargs):
        """Log a backup operation with proper timestamps and details"""
        from django.utils import timezone
        import time
        
        log_entry = cls(
            operation=operation,
            user=user,
            business=business,
            backup_file=backup_file,
            status=status,
            error_message=error_message,
            details=kwargs,
            started_at=timezone.now()
        )
        
        if status in ['success', 'failed', 'warning']:
            log_entry.completed_at = timezone.now()
            if log_entry.started_at and log_entry.completed_at:
                log_entry.duration_seconds = int(
                    (log_entry.completed_at - log_entry.started_at).total_seconds()
                )
        
        log_entry.save()
        return log_entry


class Campaign(models.Model):
    """Email/SMS marketing campaigns"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='campaigns')
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=300, blank=True, help_text="Email subject line")
    message = models.TextField(help_text="Campaign message body")

    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
    ]
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default='email')

    segment = models.ForeignKey(CustomerSegment, on_delete=models.SET_NULL, null=True, blank=True)

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipients_count = models.IntegerField(default=0)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.channel})"


# ==================== WEBHOOKS ====================

WEBHOOK_EVENTS = [
    ('sale.created', 'Sale Created'),
    ('sale.refunded', 'Sale Refunded'),
    ('product.low_stock', 'Product Low Stock'),
    ('product.out_of_stock', 'Product Out of Stock'),
    ('customer.created', 'Customer Created'),
    ('purchase.created', 'Purchase Created'),
    ('purchase.received', 'Purchase Received'),
    ('stock.adjusted', 'Stock Adjusted'),
    ('payment.received', 'Payment Received'),
]


class Webhook(models.Model):
    """Outbound webhook subscriptions per business"""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='webhooks')
    name = models.CharField(max_length=100)
    url = models.URLField(max_length=500)
    secret = models.CharField(max_length=100, blank=True, help_text='HMAC-SHA256 signing secret')
    events = models.JSONField(default=list, help_text='List of subscribed event types')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} → {self.url}"

    def subscribes_to(self, event: str) -> bool:
        return '*' in self.events or event in self.events

    def clean(self):
        if not self.pk and self.is_active:
            count = Webhook.objects.filter(business=self.business, is_active=True).count()
            if count >= 20:
                raise ValidationError('Maximum of 20 active webhooks per business.')


class WebhookDelivery(models.Model):
    """Log of every webhook dispatch attempt"""
    webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name='deliveries')
    event = models.CharField(max_length=100)
    payload = models.JSONField()
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    success = models.BooleanField(default=False)
    attempt = models.IntegerField(default=1)
    delivered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-delivered_at']

    def __str__(self):
        status = 'OK' if self.success else 'FAIL'
        return f"[{status}] {self.event} → {self.webhook.url}"


# ==================== API KEYS ====================

class APIKey(models.Model):
    """Long-lived bearer tokens for external Integration API access, scoped to a Business."""
    key = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=100, help_text='Human-readable label for this key')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='api_keys')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_api_keys'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.business.slug})"


class HeldOrder(models.Model):
    """Cart saved mid-sale, retrievable from any terminal on the same business."""
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='held_orders')
    cashier = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='held_orders'
    )
    name = models.CharField(max_length=100)
    cart_json = models.JSONField(help_text='Serialised cart items array')
    customer_json = models.JSONField(null=True, blank=True, help_text='Selected customer snapshot')
    discount_type = models.CharField(max_length=20, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.business.slug} ({self.created_at:%Y-%m-%d %H:%M})"


# ---------------------------------------------------------------------------
# Multi-Branch models
# ---------------------------------------------------------------------------

class BranchError(Exception):
    """Base exception for all branch-related errors."""
    pass


class InsufficientStockError(BranchError):
    def __init__(self, branch=None, product=None, available=None, requested=None):
        self.branch = branch
        self.product = product
        self.available = available
        self.requested = requested
        super().__init__(
            f"Insufficient stock: available={available}, requested={requested}"
        )


class BranchInactiveError(BranchError):
    pass


class PlanLimitError(BranchError):
    pass


class InvalidTransferStateError(BranchError):
    pass


class Branch(models.Model):
    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='branches'
    )
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    address = models.TextField()
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    is_hq = models.BooleanField(
        default=False,
        help_text="Designates this branch as the central HQ. Exactly one branch per business can be HQ."
    )

    # KRA TIMS / eTIMS Multi-Branch Compliance (Kenya)
    kra_pin = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Branch-specific KRA PIN (defaults to business KRA PIN if blank)"
    )
    kra_branch_id = models.CharField(
        max_length=10,
        blank=True,
        default='00',
        help_text="KRA eTIMS Branch ID (e.g. 00 for HQ, 01 for Branch 1, 02 for Branch 2)"
    )
    cu_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Branch Control Unit Number (e.g., KRAMW0012345)"
    )
    cu_serial_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Branch CU Device / VSCU Serial Number"
    )
    tims_middleware_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Local/LAN endpoint for TIMS middleware (e.g. http://192.168.1.150:8080)"
    )
    tims_enabled = models.BooleanField(
        default=False,
        help_text="Enable KRA TIMS/eTIMS invoice signing for this branch"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['business', 'name'], ['business', 'code']]
        verbose_name_plural = 'branches'

    def __str__(self):
        hq_flag = " [HQ]" if self.is_hq else ""
        return f"{self.name} ({self.code}){hq_flag}"

    def _generate_code(self):
        import re
        prefix = re.sub(r'[^A-Za-z]', '', self.name)[:3].upper()
        if not prefix:
            prefix = 'BRN'
        count = Branch.objects.filter(business=self.business).count()
        return f"{prefix}-{count + 1:03d}"

    def clean(self):
        super().clean()
        if self.business_id:
            # If no other branch is HQ in this business, this branch must be HQ
            other_hq = Branch.objects.filter(business=self.business, is_hq=True).exclude(pk=self.pk)
            if not other_hq.exists() and not self.is_hq:
                # If this is the only branch, make it HQ by default
                total_branches = Branch.objects.filter(business=self.business).exclude(pk=self.pk).count()
                if total_branches == 0:
                    self.is_hq = True

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        if self.is_default:
            Branch.objects.filter(
                business=self.business, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        if self.is_hq:
            Branch.objects.filter(
                business=self.business, is_hq=True
            ).exclude(pk=self.pk).update(is_hq=False)
        elif self.business_id and not Branch.objects.filter(business=self.business, is_hq=True).exclude(pk=self.pk).exists():
            # Guarantee at least one HQ branch exists per business
            self.is_hq = True
        super().save(*args, **kwargs)


class BranchMembership(models.Model):
    ROLE_CHOICES = [
        ('cashier', 'Cashier'),
        ('branch_manager', 'Branch Manager'),
        ('hq_admin', 'HQ Admin'),
        ('manager', 'Manager'),
        ('stock_manager', 'Stock Manager'),
        ('sales', 'Sales Associate'),
        ('viewer', 'Viewer'),
    ]
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='branch_memberships'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='memberships'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    is_home_branch = models.BooleanField(
        default=False,
        help_text="Default home branch for initial user scoping"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['user', 'branch']]

    def __str__(self):
        home_tag = " (Home)" if self.is_home_branch else ""
        return f"{self.user} @ {self.branch} ({self.role}){home_tag}"

    def save(self, *args, **kwargs):
        if self.is_home_branch and self.user_id:
            BranchMembership.objects.filter(
                user=self.user, is_home_branch=True
            ).exclude(pk=self.pk).update(is_home_branch=False)
        super().save(*args, **kwargs)


# Alias for explicit domain naming
BranchStaff = BranchMembership


class BranchStock(models.Model):
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='stock_records'
    )
    product = models.ForeignKey(
        'Product', on_delete=models.CASCADE, related_name='branch_stocks'
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    average_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Moving weighted average cost per unit"
    )
    reorder_level = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('10.000'),
        help_text="Branch-specific reorder trigger level"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['branch', 'product']]
        indexes = [models.Index(fields=['branch', 'product'])]

    def __str__(self):
        return f"{self.product.name} @ {self.branch.name}: {self.quantity} (Avg Cost: KES {self.average_cost})"

    @property
    def is_low_stock(self):
        return self.quantity <= self.reorder_level

    @property
    def stock_value(self):
        return (self.quantity * self.average_cost).quantize(Decimal('0.01'))

    def receive(self, qty=None, unit_cost=None, movement_type='purchase_in', reference_obj=None, user=None, note='', quantity=None, performed_by=None, notes=''):
        """
        Add stock to this branch, recalculate moving-average unit cost,
        and atomically write an append-only StockMovement ledger entry.
        """
        from django.db import transaction
        from decimal import Decimal
        from django.contrib.contenttypes.models import ContentType

        qty_val = qty if qty is not None else quantity
        if qty_val is None:
            raise ValueError("Quantity is required.")
        qty = Decimal(str(qty_val))
        unit_cost = Decimal(str(unit_cost)) if unit_cost is not None else self.average_cost
        user = user or performed_by
        note = note or notes

        if qty <= 0:
            raise ValueError("Received quantity must be greater than zero.")

        with transaction.atomic():
            stock = BranchStock.objects.select_for_update().get(pk=self.pk)
            existing_qty = stock.quantity
            existing_cost = stock.average_cost

            if existing_qty <= 0:
                new_avg_cost = unit_cost
            else:
                total_existing = existing_qty * existing_cost
                total_new = qty * unit_cost
                new_total_qty = existing_qty + qty
                if new_total_qty > 0:
                    new_avg_cost = ((total_existing + total_new) / new_total_qty).quantize(Decimal('0.01'))
                else:
                    new_avg_cost = unit_cost

            stock.average_cost = new_avg_cost
            stock.quantity += qty
            stock.save(update_fields=['quantity', 'average_cost', 'updated_at'])

            # Synchronize product.stock_quantity aggregate
            total_prod_qty = BranchStock.objects.filter(
                branch__business=stock.branch.business, product=stock.product
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
            Product.objects.filter(pk=stock.product_id).update(stock_quantity=total_prod_qty)

            # Generic relation extraction
            ct = None
            obj_id = None
            ref_num = ''
            if reference_obj:
                ct = ContentType.objects.get_for_model(reference_obj)
                obj_id = str(reference_obj.pk)
                ref_num = getattr(
                    reference_obj, 'reference_number',
                    getattr(reference_obj, 'reference', getattr(reference_obj, 'invoice_number', str(reference_obj)))
                )

            total_cost = (qty * unit_cost).quantize(Decimal('0.01'))
            movement = StockMovement.objects.create(
                business=stock.branch.business,
                branch=stock.branch,
                product=stock.product,
                quantity_delta=qty,
                unit_cost=unit_cost,
                total_cost=total_cost,
                movement_type=movement_type,
                content_type=ct,
                object_id=obj_id,
                reference_number=ref_num,
                balance_after=stock.quantity,
                resulted_in_negative_stock=stock.quantity < 0,
                performed_by=user,
                note=note,
            )

            self.quantity = stock.quantity
            self.average_cost = stock.average_cost
            return stock, movement

    def deduct(self, qty=None, movement_type='sale', reference_obj=None, user=None, note='', unit_cost=None, quantity=None, performed_by=None, notes='', terminal=None, idempotency_key=None):
        """
        Deduct stock from this branch, allow negative stock with warning/flag,
        and atomically write an append-only StockMovement ledger entry.
        """
        from django.db import transaction
        from decimal import Decimal
        from django.contrib.contenttypes.models import ContentType

        qty_val = qty if qty is not None else quantity
        if qty_val is None:
            raise ValueError("Quantity is required.")
        qty = Decimal(str(qty_val))
        user = user or performed_by
        note = note or notes
        if qty <= 0:
            raise ValueError("Deducted quantity must be greater than zero.")

        with transaction.atomic():
            stock = BranchStock.objects.select_for_update().get(pk=self.pk)
            applied_unit_cost = Decimal(str(unit_cost)) if unit_cost is not None else stock.average_cost

            stock.quantity -= qty
            resulted_in_neg = stock.quantity < 0
            stock.save(update_fields=['quantity', 'updated_at'])

            # Synchronize product.stock_quantity aggregate
            total_prod_qty = BranchStock.objects.filter(
                branch__business=stock.branch.business, product=stock.product
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
            Product.objects.filter(pk=stock.product_id).update(stock_quantity=total_prod_qty)

            ct = None
            obj_id = None
            ref_num = ''
            if reference_obj:
                ct = ContentType.objects.get_for_model(reference_obj)
                obj_id = str(reference_obj.pk)
                ref_num = getattr(
                    reference_obj, 'reference_number',
                    getattr(reference_obj, 'reference', getattr(reference_obj, 'invoice_number', str(reference_obj)))
                )

            term = terminal or getattr(reference_obj, 'terminal', None)
            idem = idempotency_key or getattr(reference_obj, 'idempotency_key', None)

            total_cost = (qty * applied_unit_cost).quantize(Decimal('0.01'))
            movement = StockMovement.objects.create(
                business=stock.branch.business,
                branch=stock.branch,
                product=stock.product,
                quantity_delta=-qty,
                unit_cost=applied_unit_cost,
                total_cost=total_cost,
                movement_type=movement_type,
                content_type=ct,
                object_id=obj_id,
                reference_number=ref_num,
                balance_after=stock.quantity,
                resulted_in_negative_stock=resulted_in_neg,
                performed_by=user,
                terminal=term,
                idempotency_key=idem,
                note=note,
            )

            self.quantity = stock.quantity
            return stock, movement


class StockMovement(models.Model):
    """
    Single append-only ledger tracking every inventory modification event.
    Acts as the single source of truth for stock reconciliations.
    """
    MOVEMENT_TYPE_CHOICES = [
        ('sale', 'Sale'),
        ('sale_return', 'Sale Return'),
        ('purchase_in', 'Purchase / GRN In'),
        ('supplier_return_out', 'Supplier Return Out'),
        ('hq_dispatch_out', 'HQ Dispatch Out'),
        ('branch_receipt_in', 'Branch Receipt In'),
        ('transfer_out', 'Transfer Out'),
        ('transfer_in', 'Transfer In'),
        ('in_transit_out', 'In Transit Out (Dispatched)'),
        ('transit_loss_writeoff', 'Transit Loss Write-off'),
        ('transit_return_in', 'Transit Return In'),
        ('manual_adjustment', 'Manual Adjustment'),
        ('damage_writeoff', 'Damage Write-off'),
        ('expiry_writeoff', 'Expiry Write-off'),
        ('initial_count', 'Initial Stock Count'),
    ]

    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='stock_movements'
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='stock_movements'
    )
    product = models.ForeignKey(
        'Product', on_delete=models.PROTECT, related_name='stock_movements'
    )
    quantity_delta = models.DecimalField(
        max_digits=10, decimal_places=3,
        help_text="Signed (+ for increase, - for decrease)"
    )
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    movement_type = models.CharField(max_length=30, choices=MOVEMENT_TYPE_CHOICES, db_index=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(max_length=64, null=True, blank=True)
    reference_document = GenericForeignKey('content_type', 'object_id')
    reference_number = models.CharField(max_length=100, blank=True, help_text="Human readable document number")

    balance_after = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    resulted_in_negative_stock = models.BooleanField(default=False)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements'
    )
    terminal = models.ForeignKey(
        'POSTerminal', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements'
    )
    idempotency_key = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['branch', 'product', '-created_at']),
            models.Index(fields=['movement_type', '-created_at']),
        ]

    @property
    def delta_quantity(self):
        return self.quantity_delta

    def __str__(self):
        sign = "+" if self.quantity_delta > 0 else ""
        return f"[{self.get_movement_type_display()}] {self.product.name} ({sign}{self.quantity_delta}) @ {self.branch.name}"


# ============================================================================
# HQ DISTRIBUTION & INTER-BRANCH TRANSFERS
# ============================================================================

class StockRequisition(models.Model):
    """
    Branch request for stock replenishment from HQ.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('dispatched', 'In Transit / Dispatched'),
        ('partially_fulfilled', 'Partially Fulfilled'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    ]

    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='stock_requisitions'
    )
    reference_number = models.CharField(max_length=30, unique=True, editable=False)
    requesting_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='requisitions_made'
    )
    requested_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='requisitions_requested'
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='requisitions_approved'
    )
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending', db_index=True)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['requesting_branch', 'status']),
        ]

    def __str__(self):
        return f"{self.reference_number} — {self.requesting_branch.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_number:
            from django.utils import timezone as tz
            today = tz.now().strftime('%Y%m%d')
            count = StockRequisition.objects.filter(business=self.business).count() + 1
            ref = f"REQ-{today}-{count:04d}"
            while StockRequisition.objects.filter(business=self.business, reference_number=ref).exists():
                count += 1
                ref = f"REQ-{today}-{count:04d}"
            self.reference_number = ref
        super().save(*args, **kwargs)


class StockRequisitionItem(models.Model):
    requisition = models.ForeignKey(
        StockRequisition, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        'Product', on_delete=models.PROTECT, related_name='requisition_items'
    )
    requested_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    approved_quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    dispatched_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    received_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.product.name} (Req: {self.requested_quantity}, Appr: {self.approved_quantity})"


class StockTransferRequest(models.Model):
    """
    Inter-branch transfer request between two non-HQ or peer branches.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('dispatched', 'In Transit / Dispatched'),
        ('receiving', 'Receiving in Progress'),
        ('partially_received', 'Partially Received'),
        ('discrepancy_flagged', 'Discrepancy Flagged'),
        ('resolved', 'Discrepancy Resolved'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='transfer_requests'
    )
    reference_number = models.CharField(max_length=30, unique=True, editable=False)
    source_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='transfer_requests_out'
    )
    destination_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='transfer_requests_in'
    )
    requested_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='transfers_requested'
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='transfers_approved'
    )
    reason = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending_approval', db_index=True)
    total_estimated_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    requires_approval = models.BooleanField(default=True)
    auto_approved = models.BooleanField(default=False)
    discrepancy_resolved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='transfers_discrepancy_resolved'
    )
    discrepancy_resolved_at = models.DateTimeField(null=True, blank=True)
    discrepancy_resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['source_branch', 'status']),
            models.Index(fields=['destination_branch', 'status']),
        ]

    def clean(self):
        super().clean()
        if self.source_branch_id and self.destination_branch_id and self.source_branch_id == self.destination_branch_id:
            raise ValidationError("Source branch and destination branch must be different.")

    def save(self, *args, **kwargs):
        self.clean()
        if not self.reference_number:
            from django.utils import timezone as tz
            today = tz.now().strftime('%Y%m%d')
            count = StockTransferRequest.objects.filter(business=self.business).count() + 1
            ref = f"TRF-{today}-{count:04d}"
            while StockTransferRequest.objects.filter(business=self.business, reference_number=ref).exists():
                count += 1
                ref = f"TRF-{today}-{count:04d}"
            self.reference_number = ref
        super().save(*args, **kwargs)


class StockTransferItem(models.Model):
    DISCREPANCY_RESOLUTION_CHOICES = [
        ('writeoff_loss', 'Write-off as Transit Loss'),
        ('returned_to_source', 'Return to Source Branch'),
        ('accepted_variance', 'Accepted Variance / Adjustment'),
    ]

    transfer_request = models.ForeignKey(
        StockTransferRequest, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        'Product', on_delete=models.PROTECT, related_name='transfer_items'
    )
    requested_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    approved_quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    dispatched_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    received_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    unit_cost_at_dispatch = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Moving avg unit cost at source branch when dispatched"
    )
    discrepancy_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    discrepancy_reason = models.TextField(blank=True)
    discrepancy_resolution = models.CharField(
        max_length=30, blank=True, choices=DISCREPANCY_RESOLUTION_CHOICES
    )
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.product.name} (Req: {self.requested_quantity})"


class TransferEvent(models.Model):
    """
    Immutable append-only audit trail capturing every status transition,
    decision, discrepancy flag, and resolution for StockTransfers and Dispatches.
    """
    EVENT_TYPE_CHOICES = [
        ('created', 'Created Draft / Request'),
        ('submitted', 'Submitted for Approval'),
        ('auto_approved', 'Auto-Approved by Rule'),
        ('approved', 'Approved by Authorizer'),
        ('rejected', 'Rejected'),
        ('dispatched', 'Dispatched / In Transit'),
        ('received_full', 'Fully Received'),
        ('received_partial', 'Partially Received (Discrepancy Flagged)'),
        ('discrepancy_resolved', 'Discrepancy Resolved'),
        ('cancelled', 'Cancelled'),
        ('note_added', 'Audit Note Added'),
    ]

    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='transfer_events'
    )
    transfer_request = models.ForeignKey(
        StockTransferRequest, null=True, blank=True, on_delete=models.CASCADE, related_name='events'
    )
    requisition = models.ForeignKey(
        'StockRequisition', null=True, blank=True, on_delete=models.CASCADE, related_name='events'
    )
    dispatch = models.ForeignKey(
        'Dispatch', null=True, blank=True, on_delete=models.CASCADE, related_name='events'
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES, db_index=True)
    performed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='transfer_events_performed'
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['transfer_request', 'created_at']),
            models.Index(fields=['dispatch', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.get_event_type_display()}] {self.from_status} -> {self.to_status} ({self.created_at})"


class TransferApprovalRule(models.Model):
    """
    Business-scoped configurable rules governing when inter-branch transfers
    can auto-approve vs require supervisor / HQ approval.
    """
    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='transfer_approval_rules'
    )
    name = models.CharField(max_length=100, default="Default Transfer Policy")
    is_active = models.BooleanField(default=True)
    auto_approve_below_threshold = models.BooleanField(
        default=False,
        help_text="If True, transfers with total value <= min_value_threshold auto-approve immediately"
    )
    min_value_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Transfers exceeding this monetary value require explicit manager approval"
    )
    min_quantity_threshold = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0.000'),
        help_text="Transfers exceeding this total unit count require explicit approval"
    )
    requires_hq_approval = models.BooleanField(
        default=False,
        help_text="If True, transfers require HQ admin sign-off even for peer branch transfers"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.business.name} - {self.name} (Active: {self.is_active})"


class Dispatch(models.Model):
    """
    Physical shipment record shared by both HQ Requisitions and Inter-Branch Transfers.
    Tracks in-transit goods, unit moving cost at shipment, and receipt discrepancies.
    """
    STATUS_CHOICES = [
        ('in_transit', 'In Transit'),
        ('partially_received', 'Partially Received'),
        ('received', 'Received / Completed'),
        ('cancelled', 'Cancelled'),
    ]

    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='dispatches'
    )
    reference_number = models.CharField(max_length=30, unique=True, editable=False)
    source_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='dispatches_out'
    )
    destination_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='dispatches_in'
    )
    requisition = models.ForeignKey(
        StockRequisition, null=True, blank=True, on_delete=models.SET_NULL, related_name='dispatches'
    )
    transfer_request = models.ForeignKey(
        StockTransferRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name='dispatches'
    )
    dispatched_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='dispatches_sent'
    )
    dispatched_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='dispatches_received'
    )
    received_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='in_transit', db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-dispatched_at']
        indexes = [
            models.Index(fields=['business', '-dispatched_at']),
            models.Index(fields=['source_branch', 'status']),
            models.Index(fields=['destination_branch', 'status']),
        ]

    def clean(self):
        super().clean()
        if self.requisition and self.transfer_request:
            raise ValidationError("A dispatch can link to a Requisition OR a Transfer Request, never both.")
        if not self.requisition and not self.transfer_request:
            raise ValidationError("A dispatch must link to either a Requisition or a Transfer Request.")
        if self.source_branch_id == self.destination_branch_id:
            raise ValidationError("Source and destination branch cannot be the same.")

    def save(self, *args, **kwargs):
        self.clean()
        if not self.reference_number:
            from django.utils import timezone as tz
            today = tz.now().strftime('%Y%m%d')
            count = Dispatch.objects.filter(
                business=self.business, dispatched_at__date=tz.now().date()
            ).count()
            self.reference_number = f"DSP-{today}-{count + 1:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference_number} ({self.source_branch.name} → {self.destination_branch.name}) [{self.get_status_display()}]"


class DispatchItem(models.Model):
    dispatch = models.ForeignKey(
        Dispatch, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        'Product', on_delete=models.PROTECT, related_name='dispatch_items'
    )
    dispatched_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        help_text="Moving avg unit cost at source branch at shipment time"
    )
    received_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    discrepancy_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    discrepancy_reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.product.name} (Dispatched: {self.dispatched_quantity}, Recv: {self.received_quantity})"


# Legacy StockTransfer model kept for backward compatibility
class StockTransfer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_transit', 'In Transit'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    business = models.ForeignKey(
        'Business', on_delete=models.CASCADE, related_name='stock_transfers'
    )
    reference = models.CharField(max_length=30, unique=True, editable=False)
    source_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='transfers_out'
    )
    destination_branch = models.ForeignKey(
        Branch, on_delete=models.PROTECT, related_name='transfers_in'
    )
    product = models.ForeignKey('Product', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note = models.TextField(blank=True)
    initiated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='initiated_transfers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['source_branch', 'status']),
            models.Index(fields=['destination_branch', 'status']),
        ]

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.reference:
            from django.utils import timezone as tz
            today = tz.now().strftime('%Y%m%d')
            count = StockTransfer.objects.filter(business=self.business).count() + 1
            ref = f"TRF-{today}-{count:04d}"
            while StockTransfer.objects.filter(business=self.business, reference=ref).exists():
                count += 1
                ref = f"TRF-{today}-{count:04d}"
            self.reference = ref
        super().save(*args, **kwargs)


class BranchPriceOverride(models.Model):
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name='price_overrides'
    )
    product = models.ForeignKey(
        'Product', on_delete=models.CASCADE, related_name='price_overrides'
    )
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['branch', 'product']]

    def __str__(self):
        return f"{self.product} @ {self.branch}: {self.price}"


# ============================================================================
# FRONT OFFICE TERMINAL & PIN LOGIN AUDIT MODELS
# ============================================================================

class POSTerminal(models.Model):
    """
    Represents a registered physical point-of-sale terminal/device within a branch.
    Enforces terminal-specific cashier sessions.
    """
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='terminals')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='terminals')
    name = models.CharField(max_length=100, help_text="Terminal display name (e.g. Counter 1)")
    terminal_code = models.CharField(max_length=50, help_text="Unique terminal code (e.g. TERM-01)")
    device_token = models.CharField(max_length=128, unique=True, db_index=True, help_text="Unique device cookie / token identifier")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    allowed_cashiers = models.ManyToManyField(
        User, blank=True, related_name='assigned_terminals',
        help_text="Optional: restrict to specific cashiers. If empty, any cashier assigned to this branch can log in."
    )

    # Terminal-Specific KRA Control Unit (for physical ESDs attached per-counter)
    cu_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="Override CU Number for this terminal if using dedicated physical ESD"
    )
    cu_serial_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Override CU Serial Number for this terminal"
    )
    tims_middleware_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Override TIMS Middleware URL for this terminal"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    last_active_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp of last successful bidirectional sync")
    sync_status = models.CharField(
        max_length=20,
        default='idle',
        choices=[
            ('idle', 'Idle'),
            ('syncing', 'Syncing'),
            ('synced', 'Synced'),
            ('error', 'Error'),
        ],
        help_text="Current or last known sync status"
    )

    OPERATIONAL_STATUS_CHOICES = [
        ('available', 'Available'),
        ('in_use', 'In Use'),
        ('offline', 'Offline'),
        ('maintenance', 'Maintenance'),
    ]
    operational_status = models.CharField(
        max_length=20,
        default='available',
        choices=OPERATIONAL_STATUS_CHOICES,
        help_text="Real-time till operational status"
    )

    class Meta:
        unique_together = [['business', 'terminal_code']]
        ordering = ['branch', 'terminal_code']
        indexes = [
            models.Index(fields=['business', 'device_token']),
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['branch', 'operational_status']),
        ]

    def __str__(self):
        return f"{self.name} ({self.terminal_code}) — {self.branch.name}"

    @property
    def current_active_assignment(self):
        """Returns currently active CashierTillAssignment if any."""
        return self.till_assignments.filter(status='active').select_related('cashier', 'branch').first()

    def get_status_display_badge(self):
        active = self.current_active_assignment
        if not self.is_active or self.operational_status == 'offline':
            return {'status': 'offline', 'label': 'Offline', 'badge_class': 'bg-secondary'}
        if self.operational_status == 'maintenance':
            return {'status': 'maintenance', 'label': 'Maintenance', 'badge_class': 'bg-warning text-dark'}
        if active:
            cashier_name = active.cashier.get_full_name() or active.cashier.username
            return {'status': 'in_use', 'label': f'In Use ({cashier_name})', 'badge_class': 'bg-success', 'cashier': cashier_name}
        return {'status': 'available', 'label': 'Available', 'badge_class': 'bg-primary'}

    def can_cashier_login(self, user):
        """Check if user is allowed to log into this terminal."""
        if not self.is_active:
            return False, "Terminal is inactive"
        if self.branch and not self.branch.is_active:
            return False, "Branch is inactive"
        if self.allowed_cashiers.exists() and not self.allowed_cashiers.filter(pk=user.pk).exists():
            return False, "User not authorized for this specific terminal"
        has_branch_access = (
            user.is_superuser
            or user.is_staff
            or not self.branch
            or BranchMembership.objects.filter(user=user, branch=self.branch, is_active=True).exists()
            or not BranchMembership.objects.filter(user=user, is_active=True).exists()
        )
        if not has_branch_access:
            return False, "User not assigned to this branch"
        return True, ""


class PINLoginAuditLog(models.Model):
    """
    Audit log tracking all PIN login attempts, terminal sessions, and access events.
    """
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed_pin', 'Incorrect PIN'),
        ('locked_out', 'Account Locked'),
        ('invalid_terminal', 'Invalid / Unregistered Terminal'),
        ('terminal_inactive', 'Terminal Inactive'),
        ('no_pin_set', 'No PIN Configured'),
        ('unauthorized_branch', 'Unauthorized Branch'),
        ('session_closed', 'Session Closed'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='pin_audit_logs')
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL, related_name='pin_audit_logs')
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='pin_audit_logs')
    employee_id = models.CharField(max_length=50, blank=True)
    terminal = models.ForeignKey(POSTerminal, null=True, blank=True, on_delete=models.SET_NULL, related_name='pin_audit_logs')
    terminal_code = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, db_index=True)
    failure_reason = models.TextField(blank=True)
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', '-created_at']),
            models.Index(fields=['branch', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.employee_id or (self.user.username if self.user else 'Unknown')} @ {self.terminal_code or 'Unknown'} ({self.created_at:%Y-%m-%d %H:%M})"


# ============================================================================
# CASHIER TILL ASSIGNMENT & CROSS-BRANCH TRANSFER SYSTEM
# ============================================================================

class CashierTillAssignment(models.Model):
    """
    Assignment of a cashier to a specific till / terminal for a scheduled shift window.
    Enforces that a till has only one active cashier and a cashier has only one active till.
    """
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('active', 'Active (Shift In Progress)'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='cashier_assignments')
    cashier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='till_assignments')
    terminal = models.ForeignKey(POSTerminal, on_delete=models.CASCADE, related_name='till_assignments')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='till_assignments')
    
    shift_start = models.DateTimeField(db_index=True, help_text="Scheduled shift start time")
    shift_end = models.DateTimeField(db_index=True, help_text="Scheduled shift end time")
    actual_start = models.DateTimeField(null=True, blank=True, help_text="Timestamp when cashier clocked in / opened till")
    actual_end = models.DateTimeField(null=True, blank=True, help_text="Timestamp when cashier clocked out / released till")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled', db_index=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Hourly labor rate in KES")
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_shifts')
    notes = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-shift_start']
        indexes = [
            models.Index(fields=['business', 'branch', 'status']),
            models.Index(fields=['cashier', 'status', 'shift_start']),
            models.Index(fields=['terminal', 'status', 'shift_start']),
        ]

    def __str__(self):
        return f"{self.cashier.username} @ {self.terminal.terminal_code} ({self.shift_start:%Y-%m-%d %H:%M} - {self.shift_end:%H:%M}) [{self.get_status_display()}]"

    def calculate_hours_worked(self):
        """Calculate duration worked in hours (decimal). Uses actual duration if available, else scheduled."""
        if self.actual_start and self.actual_end:
            duration = self.actual_end - self.actual_start
        elif self.actual_start and self.status == 'active':
            duration = timezone.now() - self.actual_start
        else:
            duration = self.shift_end - self.shift_start
        return max(Decimal('0.00'), Decimal(str(round(duration.total_seconds() / 3600.0, 2))))

    def calculate_labor_cost(self):
        """Returns labor cost = hours worked * hourly rate"""
        return round(self.calculate_hours_worked() * self.hourly_rate, 2)


class CashierTransferRequest(models.Model):
    """
    Cross-branch transfer request for cashiers.
    Supports permanent and temporary transfers with start and optional end dates.
    Requires approval from the receiving branch's manager before taking effect.
    """
    TYPE_CHOICES = [
        ('permanent', 'Permanent Transfer'),
        ('temporary', 'Temporary Transfer'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='cashier_transfers')
    cashier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cashier_transfers')
    from_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cashier_transfers_out')
    to_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cashier_transfers_in')
    transfer_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='temporary')
    
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True, help_text="End date required for temporary transfers")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requested_cashier_transfers')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_cashier_transfers')
    action_date = models.DateTimeField(null=True, blank=True)
    
    reason = models.TextField(help_text="Reason for transfer")
    rejection_reason = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['to_branch', 'status']),
            models.Index(fields=['from_branch', 'status']),
            models.Index(fields=['cashier', 'status']),
        ]

    def __str__(self):
        return f"{self.get_transfer_type_display()} of {self.cashier.username}: {self.from_branch.code} → {self.to_branch.code} [{self.get_status_display()}]"

    def is_active_for_date(self, target_date=None):
        """Check if this approved transfer is active on a specific date (defaults to today)."""
        if self.status != 'approved':
            return False
        if target_date is None:
            target_date = timezone.localdate()
        if self.transfer_type == 'permanent':
            return target_date >= self.start_date
        # Temporary transfer
        if self.end_date:
            return self.start_date <= target_date <= self.end_date
        return target_date >= self.start_date


class CashierAssignmentAuditLog(models.Model):
    """
    Audit log capturing every transfer and assignment change with timestamp, approver, and reason.
    """
    ACTION_CHOICES = [
        ('transfer_requested', 'Transfer Requested'),
        ('transfer_approved', 'Transfer Approved'),
        ('transfer_rejected', 'Transfer Rejected'),
        ('transfer_cancelled', 'Transfer Cancelled'),
        ('transfer_expired', 'Temporary Transfer Expired (Reverted)'),
        ('till_assigned', 'Till Scheduled / Assigned'),
        ('till_activated', 'Till Activated (Shift Started)'),
        ('till_released', 'Till Released (Shift Ended)'),
        ('conflict_prevented', 'Schedule Conflict Prevented'),
    ]

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='assignment_audit_logs')
    cashier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignment_audit_logs')
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='performed_assignment_audits')
    from_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    to_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    terminal = models.ForeignKey(POSTerminal, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    assignment = models.ForeignKey(CashierTillAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    transfer_request = models.ForeignKey(CashierTransferRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    reason = models.TextField(blank=True, default='')
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['business', '-timestamp']),
            models.Index(fields=['cashier', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        return f"[{self.get_action_display()}] {self.cashier.username} by {self.performed_by.username if self.performed_by else 'System'} ({self.timestamp:%Y-%m-%d %H:%M})"


# ==================== BANK ACCOUNTS & RECONCILIATION ====================

class BankAccount(CacheInvalidationMixin, AuditModelMixin, models.Model):
    """
    Commercial bank accounts or digital treasury accounts belonging to a business.
    """
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='bank_accounts'
    )
    bank_name = models.CharField(
        max_length=100,
        help_text="e.g. KCB Bank, Equity Bank, Co-operative Bank, Absa, MPESA Paybill/Till"
    )
    account_name = models.CharField(
        max_length=150,
        help_text="e.g. Main Operations Account, CBD Collection Till Account"
    )
    account_number = models.CharField(
        max_length=60,
        help_text="Bank Account Number or Paybill/Till Number"
    )
    branch_name = models.CharField(max_length=100, blank=True, help_text="Bank branch / location")
    currency = models.CharField(max_length=10, default='KES')
    opening_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Initial ledger balance before tracking in system"
    )
    current_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Current calculated book balance"
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Default bank account pre-selected for physical deposits"
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'bank_name', 'account_name']
        unique_together = [['business', 'account_number']]
        indexes = [
            models.Index(fields=['business', 'is_active']),
        ]

    def __str__(self):
        return f"{self.bank_name} - {self.account_name} ({self.account_number})"

    def save(self, *args, **kwargs):
        if self.is_default:
            BankAccount.objects.filter(
                business=self.business, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class BankingRecord(models.Model):
    """
    Physical cash/cheque deposit record created by a cashier/supervisor
    documenting cash taken from POS registers and deposited into the bank.
    """
    PAYMENT_TYPE_CHOICES = [
        ('cash', 'Cash Deposit'),
        ('cheque', 'Cheque Deposit'),
        ('mixed', 'Mixed (Cash & Cheque)'),
        ('card_settlement', 'Card Batch Settlement (PDQ)'),
        ('mobile_money', 'Mobile Money Sweeping / Till Bank Transfer'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending / In Transit'),
        ('banked', 'Banked (Awaiting Statement Match)'),
        ('matched', 'Matched & Reconciled'),
        ('discrepancy', 'Discrepancy Flagged'),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='banking_records'
    )
    record_number = models.CharField(max_length=30, unique=True, editable=False, db_index=True)
    branch = models.ForeignKey(
        Branch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='banking_records',
        help_text="Specific branch source (leave blank for central consolidated banking)"
    )
    terminal = models.ForeignKey(
        POSTerminal, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='banking_records',
        help_text="Specific till / register if banked by terminal"
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='banking_records'
    )
    period_start = models.DateField(help_text="Collection period start date")
    period_end = models.DateField(help_text="Collection period end date")
    
    # Financial fields
    expected_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="System-calculated collections due to be banked"
    )
    deposited_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Actual physical amount on the bank deposit slip"
    )
    variance_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="deposited_amount - expected_amount (Negative = Short-banked, Positive = Over-banked)"
    )
    
    payment_type = models.CharField(max_length=25, choices=PAYMENT_TYPE_CHOICES, default='cash')
    deposit_reference = models.CharField(
        max_length=100,
        help_text="Bank deposit slip number, transaction reference, or teller code"
    )
    deposit_date = models.DateField(help_text="Date physically banked at the bank", db_index=True)
    deposited_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='banking_deposits_made',
        help_text="Cashier or supervisor who performed the bank run"
    )
    slip_image = models.FileField(
        upload_to='banking/slips/%Y/%m/', null=True, blank=True,
        help_text="Photo / scan of bank deposit slip or confirmation receipt"
    )
    
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='banked', db_index=True
    )
    variance_reason = models.TextField(blank=True, help_text="Mandatory explanation if variance exceeds threshold")
    notes = models.TextField(blank=True)
    
    # Audit & Reconciled By
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    reconciled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='banking_records_reconciled'
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-deposit_date', '-created_at']
        indexes = [
            models.Index(fields=['business', '-deposit_date']),
            models.Index(fields=['business', 'status']),
            models.Index(fields=['bank_account', 'status']),
        ]

    def __str__(self):
        return f"{self.record_number} — {self.bank_account.bank_name} ({self.deposit_date}): KES {self.deposited_amount:,.2f}"

    def clean(self):
        super().clean()
        if self.deposited_amount is not None and self.expected_amount is not None:
            self.variance_amount = self.deposited_amount - self.expected_amount

    def save(self, *args, **kwargs):
        if self.deposited_amount is not None and self.expected_amount is not None:
            self.variance_amount = self.deposited_amount - self.expected_amount
            
        if not self.record_number:
            from django.utils import timezone as tz
            today_str = tz.now().strftime('%Y%m%d')
            count = BankingRecord.objects.filter(business=self.business).count() + 1
            ref = f"BNK-{today_str}-{count:04d}"
            while BankingRecord.objects.filter(business=self.business, record_number=ref).exists():
                count += 1
                ref = f"BNK-{today_str}-{count:04d}"
            self.record_number = ref
        super().save(*args, **kwargs)


class BankStatementImportBatch(models.Model):
    """
    Tracks an imported bank statement file or manual entry batch.
    """
    FORMAT_CHOICES = [
        ('csv', 'CSV Spreadsheet'),
        ('ofx', 'OFX / QBO File'),
        ('manual', 'Manual Entry Batch'),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='statement_import_batches'
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='statement_batches'
    )
    batch_number = models.CharField(max_length=30, unique=True, editable=False)
    import_file = models.FileField(upload_to='banking/statements/%Y/%m/', null=True, blank=True)
    file_format = models.CharField(max_length=15, choices=FORMAT_CHOICES, default='csv')
    
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    closing_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    statement_start_date = models.DateField(null=True, blank=True)
    statement_end_date = models.DateField(null=True, blank=True)
    
    total_lines = models.IntegerField(default=0)
    matched_lines = models.IntegerField(default=0)
    total_credits = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_debits = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    
    imported_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='statement_imports'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.batch_number} — {self.bank_account.bank_name} ({self.created_at:%Y-%m-%d})"

    def save(self, *args, **kwargs):
        if not self.batch_number:
            from django.utils import timezone as tz
            today_str = tz.now().strftime('%Y%m%d')
            count = BankStatementImportBatch.objects.filter(business=self.business).count() + 1
            ref = f"STMT-{today_str}-{count:04d}"
            while BankStatementImportBatch.objects.filter(business=self.business, batch_number=ref).exists():
                count += 1
                ref = f"STMT-{today_str}-{count:04d}"
            self.batch_number = ref
        super().save(*args, **kwargs)


class BankStatementLine(models.Model):
    """
    Individual transaction line extracted from an official bank statement.
    """
    LINE_TYPE_CHOICES = [
        ('credit', 'Deposit / Credit (+)'),
        ('debit', 'Withdrawal / Fee / Debit (-)'),
    ]

    STATUS_CHOICES = [
        ('unmatched', 'Unmatched'),
        ('matched', 'Matched & Reconciled'),
        ('ignored', 'Ignored / Non-POS Item'),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='statement_lines'
    )
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='statement_lines'
    )
    batch = models.ForeignKey(
        BankStatementImportBatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lines'
    )
    transaction_date = models.DateField(db_index=True)
    value_date = models.DateField(null=True, blank=True)
    line_type = models.CharField(max_length=10, choices=LINE_TYPE_CHOICES, default='credit')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='unmatched', db_index=True)
    matched_banking_record = models.ForeignKey(
        BankingRecord, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='matched_statement_lines'
    )
    matched_supplier_payment = models.ForeignKey(
        'SupplierPayment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='matched_statement_lines'
    )
    matched_supplier_refund = models.ForeignKey(
        'SupplierRefund', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='matched_statement_lines'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transaction_date', '-id']
        indexes = [
            models.Index(fields=['business', 'bank_account', 'status']),
            models.Index(fields=['transaction_date', 'status']),
        ]

    def __str__(self):
        sign = "+" if self.line_type == 'credit' else "-"
        return f"[{self.transaction_date}] {sign}KES {self.amount:,.2f} — {self.description[:40]}"


class ReconciliationMatch(models.Model):
    """
    Formal reconciliation junction linking one or more physical banking records,
    supplier payments, or supplier refunds to one or more bank statement lines.
    """
    MATCH_TYPE_CHOICES = [
        ('one_to_one', '1-to-1 Match'),
        ('many_to_one', 'Combined Records to 1 Statement Line'),
        ('one_to_many', '1 Record Split to Multiple Statement Lines'),
        ('with_fee', 'Match with Bank Fee / Charge Deduction'),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='reconciliation_matches'
    )
    match_number = models.CharField(max_length=30, unique=True, editable=False)
    match_type = models.CharField(max_length=20, choices=MATCH_TYPE_CHOICES, default='one_to_one')
    
    banking_records = models.ManyToManyField(
        BankingRecord, blank=True, related_name='reconciliation_matches'
    )
    supplier_payments = models.ManyToManyField(
        'SupplierPayment', blank=True, related_name='reconciliation_matches'
    )
    supplier_refunds = models.ManyToManyField(
        'SupplierRefund', blank=True, related_name='reconciliation_matches'
    )
    statement_lines = models.ManyToManyField(
        BankStatementLine, related_name='reconciliation_matches'
    )
    
    total_banked_amount = models.DecimalField(max_digits=14, decimal_places=2)
    total_statement_amount = models.DecimalField(max_digits=14, decimal_places=2)
    bank_charge_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text="Bank transaction fees or excise deducted from deposit"
    )
    variance_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    
    matched_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='reconciliations_performed'
    )
    matched_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-matched_at']

    def __str__(self):
        return f"{self.match_number} ({self.get_match_type_display()}): Banked KES {self.total_banked_amount:,.2f} = Statement KES {self.total_statement_amount:,.2f}"

    def save(self, *args, **kwargs):
        if not self.match_number:
            from django.utils import timezone as tz
            today_str = tz.now().strftime('%Y%m%d')
            count = ReconciliationMatch.objects.filter(business=self.business).count() + 1
            ref = f"REC-{today_str}-{count:04d}"
            while ReconciliationMatch.objects.filter(business=self.business, match_number=ref).exists():
                count += 1
                ref = f"REC-{today_str}-{count:04d}"
            self.match_number = ref
        super().save(*args, **kwargs)


class BankingAuditLog(models.Model):
    """
    Immutable audit log recording every creation, edit, status change, and reconciliation event.
    """
    ACTION_CHOICES = [
        ('record_created', 'Banking Record Created'),
        ('record_updated', 'Banking Record Details Updated'),
        ('slip_uploaded', 'Deposit Slip Uploaded'),
        ('statement_imported', 'Bank Statement Imported'),
        ('manual_line_added', 'Manual Statement Line Added'),
        ('auto_matched', 'Auto-Matched to Statement Line'),
        ('manual_matched', 'Manually Reconciled'),
        ('unmatched', 'Reconciliation Unmatched / Reverted'),
        ('line_ignored', 'Statement Line Marked as Ignored'),
        ('discrepancy_flagged', 'Variance Discrepancy Flagged'),
        ('discrepancy_resolved', 'Discrepancy Resolved with Note'),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='banking_audit_logs'
    )
    banking_record = models.ForeignKey(
        BankingRecord, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs'
    )
    statement_line = models.ForeignKey(
        BankStatementLine, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs'
    )
    reconciliation_match = models.ForeignKey(
        ReconciliationMatch, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['business', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        user_str = self.performed_by.username if self.performed_by else 'System'
        return f"[{self.get_action_display()}] by {user_str} ({self.timestamp:%Y-%m-%d %H:%M})"


# ==================== CASH PICKUP / TILL DROP ====================

class CashPickup(models.Model):
    """
    Cash Pickup / Till Drop / Safe Drop / Cash Lift entity.
    Enforces dual-custody cash removal from active POS registers during shifts,
    reducing robbery exposure and creating an immutable custody trail
    from Till -> Safe -> Bank Deposit -> Bank Statement Match.
    """
    REASON_CHOICES = [
        ('threshold_exceeded', 'Drawer Threshold Exceeded'),
        ('scheduled', 'Scheduled Cash Lift'),
        ('end_of_shift', 'End of Shift Drop'),
        ('count_dispute', 'Count Dispute / Safety Lift'),
        ('other', 'Other Reason'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed & Locked'),
        ('in_safe', 'Transferred to Safe'),
        ('banked', 'Banked in Deposit'),
        ('disputed', 'Disputed Count'),
        ('cancelled', 'Cancelled'),
    ]

    WITNESS_CHOICES = [
        ('supervisor', 'Supervisor / Manager'),
        ('peer_cashier', 'Peer Cashier (Witness Fallback)'),
    ]

    TENDER_CHOICES = [
        ('cash', 'Cash (Banknotes/Coins)'),
        ('cheque', 'Cheques'),
        ('foreign_currency', 'Foreign Currency'),
        ('mixed', 'Mixed Tenders'),
    ]

    pickup_number = models.CharField(
        max_length=30, unique=True, editable=False, db_index=True,
        help_text="Format: PKU-YYYYMMDD-XXXX"
    )
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='cash_pickups'
    )
    branch = models.ForeignKey(
        'Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_pickups'
    )
    terminal = models.ForeignKey(
        'POSTerminal', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_pickups'
    )
    session = models.ForeignKey(
        'POSSession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_pickups'
    )
    shift = models.ForeignKey(
        'Shift', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_pickups'
    )

    # Dual Custody Actors
    cashier = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='initiated_cash_pickups',
        help_text="Cashier operating the till"
    )
    supervisor = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='authorized_cash_pickups',
        help_text="Supervisor / manager who witnessed and authorized count"
    )
    witness_type = models.CharField(
        max_length=20, choices=WITNESS_CHOICES, default='supervisor'
    )

    # Financials
    tender_type = models.CharField(
        max_length=20, choices=TENDER_CHOICES, default='cash'
    )
    currency = models.CharField(max_length=10, default='KES')
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    pickup_reference = models.CharField(
        max_length=100,
        help_text="Bag number, tamper envelope barcode, or slip ID"
    )
    pickup_time = models.DateTimeField(default=timezone.now, db_index=True)
    reason = models.CharField(
        max_length=30, choices=REASON_CHOICES, default='threshold_exceeded'
    )

    # Authentication Timestamps
    cashier_confirmed_at = models.DateTimeField(null=True, blank=True)
    supervisor_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Lifecycle & Linking
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='confirmed', db_index=True
    )
    banking_record = models.ForeignKey(
        BankingRecord, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_pickups',
        help_text="Physical bank deposit record this pickup was rolled into"
    )

    # Immutability & Audit
    is_locked = models.BooleanField(
        default=True,
        help_text="Locked after confirmation; amendments require manager override"
    )
    override_reason = models.TextField(blank=True)
    override_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pickup_overrides'
    )
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-pickup_time', '-created_at']
        indexes = [
            models.Index(fields=['business', 'status', '-pickup_time']),
            models.Index(fields=['business', 'branch', '-pickup_time']),
            models.Index(fields=['session', 'status']),
        ]

    def __str__(self):
        return f"{self.pickup_number} - {self.currency} {self.amount} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.pickup_number:
            today = timezone.localdate()
            prefix = f"PKU-{today.strftime('%Y%m%d')}"
            last = CashPickup.objects.filter(
                business=self.business,
                pickup_number__startswith=prefix
            ).order_by('-pickup_number').first()
            if last:
                try:
                    last_seq = int(last.pickup_number.split('-')[-1])
                    seq = last_seq + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            self.pickup_number = f"{prefix}-{seq:04d}"

        if not self.cashier_confirmed_at:
            self.cashier_confirmed_at = timezone.now()
        if not self.supervisor_confirmed_at:
            self.supervisor_confirmed_at = timezone.now()

        super().save(*args, **kwargs)


# ==================== CASH PAID-OUT / TILL EXPENSES ====================

class CashPaidOut(CacheInvalidationMixin, AuditModelMixin, models.Model):
    """
    Cash Paid-Out / Till Expenses / Petty Cash Out.
    Tracks cash disbursed directly from the till drawer (or petty cash fund) for immediate
    operational expenses (fuel, stationery, courier, repairs, staff welfare).
    Enforces category thresholds, dual custody, post-payout receipt tracking, informal vendor
    exception sign-offs, and reversal audit trails.
    """
    STATUS_CHOICES = [
        ('pending_approval', 'Pending Approval'),
        ('paid_pending_receipt', 'Paid - Pending Receipt'),
        ('confirmed', 'Confirmed (Receipt Attached / Exception Signed)'),
        ('rejected', 'Rejected'),
        ('reversed', 'Reversed (Cash Returned)'),
        ('written_off', 'Written Off (Lost Receipt Loss)'),
    ]

    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='cash_paid_outs'
    )
    paid_out_number = models.CharField(
        max_length=30, editable=False, db_index=True,
        help_text="Format: POUT-YYYYMMDD-XXXX"
    )

    # Location & Register Origin
    branch = models.ForeignKey(
        'Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_paid_outs'
    )
    terminal = models.ForeignKey(
        'POSTerminal', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_paid_outs'
    )
    session = models.ForeignKey(
        'POSSession', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_paid_outs'
    )
    shift = models.ForeignKey(
        'Shift', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cash_paid_outs'
    )
    is_petty_cash_fund = models.BooleanField(
        default=False,
        help_text="True if disbursed from a standalone petty cash float instead of active till register"
    )

    # Actors
    requested_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='requested_paid_outs',
        help_text="Staff member or cashier who requested the cash"
    )
    authorized_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='authorized_paid_outs',
        help_text="Supervisor/Manager who approved the payout"
    )

    # Financials & Categorization
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    currency = models.CharField(max_length=10, default='KES')
    category = models.ForeignKey(
        'ExpenseCategory', on_delete=models.PROTECT, related_name='paid_outs',
        help_text="Expense category linking to chart of accounts"
    )
    payee = models.CharField(
        max_length=200,
        help_text="Vendor, courier, or individual the cash was given to"
    )
    description = models.TextField(
        help_text="Purpose of expense / goods or services acquired"
    )

    # Receipt Workflow
    receipt_reference = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Invoice / receipt / slip number once collected"
    )
    receipt_attachment = models.FileField(
        upload_to='paid_outs/receipts/%Y/%m/', blank=True, null=True,
        help_text="Photo or scan of vendor receipt"
    )
    receipt_due_by = models.DateTimeField(
        null=True, blank=True,
        help_text="Deadline for returning receipt (defaults to shift close / end of day)"
    )
    receipt_received_at = models.DateTimeField(null=True, blank=True)

    # Informal Vendor Exception Note
    has_receipt_exception = models.BooleanField(
        default=False,
        help_text="True if manager signed an exception note for informal vendor with no receipt"
    )
    exception_reason = models.TextField(blank=True, default='')
    exception_approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_receipt_exceptions'
    )

    # Status & General Ledger Linkage
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default='paid_pending_receipt', db_index=True
    )
    paid_out_time = models.DateTimeField(default=timezone.now, db_index=True)
    expense_entry = models.ForeignKey(
        'Expense', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='paid_out_source',
        help_text="Linked General Ledger Expense entry created upon receipt/exception confirmation"
    )

    # Reversal Handling
    is_reversed = models.BooleanField(default=False)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reversed_paid_outs'
    )
    reversal_reason = models.TextField(blank=True, default='')

    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-paid_out_time', '-created_at']
        indexes = [
            models.Index(fields=['business', 'status', '-paid_out_time']),
            models.Index(fields=['business', 'branch', '-paid_out_time']),
            models.Index(fields=['session', 'status']),
            models.Index(fields=['category', '-paid_out_time']),
        ]

    def __str__(self):
        return f"{self.paid_out_number} - {self.currency} {self.amount:.2f} ({self.category.name}) - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.paid_out_number:
            today = timezone.localdate()
            prefix = f"POUT-{today.strftime('%Y%m%d')}"
            last = CashPaidOut.objects.filter(
                business=self.business,
                paid_out_number__startswith=prefix
            ).order_by('-paid_out_number').first()
            if last:
                try:
                    last_seq = int(last.paid_out_number.split('-')[-1])
                    seq = last_seq + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1
            self.paid_out_number = f"{prefix}-{seq:04d}"

        if not self.receipt_due_by and self.paid_out_time:
            local_dt = timezone.localtime(self.paid_out_time)
            self.receipt_due_by = local_dt.replace(hour=23, minute=59, second=59)

        super().save(*args, **kwargs)



