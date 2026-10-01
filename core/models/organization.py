"""
Core Organization and Identity Models
Includes Company, Branch, CompanyMembership, BranchMembership, and UserProfile.
"""
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.db import models
from django.utils import timezone
from core.models.base import TimeStampedModel, SoftDeleteModel


class Company(TimeStampedModel, SoftDeleteModel):
    """
    Central Tenant / Organization entity.
    All business modules and transactions are scoped to a Company.
    """
    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=100, unique=True)
    legal_name = models.CharField(max_length=255, blank=True)
    registration_number = models.CharField(max_length=100, blank=True, help_text="Business Registration Number")
    
    # Kenya Tax & Regulatory Identifiers
    kra_pin = models.CharField(max_length=50, blank=True, help_text="KRA PIN Number")
    vat_number = models.CharField(max_length=50, blank=True, help_text="VAT Registration Number")
    
    # Localization Defaults
    currency = models.CharField(max_length=3, default='KES', help_text="ISO 4217 Currency Code")
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=1, help_text="1=January (Kenya Fiscal Year)")
    timezone = models.CharField(max_length=50, default='Africa/Nairobi')
    
    # Contact & Physical Address
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, default='Nairobi')
    county = models.CharField(max_length=100, blank=True, default='Nairobi')
    logo = models.ImageField(upload_to='company_logos/', null=True, blank=True)
    
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Company'
        verbose_name_plural = 'Companies'
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_headquarters(self):
        """Return the HQ branch or first active branch."""
        hq = self.branches.filter(is_headquarters=True, is_active=True).first()
        if not hq:
            hq = self.branches.filter(is_active=True).first()
        return hq


class Branch(TimeStampedModel, SoftDeleteModel):
    """
    Physical or logical outlet / branch of a Company.
    """
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='branches',
        db_index=True,
    )
    name = models.CharField(max_length=100, db_index=True)
    code = models.CharField(max_length=20, db_index=True, help_text="Short code e.g. HQ, NBI-01, MSA-01")
    is_headquarters = models.BooleanField(default=False, help_text="Designates this branch as the primary HQ")
    
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True, default='Nairobi')
    county = models.CharField(max_length=100, blank=True, default='Nairobi')
    
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'
        unique_together = [['company', 'code']]
        ordering = ['-is_headquarters', 'name']

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class CompanyMembership(TimeStampedModel):
    """
    Associates a User with a Company and defines their platform role.
    """
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_MANAGER = 'manager'
    ROLE_STAFF = 'staff'
    ROLE_VIEWER = 'viewer'

    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner / Director'),
        (ROLE_ADMIN, 'Administrator'),
        (ROLE_MANAGER, 'Manager'),
        (ROLE_STAFF, 'Staff / Operator'),
        (ROLE_VIEWER, 'Viewer (Read-Only)'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='memberships',
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_memberships',
        db_index=True,
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STAFF, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    custom_permissions = models.JSONField(default=list, blank=True, help_text="List of granted permission codenames")

    class Meta:
        verbose_name = 'Company Membership'
        verbose_name_plural = 'Company Memberships'
        unique_together = [['company', 'user']]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.company.name} ({self.get_role_display()})"

    @property
    def is_admin_or_owner(self):
        return self.role in [self.ROLE_OWNER, self.ROLE_ADMIN] or self.user.is_superuser


class BranchMembership(TimeStampedModel):
    """
    Associates a User with a specific Branch and defines their primary outlet.
    """
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='memberships',
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='core_branch_memberships',
        db_index=True,
    )
    is_primary = models.BooleanField(default=False, help_text="True if this is the user's default branch")
    is_active = models.BooleanField(default=True, db_index=True)
    branch_role = models.CharField(max_length=30, blank=True, help_text="Branch-specific title or role e.g. Cashier")

    class Meta:
        verbose_name = 'Branch Membership'
        verbose_name_plural = 'Branch Memberships'
        unique_together = [['branch', 'user']]

    def __str__(self):
        return f"{self.user.username} @ {self.branch.name}"


class UserProfile(TimeStampedModel):
    """
    Platform Core User Profile extension on standard auth.User.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='core_profile',
    )
    phone = models.CharField(max_length=20, blank=True)
    pin_hash = models.CharField(max_length=128, blank=True, help_text="Hashed 4-6 digit quick PIN")
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    
    force_password_change = models.BooleanField(default=False)
    last_active_company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    last_active_branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    
    # Security Lockout Controls
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"Profile of {self.user.username}"

    def set_pin(self, raw_pin):
        """Hash and store the cashier/operator PIN."""
        if raw_pin:
            self.pin_hash = make_password(str(raw_pin))
        else:
            self.pin_hash = ''

    def check_pin(self, raw_pin):
        """Verify the PIN against stored hash."""
        if not self.pin_hash or not raw_pin:
            return False
        return check_password(str(raw_pin), self.pin_hash)

    def is_locked(self):
        """Check if account is temporarily locked due to failed attempts."""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def record_failed_attempt(self, max_attempts=5, lockout_minutes=15):
        """Increment failed attempts and lock if threshold exceeded."""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=lockout_minutes)
        self.save(update_fields=['failed_login_attempts', 'locked_until'])

    def reset_failed_attempts(self):
        """Reset failed attempt counter on successful login."""
        if self.failed_login_attempts > 0 or self.locked_until is not None:
            self.failed_login_attempts = 0
            self.locked_until = None
            self.save(update_fields=['failed_login_attempts', 'locked_until'])
