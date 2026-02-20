from django.db import models
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from .image_utils import ImageOptimizer, generate_upload_path


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
            name='CASH',
            defaults={
                'is_active': True,
                'requires_reference': False,
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

    # Timestamps
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'business')
        ordering = ['business', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.business.name} ({self.role})"

    def has_permission(self, permission):
        """Check if user has specific permission in this business"""
        role_permissions = {
            'owner': ['all'],
            'admin': ['all'],
            'manager': ['view', 'create', 'edit', 'reports', 'users'],
            'stock_manager': ['view', 'create', 'edit', 'stock'],
            'cashier': ['view', 'create', 'pos'],
            'sales': ['view', 'create', 'pos'],
            'viewer': ['view'],
        }

        perms = role_permissions.get(self.role, [])
        return 'all' in perms or permission in perms


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


class Category(models.Model):
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


class Product(models.Model):
    """Products available for sale"""
    TAX_CLASS_CHOICES = [
        ('standard', 'Standard (16% VAT)'),
        ('zero_rated', 'Zero Rated (0% VAT)'),
        ('exempt', 'Exempt (No VAT)'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    product_code = models.CharField(max_length=50, blank=True, null=True, help_text="Internal product code or SKU")
    barcode = models.CharField(max_length=100, blank=True, help_text="Barcode for scanning (EAN, UPC, etc.)")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    unit = models.ForeignKey(UnitOfMeasurement, on_delete=models.SET_NULL, null=True, blank=True, 
                            related_name='products', help_text="Unit of measurement (e.g., kg, L, pcs)")
    cost_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Cost price (what you pay to stock the product) - REQUIRED"
    )
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Selling price (what customers pay)")
    tax_class = models.CharField(max_length=20, choices=TAX_CLASS_CHOICES, default='standard', help_text="Tax classification for this product")
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=0, help_text="Current stock quantity")
    low_stock_threshold = models.DecimalField(max_digits=10, decimal_places=3, default=10, help_text="Alert when stock falls below this level")
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['business', 'product_code']]
        ordering = ['name']

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
        
        # Optimize image on upload (with error handling for missing files)
        if self.image and hasattr(self.image, 'file'):
            try:
                # Validate image
                is_valid, error = ImageOptimizer.validate_image(self.image)
                if not is_valid:
                    raise ValueError(error)
                
                # Optimize image
                self.image = ImageOptimizer.optimize_image(self.image)
            except (FileNotFoundError, IOError, OSError):
                # Image file doesn't exist (e.g., on Heroku ephemeral filesystem)
                # Skip optimization and continue
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
    
    def is_low_stock(self):
        """Check if product is low on stock"""
        return self.stock_quantity <= self.low_stock_threshold
    
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


class Sale(models.Model):
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
    
    # Promotion tracking
    promotion = models.ForeignKey('Promotion', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Shift tracking
    shift = models.ForeignKey('Shift', on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        unique_together = [['business', 'invoice_number']]

    def __str__(self):
        return f"Invoice {self.invoice_number} - KES {self.total}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number: INV-YYYYMMDD-XXXX
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_sale = Sale.objects.filter(business=self.business, invoice_number__startswith=f'INV-{date_str}').order_by('-invoice_number').first()
            if last_sale:
                last_num = int(last_sale.invoice_number.split('-')[-1])
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
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    
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


class StockAdjustment(models.Model):
    """Track stock adjustments and changes"""
    ADJUSTMENT_TYPES = [
        ('restock', 'Restock'),
        ('damage', 'Damage/Loss'),
        ('return', 'Customer Return'),
        ('correction', 'Stock Correction'),
        ('sale', 'Sale'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='stock_adjustments')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_adjustments')
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)
    quantity_change = models.IntegerField(help_text="Positive for additions, negative for deductions")
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
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
        for purchase in self.purchases.filter(status='received'):
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
        """Calculate current outstanding balance based on actual received amounts"""
        # Calculate total based on actual received quantities
        total_purchases = Decimal('0.00')
        for purchase in self.purchases.filter(status='received'):
            # Calculate actual received amount
            actual_amount = Decimal('0.00')
            for item in purchase.items.all():
                # Use quantity_received if available, otherwise use ordered quantity
                qty = item.quantity_received if item.quantity_received > 0 else item.quantity
                actual_amount += Decimal(qty) * item.unit_cost
            
            # If no items or all zero, fall back to total_amount
            if actual_amount == Decimal('0.00'):
                actual_amount = purchase.total_amount
            
            total_purchases += actual_amount
        
        total_payments = self.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        return total_purchases - total_payments
    
    def total_payments(self):
        """Calculate total payments made to this supplier"""
        return self.payments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')


class Purchase(models.Model):
    """Purchase orders from suppliers"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('ordered', 'Ordered'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='purchases')
    purchase_number = models.CharField(max_length=20, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchases')
    date = models.DateTimeField(default=timezone.now)
    expected_delivery = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    received_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
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
        if self.status == 'received':
            return False
        
        self.status = 'received'
        self.received_date = timezone.now()
        self.save()
        
        # Update stock for all items
        for item in self.items.all():
            # Get receiving data for this item if provided
            item_data = None
            if receiving_data and 'items' in receiving_data:
                item_data = next(
                    (d for d in receiving_data['items'] if d['item_id'] == item.id),
                    None
                )
            
            if item_data:
                # Use actual received quantities
                qty_received = item_data['quantity_received']
                qty_damaged = item_data['quantity_damaged']
                notes = item_data.get('notes', '')
                expiry_date = item_data.get('expiry_date')
                batch_number = item_data.get('batch_number', '')
                
                # Get product reference first
                product = item.product
                
                # Update item receiving details
                item.quantity_received = qty_received
                item.quantity_damaged = qty_damaged
                item.receiving_notes = notes
                
                # Update expiry and batch if provided
                if expiry_date:
                    from datetime import datetime
                    try:
                        expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                        item.expiry_date = expiry_date_obj
                        
                        # Also update the product's expiry date
                        product.expiry_date = expiry_date_obj
                        # Set default alert days to 7 if not already customized
                        if product.expiry_alert_days <= 3:  # If using old default or less
                            product.expiry_alert_days = 7
                    except ValueError:
                        pass  # Invalid date format, skip
                
                if batch_number:
                    item.batch_number = batch_number
                
                item.save()
                
                # Update stock with received quantity only
                previous_qty = product.stock_quantity
                product.stock_quantity += Decimal(qty_received)
                # Save product with all changes (stock + expiry if set)
                product.save(update_fields=['stock_quantity', 'expiry_date', 'expiry_alert_days'])
                
                # Create restock adjustment
                StockAdjustment.objects.create(
                    business=self.business,
                    product=product,
                    adjustment_type='restock',
                    quantity_change=qty_received,
                    previous_quantity=int(previous_qty),
                    new_quantity=int(product.stock_quantity),
                    reason=f'Received from {self.purchase_number} ({qty_received} of {item.quantity} ordered)'
                )
                
                # Create damage adjustment if needed
                if qty_damaged > 0:
                    StockAdjustment.objects.create(
                        business=self.business,
                        product=product,
                        adjustment_type='damage',
                        quantity_change=-qty_damaged,
                        previous_quantity=0,
                        new_quantity=0,
                        reason=f'Damaged on delivery - {self.purchase_number}: {notes}'
                    )
            else:
                # No receiving data - use full ordered quantity (backward compatibility)
                qty_received = item.quantity
                item.quantity_received = qty_received
                item.quantity_damaged = 0
                item.save()
                
                product = item.product
                previous_qty = product.stock_quantity
                product.stock_quantity += Decimal(qty_received)
                product.save()
                
                StockAdjustment.objects.create(
                    business=self.business,
                    product=product,
                    adjustment_type='restock',
                    quantity_change=qty_received,
                    previous_quantity=int(previous_qty),
                    new_quantity=int(product.stock_quantity),
                    reason=f'Received from {self.purchase_number}'
                )
        
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
    quantity = models.PositiveIntegerField(help_text='Quantity ordered')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
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
        self.total_cost = Decimal(self.quantity) * self.unit_cost
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


# ==================== SUPPLIER PAYMENTS ====================

class SupplierPayment(models.Model):
    """Records payments made to suppliers"""
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='supplier_payments')
    payment_number = models.CharField(max_length=20, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='payments')
    payment_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    payment_method = models.ForeignKey('PaymentMethod', on_delete=models.PROTECT)
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='supplier_payments_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date', '-created_at']
        unique_together = [['business', 'payment_number']]
        indexes = [
            models.Index(fields=['supplier', 'payment_date']),
            models.Index(fields=['payment_date']),
        ]
    
    def __str__(self):
        return f"{self.payment_number} - {self.supplier.name} - KES {self.amount}"
    
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
        """Returns the total amount allocated to purchases"""
        return self.allocations.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def unallocated_amount(self):
        """Returns the amount not yet allocated to specific purchases"""
        return self.amount - self.total_allocated()


class PaymentAllocation(models.Model):
    """Tracks allocation of payments to specific purchases"""
    payment = models.ForeignKey(SupplierPayment, on_delete=models.CASCADE, related_name='allocations')
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name='payment_allocations')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['payment']),
            models.Index(fields=['purchase']),
        ]
    
    def __str__(self):
        return f"{self.payment.payment_number} -> {self.purchase.purchase_number}: KES {self.amount}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Validate allocation amount doesn't exceed payment amount
        if self.amount > self.payment.amount:
            raise ValidationError("Allocation amount cannot exceed payment amount")
        
        # Validate total allocations for this payment don't exceed payment amount
        existing_allocations = PaymentAllocation.objects.filter(
            payment=self.payment
        ).exclude(pk=self.pk).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        
        if existing_allocations + self.amount > self.payment.amount:
            raise ValidationError("Total allocations exceed payment amount")
        
        # Validate total allocations for this purchase don't exceed purchase total
        existing_purchase_allocations = PaymentAllocation.objects.filter(
            purchase=self.purchase
        ).exclude(pk=self.pk).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        
        if existing_purchase_allocations + self.amount > self.purchase.total_amount:
            raise ValidationError("Total allocations exceed purchase amount")



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


# ==================== BUSINESS SETTINGS ====================

class BusinessSettings(models.Model):
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
        return self.business_name or self.business.name
    
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
        ('stock_adjust', 'Stock Adjustment'),
        ('purchase', 'Purchase'),
        ('settings', 'Settings Change'),
        ('backup', 'Data Backup'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    model_name = models.CharField(max_length=50, blank=True)
    object_id = models.IntegerField(blank=True, null=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
        ]
    
    def __str__(self):
        username = self.user.username if self.user else "Unknown"
        return f"{username} - {self.action_type} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def log_activity(cls, user, action_type, description, model_name='', object_id=None, request=None):
        """Helper method to create activity log"""
        ip_address = None
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0]
            else:
                ip_address = request.META.get('REMOTE_ADDR')
        
        return cls.objects.create(
            user=user,
            action_type=action_type,
            model_name=model_name,
            object_id=object_id,
            description=description,
            ip_address=ip_address
        )


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
            self.save()
            return True
        return False
    
    def mark_collected(self, collection_date=None, notes=''):
        """Mark goods as collected by supplier"""
        self.status = 'collected'
        self.collection_date = collection_date or timezone.now().date()
        self.collection_notes = notes
        self.save()
    
    def apply_credit_note(self, credit_note_number, amount, date=None):
        """Record credit note received from supplier"""
        self.status = 'credited'
        self.credit_note_number = credit_note_number
        self.credit_note_amount = amount
        self.credit_note_date = date or timezone.now().date()
        self.save()
    
    def cancel(self):
        """Cancel the GRN"""
        if self.status in ['draft', 'submitted']:
            self.status = 'cancelled'
            self.save()
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

class Customer(models.Model):
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
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = [['business', 'customer_code']]
    
    def __str__(self):
        return f"{self.name} ({self.customer_code})"
    
    def save(self, *args, **kwargs):
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


class LoyaltyReward(models.Model):
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

class PaymentMethod(models.Model):
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


class SalePayment(models.Model):
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
    """Promotional campaigns and discounts"""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, help_text="Promo code customers can enter")
    description = models.TextField(blank=True)
    
    # Discount details
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
        ('buy_x_get_y', 'Buy X Get Y'),
    ]
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Buy X Get Y details
    buy_quantity = models.IntegerField(default=0, help_text="Buy this many")
    get_quantity = models.IntegerField(default=0, help_text="Get this many free")
    
    # Validity
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    # Restrictions
    min_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_uses = models.IntegerField(default=0, help_text="0 = unlimited")
    uses_count = models.IntegerField(default=0)
    
    # Applicable products/categories
    applicable_products = models.ManyToManyField(Product, blank=True)
    applicable_categories = models.ManyToManyField(Category, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    def is_valid(self):
        """Check if promotion is currently valid"""
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.start_date or now > self.end_date:
            return False
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False
        return True
    
    def can_apply_to_sale(self, sale_amount):
        """Check if promotion can be applied to a sale"""
        if not self.is_valid():
            return False
        if sale_amount < self.min_purchase_amount:
            return False
        return True


# ==================== EXPENSE TRACKING ====================

class ExpenseCategory(models.Model):
    """Categories for business expenses"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    class Meta:
        verbose_name_plural = "Expense Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Expense(models.Model):
    """Track business expenses"""
    expense_number = models.CharField(max_length=20, unique=True, editable=False)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    expense_date = models.DateField(default=timezone.now)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT)
    reference_number = models.CharField(max_length=100, blank=True)
    
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-expense_date']
    
    def __str__(self):
        return f"{self.expense_number} - {self.description}"
    
    def save(self, *args, **kwargs):
        if not self.expense_number:
            # Generate expense number: EXP-YYYYMMDD-XXXX
            today = timezone.now()
            date_str = today.strftime('%Y%m%d')
            last_expense = Expense.objects.filter(
                expense_number__startswith=f'EXP-{date_str}'
            ).order_by('-expense_number').first()
            if last_expense:
                last_num = int(last_expense.expense_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
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
