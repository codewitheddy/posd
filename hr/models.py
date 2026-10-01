import re
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


# ─── KENYA VALIDATION PATTERNS ───────────────────────────────────────────────
KRA_PIN_REGEX = r'^[A-Z]\d{9}[A-Z]$'
kra_pin_validator = RegexValidator(
    regex=KRA_PIN_REGEX,
    message="KRA PIN must be exactly 11 characters: 1 uppercase letter, 9 digits, and 1 uppercase letter (e.g. A012345678X)."
)

KENYA_PHONE_REGEX = r'^(?:\+254|0)?[17]\d{8}$'
kenya_phone_validator = RegexValidator(
    regex=KENYA_PHONE_REGEX,
    message="Phone number must be a valid Kenyan format (e.g. +254712345678, 0712345678, or 0112345678)."
)

KENYA_COUNTIES = [
    ('baringo', 'Baringo'), ('bomet', 'Bomet'), ('bungoma', 'Bungoma'),
    ('busia', 'Busia'), ('elgeyo_marakwet', 'Elgeyo-Marakwet'), ('embu', 'Embu'),
    ('garissa', 'Garissa'), ('homa_bay', 'Homa Bay'), ('isiolo', 'Isiolo'),
    ('kajiado', 'Kajiado'), ('kakamega', 'Kakamega'), ('kericho', 'Kericho'),
    ('kiambu', 'Kiambu'), ('kilifi', 'Kilifi'), ('kirinyaga', 'Kirinyaga'),
    ('kisii', 'Kisii'), ('kisumu', 'Kisumu'), ('kitui', 'Kitui'),
    ('kwale', 'Kwale'), ('laikipia', 'Laikipia'), ('lamu', 'Lamu'),
    ('machakos', 'Machakos'), ('makueni', 'Makueni'), ('mandera', 'Mandera'),
    ('marsabit', 'Marsabit'), ('meru', 'Meru'), ('migori', 'Migori'),
    ('mombasa', 'Mombasa'), ('muranga', "Murang'a"), ('nairobi', 'Nairobi'),
    ('nakuru', 'Nakuru'), ('nandi', 'Nandi'), ('narok', 'Narok'),
    ('nyamira', 'Nyamira'), ('nyandarua', 'Nyandarua'), ('nyeri', 'Nyeri'),
    ('samburu', 'Samburu'), ('siaya', 'Siaya'), ('taita_taveta', 'Taita-Taveta'),
    ('tana_river', 'Tana River'), ('tharaka_nithi', 'Tharaka-Nithi'),
    ('trans_nzoia', 'Trans Nzoia'), ('turkana', 'Turkana'), ('uasin_gishu', 'Uasin Gishu'),
    ('vihiga', 'Vihiga'), ('wajir', 'Wajir'), ('pokot', 'West Pokot'),
]


# ─── CORE HR MASTER MODELS ───────────────────────────────────────────────────

class Department(models.Model):
    business = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='hr_departments')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_departments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('business', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.business.name})"


class KenyanBank(models.Model):
    """Registry of Kenyan commercial banks and clearing codes for bulk EFT/RTGS."""
    name = models.CharField(max_length=100)
    bank_code = models.CharField(max_length=20, unique=True, help_text="Central Bank of Kenya clearing code")
    swift_code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.bank_code})"


class Employee(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated'),
    ]

    ID_TYPE_CHOICES = [
        ('national_id', 'National ID Card'),
        ('passport', 'Passport'),
        ('alien_id', 'Alien ID Card / Refugee ID'),
        ('military_id', 'Military ID'),
    ]

    user_account = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employee_profile',
        help_text="Leave blank for non-POS staff (cleaners, drivers, etc.)"
    )
    first_name = models.CharField(max_length=100, blank=True, help_text="Required if no user account")
    last_name = models.CharField(max_length=100, blank=True)
    business = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='employees')
    branch = models.ForeignKey('pos.Branch', on_delete=models.PROTECT, related_name='employees')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    job_title = models.CharField(max_length=100)
    staff_code = models.CharField(max_length=20, unique=True, editable=False, null=True, help_text="Auto-generated staff code")

    # Kenya Statutory Identification & Tax Fields
    id_type = models.CharField(max_length=20, choices=ID_TYPE_CHOICES, default='national_id')
    id_number = models.CharField(max_length=50, null=True, help_text="National ID / Passport Number")
    kra_pin = models.CharField(max_length=50, blank=True, null=True, validators=[kra_pin_validator], help_text="KRA PIN (Format: A012345678X)")
    nssf_number = models.CharField(max_length=50, null=True, help_text="NSSF Member Number")
    sha_number = models.CharField(max_length=50, blank=True, null=True, help_text="Social Health Authority (SHA) registration number")
    nhif_number = models.CharField(max_length=50, blank=True, null=True, help_text="Legacy NHIF number (historical records)")
    helb_number = models.CharField(max_length=50, blank=True, null=True, help_text="HELB loan account reference")
    nita_number = models.CharField(max_length=50, blank=True, null=True, help_text="NITA apprentice/employer registration number")

    # Payment & Banking Details
    phone_number = models.CharField(max_length=20, blank=True, validators=[kenya_phone_validator], help_text="Official contact phone e.g. +254712345678")
    mpesa_number = models.CharField(max_length=20, blank=True, validators=[kenya_phone_validator], help_text="M-Pesa B2C salary payment phone e.g. +254712345678")
    bank_name = models.CharField(max_length=100, blank=True, help_text="Bank Name")
    bank_code = models.CharField(max_length=20, blank=True, help_text="Bank Clearing Code")
    bank_branch = models.CharField(max_length=100, blank=True, help_text="Branch Name")
    bank_branch_code = models.CharField(max_length=20, blank=True, help_text="Branch Sort Code")
    bank_account_number = models.CharField(max_length=50, blank=True, help_text="Bank Account Number")

    # Tax Classification & Exemption Status
    is_secondary_employee = models.BooleanField(default=False, help_text="Secondary employment (No personal relief granted)")
    is_non_resident = models.BooleanField(default=False, help_text="Non-resident for tax purposes (flat withholding rate)")
    disability_status = models.BooleanField(default=False, help_text="Registered Person with Disability (NCPWD)")
    disability_cert_number = models.CharField(max_length=50, blank=True, help_text="NCPWD Registration Number")
    disability_exemption_cert = models.CharField(max_length=50, blank=True, help_text="KRA Tax Exemption Certificate Number")
    disability_exemption_expiry = models.DateField(null=True, blank=True, help_text="KRA PWD Exemption Expiry Date")

    # Demographic & Work Permit Tracking
    county = models.CharField(max_length=50, choices=KENYA_COUNTIES, blank=True, help_text="County of residence")
    nationality = models.CharField(max_length=50, default='Kenyan')
    work_permit_type = models.CharField(max_length=50, blank=True, help_text="Class D, Class G, etc. for foreign nationals")
    work_permit_number = models.CharField(max_length=50, blank=True)
    work_permit_expiry = models.DateField(null=True, blank=True)

    # Compensation & Allowances
    address = models.TextField(blank=True)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Basic Salary')
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    house_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly house allowance")
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly transport allowance")
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly medical allowance")
    other_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly other allowances")
    other_allowances = models.JSONField(default=dict, blank=True, help_text="Additional custom allowances as JSON {'name': amount, ...}")

    # Employment Status & Lifecycle
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    hire_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def get_full_name(self):
        """Return display name regardless of whether a user account exists."""
        if self.user_account:
            return self.user_account.get_full_name() or self.user_account.username
        return f"{self.first_name} {self.last_name}".strip() or f"Employee #{self.pk}"

    @property
    def effective_hourly_rate(self):
        """Calculate effective hourly rate for overtime calculations."""
        if self.basic_salary > 0:
            # Salaried employees: basic salary ÷ 208 hours (26 days × 8 hours)
            return self.basic_salary / Decimal('208')
        else:
            return self.hourly_rate

    @property
    def total_other_allowances(self):
        """Calculate total of all other allowances from the JSON field."""
        if not self.other_allowances:
            return Decimal('0.00')
        return sum(Decimal(str(amount)) for amount in self.other_allowances.values() if amount)

    def __str__(self):
        return f"{self.get_full_name()} ({self.business.name})"

    def clean(self):
        """Validate compulsory fields and formats for staff registration."""
        errors = {}

        if not self.id_number:
            errors['id_number'] = 'National ID or Passport number is required.'
        if self.kra_pin:
            self.kra_pin = self.kra_pin.strip().upper()
            if not re.match(KRA_PIN_REGEX, self.kra_pin):
                errors['kra_pin'] = 'KRA PIN must be exactly 11 characters (1 letter, 9 digits, 1 letter, e.g. A012345678X).'
        else:
            errors['kra_pin'] = 'KRA PIN is required for statutory tax compliance.'

        if not self.nssf_number:
            errors['nssf_number'] = 'NSSF number is required.'

        # Validate name
        if not self.user_account and not (self.first_name and self.last_name):
            errors['first_name'] = 'Either select a user account or provide first and last name.'
            if not self.last_name:
                errors['last_name'] = 'Last name is required when no user account is selected.'

        if self.disability_status and not self.disability_cert_number:
            errors['disability_cert_number'] = 'NCPWD registration certificate number is required when disability status is active.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.kra_pin:
            self.kra_pin = self.kra_pin.strip().upper()

        # Auto-generate staff code if not set
        if not self.staff_code:
            last_employee = Employee.objects.filter(business=self.business).order_by('-id').first()
            if last_employee and last_employee.staff_code:
                try:
                    num = int(last_employee.staff_code[3:])
                    new_num = num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.staff_code = f"EMP{new_num:03d}"

        is_new = self.pk is None
        old_status = None
        if not is_new:
            try:
                old_status = Employee.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            except Exception:
                pass
        super().save(*args, **kwargs)
        if self.user_account and (is_new or old_status != self.status):
            try:
                profile = self.user_account.profile
                if self.status == 'terminated':
                    profile.is_active = False
                elif self.status == 'active':
                    profile.is_active = True
                profile.save(update_fields=['is_active'])
            except Exception:
                pass


# ─── VERSIONED STATUTORY RULE ENGINE MODELS (KENYA) ──────────────────────────

class StatutoryRuleSet(models.Model):
    """
    Master versioned, effective-dated statutory rule table for Kenyan payroll.
    Eliminates all hardcoding and provides complete auditability across Finance Acts.
    """
    business = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='statutory_rulesets')
    name = models.CharField(max_length=150, help_text="e.g. Kenya Statutory Rules — 2026 Edition")
    version_code = models.CharField(max_length=50, help_text="e.g. KE-2026-V1")
    effective_from = models.DateField(help_text="Date when this rule-set becomes active")
    effective_to = models.DateField(null=True, blank=True, help_text="Leave blank if currently active / open-ended")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, help_text="Gazette notice / Finance Act citation")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_from', '-created_at']
        unique_together = ('business', 'version_code')

    def __str__(self):
        return f"{self.name} ({self.version_code}) [{self.effective_from} to {self.effective_to or 'Open'}]"

    @classmethod
    def get_active_ruleset(cls, business, target_date=None):
        """Resolve the active statutory ruleset for a business on a given date."""
        if target_date is None:
            target_date = timezone.localdate()
        
        # 1. Look for ruleset specifically covering target_date
        ruleset = cls.objects.filter(
            business=business,
            is_active=True,
            effective_from__lte=target_date,
        ).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=target_date)
        ).order_by('-effective_from').first()

        # 2. Fallback to latest active ruleset
        if not ruleset:
            ruleset = cls.objects.filter(business=business, is_active=True).order_by('-effective_from').first()

        # 3. If none exists, seed default Kenya 2026 ruleset for this business
        if not ruleset:
            ruleset = cls.seed_default_kenya_rules(business)

        return ruleset

    @classmethod
    def seed_default_kenya_rules(cls, business, user=None):
        """Seed default reference 2026 Kenya statutory ruleset."""
        ruleset, created = cls.objects.get_or_create(
            business=business,
            version_code='KE-2026-DEF',
            defaults={
                'name': 'Kenya Statutory Rules — 2026 Standard',
                'effective_from': timezone.datetime(2026, 1, 1).date(),
                'is_active': True,
                'notes': 'Seeded default rules based on Income Tax Act Cap 470, NSSF Act 2013, SHIA 2023, AHA 2024.',
                'created_by': user,
            }
        )

        # 1. PAYE Tax Bands (Monthly)
        # Band 1: 0 to 24,000 @ 10%
        # Band 2: 24,001 to 32,333 @ 25%
        # Band 3: 32,334 to 500,000 @ 30%
        # Band 4: 500,001 to 800,000 @ 32.5%
        # Band 5: Above 800,000 @ 35%
        paye_bands = [
            (1, Decimal('0.00'), Decimal('24000.00'), Decimal('10.00'), 'First KES 24,000 @ 10%'),
            (2, Decimal('24000.01'), Decimal('32333.00'), Decimal('25.00'), 'Next KES 8,333 @ 25%'),
            (3, Decimal('32333.01'), Decimal('500000.00'), Decimal('30.00'), 'Next KES 467,667 @ 30%'),
            (4, Decimal('500000.01'), Decimal('800000.00'), Decimal('32.50'), 'Next KES 300,000 @ 32.5%'),
            (5, Decimal('800000.01'), None, Decimal('35.00'), 'Above KES 800,000 @ 35%'),
        ]
        for order, lower, upper, rate, desc in paye_bands:
            PAYETaxBand.objects.get_or_create(
                ruleset=ruleset,
                band_order=order,
                defaults={'lower_limit': lower, 'upper_limit': upper, 'rate_percentage': rate, 'description': desc}
            )

        # 2. NSSF Tier I and Tier II (Feb 2026 Phased Schedule)
        NSSFTierRule.objects.get_or_create(
            ruleset=ruleset,
            tier_name='tier_1',
            defaults={
                'lower_limit': Decimal('0.00'),
                'upper_limit': Decimal('9000.00'),
                'employee_rate': Decimal('6.00'),
                'employer_rate': Decimal('6.00'),
                'max_employee_deduction': Decimal('540.00'),
                'max_employer_contribution': Decimal('540.00'),
            }
        )
        NSSFTierRule.objects.get_or_create(
            ruleset=ruleset,
            tier_name='tier_2',
            defaults={
                'lower_limit': Decimal('9000.01'),
                'upper_limit': Decimal('108000.00'),
                'employee_rate': Decimal('6.00'),
                'employer_rate': Decimal('6.00'),
                'max_employee_deduction': Decimal('5940.00'),
                'max_employer_contribution': Decimal('5940.00'),
            }
        )

        # 3. SHIF (Social Health Insurance Fund)
        SHIFRule.objects.get_or_create(
            ruleset=ruleset,
            defaults={
                'percentage_rate': Decimal('2.75'),
                'minimum_contribution': Decimal('300.00'),
                'maximum_contribution': None,
                'is_allowable_deduction': False,
            }
        )

        # 4. Affordable Housing Levy (1.5% each)
        HousingLevyRule.objects.get_or_create(
            ruleset=ruleset,
            defaults={
                'employee_rate': Decimal('1.50'),
                'employer_rate': Decimal('1.50'),
                'is_allowable_deduction': True,
            }
        )

        # 5. NITA Levy (KES 50 flat employer)
        NITARule.objects.get_or_create(
            ruleset=ruleset,
            defaults={
                'monthly_employer_levy': Decimal('50.00'),
            }
        )

        # 6. Statutory Reliefs & Caps
        relief_defaults = [
            ('personal', Decimal('2400.00'), Decimal('0.00'), Decimal('2400.00')),
            ('insurance', Decimal('0.00'), Decimal('15.00'), Decimal('5000.00')),
            ('disability', Decimal('150000.00'), Decimal('0.00'), Decimal('150000.00')),
            ('pension_cap', Decimal('20000.00'), Decimal('0.00'), Decimal('20000.00')),
            ('mortgage_cap', Decimal('25000.00'), Decimal('0.00'), Decimal('25000.00')),
            ('post_retirement_medical', Decimal('15000.00'), Decimal('0.00'), Decimal('15000.00')),
        ]
        for r_type, amount, pct, limit in relief_defaults:
            StatutoryReliefRule.objects.get_or_create(
                ruleset=ruleset,
                relief_type=r_type,
                defaults={'monthly_amount': amount, 'percentage': pct, 'maximum_monthly_limit': limit}
            )

        return ruleset


class PAYETaxBand(models.Model):
    """Progressive monthly PAYE tax bands (Income Tax Act Cap 470)."""
    ruleset = models.ForeignKey(StatutoryRuleSet, on_delete=models.CASCADE, related_name='paye_bands')
    band_order = models.PositiveIntegerField(default=1)
    lower_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    upper_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Null for the topmost bracket")
    rate_percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g. 10.00, 25.00, 30.00, 32.50, 35.00")
    description = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['ruleset', 'band_order']
        unique_together = ('ruleset', 'band_order')

    def __str__(self):
        upper_str = f"KES {self.upper_limit:,.2f}" if self.upper_limit else "Above"
        return f"Band {self.band_order}: KES {self.lower_limit:,.2f} – {upper_str} @ {self.rate_percentage}%"


class NSSFTierRule(models.Model):
    """NSSF Act 2013 Tier I & Tier II rules with employer match."""
    ruleset = models.ForeignKey(StatutoryRuleSet, on_delete=models.CASCADE, related_name='nssf_tiers')
    tier_name = models.CharField(max_length=20, choices=[('tier_1', 'Tier I (Lower Earnings Limit)'), ('tier_2', 'Tier II (Upper Earnings Limit)')])
    lower_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    upper_limit = models.DecimalField(max_digits=12, decimal_places=2)
    employee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('6.00'))
    employer_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('6.00'))
    max_employee_deduction = models.DecimalField(max_digits=10, decimal_places=2)
    max_employer_contribution = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['ruleset', 'tier_name']
        unique_together = ('ruleset', 'tier_name')

    def __str__(self):
        return f"{self.get_tier_name_display()} (Max KES {self.max_employee_deduction:,.2f})"


class SHIFRule(models.Model):
    """Social Health Insurance Fund (SHIF) / Social Health Insurance Act 2023."""
    ruleset = models.OneToOneField(StatutoryRuleSet, on_delete=models.CASCADE, related_name='shif_rule')
    percentage_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('2.75'))
    minimum_contribution = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('300.00'))
    maximum_contribution = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_allowable_deduction = models.BooleanField(default=False, help_text="Treated as allowable deduction before PAYE calculation")

    def __str__(self):
        return f"SHIF: {self.percentage_rate}% (Min KES {self.minimum_contribution})"


class HousingLevyRule(models.Model):
    """Affordable Housing Levy (Affordable Housing Act 2024)."""
    ruleset = models.OneToOneField(StatutoryRuleSet, on_delete=models.CASCADE, related_name='housing_levy_rule')
    employee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.50'))
    employer_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.50'))
    is_allowable_deduction = models.BooleanField(default=True, help_text="Allowable deduction for PAYE tax purposes")

    def __str__(self):
        return f"Housing Levy: {self.employee_rate}% Emp + {self.employer_rate}% Empr"


class NITARule(models.Model):
    """National Industrial Training Authority (NITA) monthly employer levy."""
    ruleset = models.OneToOneField(StatutoryRuleSet, on_delete=models.CASCADE, related_name='nita_rule')
    monthly_employer_levy = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('50.00'), help_text="Flat monthly employer levy per employee")

    def __str__(self):
        return f"NITA Levy: KES {self.monthly_employer_levy}/month"


class StatutoryReliefRule(models.Model):
    """Statutory tax reliefs and allowable deduction caps."""
    RELIEF_TYPES = [
        ('personal', 'Personal Relief (Monthly)'),
        ('insurance', 'Insurance Relief (Health/Life Premiums)'),
        ('disability', 'Disability (PWD) Monthly Tax Exemption'),
        ('pension_cap', 'Defined Pension / Provident Fund Monthly Cap'),
        ('mortgage_cap', 'Owner-Occupied Mortgage Interest Monthly Cap'),
        ('post_retirement_medical', 'Post-Retirement Medical Fund Monthly Cap'),
    ]
    ruleset = models.ForeignKey(StatutoryRuleSet, on_delete=models.CASCADE, related_name='relief_rules')
    relief_type = models.CharField(max_length=40, choices=RELIEF_TYPES)
    monthly_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="e.g. 15% for insurance relief")
    maximum_monthly_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="e.g. 5,000 max monthly insurance relief")

    class Meta:
        ordering = ['ruleset', 'relief_type']
        unique_together = ('ruleset', 'relief_type')

    def __str__(self):
        return f"{self.get_relief_type_display()}: KES {self.monthly_amount:,.2f}"


# ─── DATA PROTECTION ACT 2019 (KENYA ODPC) FOUNDATIONS ────────────────────────

class ConsentRecord(models.Model):
    """Employee personal data processing consent and privacy notice acknowledgment."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='consent_records')
    purpose = models.CharField(max_length=200, help_text="e.g. Payroll Processing, Biometric Attendance, Statutory Returns")
    is_consented = models.BooleanField(default=True)
    consented_at = models.DateTimeField(auto_now_add=True)
    privacy_policy_version = models.CharField(max_length=50, default='KE-DPA-2024-V1')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ['-consented_at']

    def __str__(self):
        return f"Consent for {self.employee} ({self.purpose})"


class DataSubjectRequest(models.Model):
    """DPA 2019 Data Subject Rights (DSR) request tracker with statutory 30-day resolution SLA."""
    REQUEST_TYPES = [
        ('access', 'Right to Access (Copy of Personal Data)'),
        ('rectification', 'Right to Rectification (Correction)'),
        ('erasure', 'Right to Erasure / Anonymization'),
        ('restriction', 'Right to Restrict Processing'),
        ('portability', 'Right to Data Portability (JSON/CSV Export)'),
        ('objection', 'Right to Object to Processing'),
    ]
    STATUS_CHOICES = [
        ('received', 'Received'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
    ]
    business = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='dsr_requests')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='dsr_requests')
    request_type = models.CharField(max_length=30, choices=REQUEST_TYPES)
    details = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='received')
    received_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(help_text="Statutory 30-day deadline per DPA 2019")
    completed_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-received_at']

    def save(self, *args, **kwargs):
        if not self.due_date:
            self.due_date = timezone.localdate() + timezone.timedelta(days=30)
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return self.status in ['received', 'in_progress'] and timezone.localdate() > self.due_date


class DataBreachIncident(models.Model):
    """Personal data breach register with 72-hour ODPC notification tracker (DPA Sec. 43)."""
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('detected', 'Detected / Investigating'),
        ('contained', 'Contained'),
        ('reported_odpc', 'Reported to ODPC'),
        ('resolved', 'Resolved & Closed'),
    ]
    business = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='breach_incidents')
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    detected_at = models.DateTimeField()
    odpc_notification_deadline = models.DateTimeField(help_text="72 hours from detection")
    odpc_notified_at = models.DateTimeField(null=True, blank=True)
    odpc_reference_number = models.CharField(max_length=100, blank=True)
    affected_subjects_count = models.PositiveIntegerField(default=0)
    remediation_steps = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='detected')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-detected_at']

    def save(self, *args, **kwargs):
        if not self.odpc_notification_deadline and self.detected_at:
            self.odpc_notification_deadline = self.detected_at + timezone.timedelta(hours=72)
        super().save(*args, **kwargs)


class SensitiveDataAccessLog(models.Model):
    """Audit log specifically tracking access to sensitive employee data (salary, medical, ID, disciplinary)."""
    CATEGORY_CHOICES = [
        ('salary_payroll', 'Salary & Compensation'),
        ('national_id_passport', 'National ID / Passport / Bio'),
        ('medical_health', 'Medical Notes & Health Certs'),
        ('disciplinary', 'Disciplinary Hearings & Show Cause'),
        ('banking_pin', 'Banking Details & PIN'),
    ]
    ACTION_CHOICES = [
        ('view', 'Viewed Record'),
        ('edit', 'Updated Record'),
        ('export', 'Exported Report / CSV'),
        ('download', 'Downloaded File / PDF'),
    ]
    business = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='sensitive_data_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='access_logs')
    data_category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-timestamp']


# ─── OPERATIONAL HR MODELS ───────────────────────────────────────────────────

class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('off', 'Off'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    clock_in = models.TimeField()
    clock_out = models.TimeField(null=True, blank=True)
    total_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='present')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.employee} - {self.date} ({self.status})"


class Payroll(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payroll_records')
    ruleset_used = models.ForeignKey(StatutoryRuleSet, on_delete=models.SET_NULL, null=True, blank=True, related_name='payrolls_processed')
    period_start = models.DateField()
    period_end = models.DateField()
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Allowances
    house_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    other_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    other_allowances_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Total of additional custom allowances")
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    overtime_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Statutory Deductions (Employee Portion)
    paye = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    shif = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='SHIF (Social Health Insurance Fund)')
    nssf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='NSSF (Employee Tier I + II)')
    housing_levy = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Affordable Housing Levy (1.5% Employee)')
    
    # Statutory Contributions (Employer Matching Portion)
    employer_nssf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Employer Matching NSSF')
    employer_housing_levy = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Employer Matching Housing Levy (1.5%)')
    employer_nita = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name='Employer NITA Levy (KES 50)')
    
    # Custom Deductions & Advances
    helb_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='HELB Loan Deduction')
    absence_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    advances_deducted = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    # Net Pay
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    pay_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('employee', 'period_start', 'period_end')
        ordering = ['-period_end']

    def __str__(self):
        return f"{self.employee} - {self.period_start} to {self.period_end} ({self.status})"

    @property
    def total_allowances(self):
        return self.house_allowance + self.transport_allowance + self.medical_allowance + self.other_allowance + self.other_allowances_total

    @property
    def gross_salary(self):
        return self.basic_salary + self.total_allowances + self.overtime_amount + self.bonus + self.commission

    @property
    def total_deductions(self):
        return self.paye + self.shif + self.nssf + self.housing_levy + self.helb_deduction + self.absence_deduction + self.other_deductions + self.advances_deducted

    @property
    def total_employer_cost(self):
        """Total cost of employment = Gross Salary + Employer NSSF + Employer Housing Levy + NITA."""
        return self.gross_salary + self.employer_nssf + self.employer_housing_levy + self.employer_nita


class StaffAdvance(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('settled', 'Settled'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='advances')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    date_taken = models.DateField()
    deduction_per_month = models.DecimalField(max_digits=12, decimal_places=2)
    balance_remaining = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')

    class Meta:
        ordering = ['-date_taken']

    def __str__(self):
        return f"{self.employee} - KES {self.amount} ({self.status})"


class Leave(models.Model):
    LEAVE_TYPE_CHOICES = [
        ('annual', 'Annual Leave (21 Working Days Min)'),
        ('sick', 'Sick Leave (30 Full Pay / 15 Half Pay)'),
        ('maternity', 'Maternity Leave (3 Months Paid)'),
        ('paternity', 'Paternity Leave (2 Weeks Paid)'),
        ('emergency', 'Compassionate / Emergency Leave'),
        ('study', 'Study / Exam Leave'),
        ('unpaid', 'Unpaid Leave'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    days_count = models.PositiveIntegerField(default=1)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leaves')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.start_date} to {self.end_date})"


class PerformanceRecord(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='performance_records')
    period_start = models.DateField()
    period_end = models.DateField()
    total_sales = models.IntegerField(default=0)
    total_transactions = models.IntegerField(default=0)
    total_discounts_given = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_voids = models.IntegerField(default=0)
    total_refunds = models.IntegerField(default=0)
    shift_shortages = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    performance_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('employee', 'period_start', 'period_end')
        ordering = ['-period_end']

    def __str__(self):
        return f"{self.employee} - Score: {self.performance_score} ({self.period_start} to {self.period_end})"


class DisciplinaryRecord(models.Model):
    INCIDENT_TYPE_CHOICES = [
        ('show_cause', 'Show Cause Notice Issued'),
        ('verbal_warning', 'Verbal Warning'),
        ('written_warning_1', '1st Written Warning'),
        ('written_warning_final', 'Final Written Warning'),
        ('suspension', 'Suspension Pending Inquiry'),
        ('termination', 'Fair Termination / Dismissal'),
        ('other', 'Other Incident'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='disciplinary_records')
    incident_date = models.DateField()
    incident_type = models.CharField(max_length=30, choices=INCIDENT_TYPE_CHOICES)
    description = models.TextField()
    action_taken = models.TextField()
    hearing_held = models.BooleanField(default=False, help_text="Formal hearing conducted per Employment Act Sec. 41")
    hearing_date = models.DateField(null=True, blank=True)
    employee_accompanied_by = models.CharField(max_length=150, blank=True, help_text="Name of fellow employee or shop floor union rep")
    issued_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='issued_disciplinaries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-incident_date']

    def __str__(self):
        return f"{self.employee} - {self.incident_type} on {self.incident_date}"


class HRGLMapping(models.Model):
    """
    Maps Payroll and HR statutory deduction components to General Ledger account codes.
    Stores account codes as string identifiers to avoid cross-module coupling.
    """
    business = models.OneToOneField('pos.Business', on_delete=models.CASCADE, related_name='hr_gl_mapping')
    basic_salaries_expense_code = models.CharField(max_length=20, default='6000', help_text="Salaries & Wages Expense (default: 6000)")
    employer_nssf_expense_code = models.CharField(max_length=20, default='6030', help_text="NSSF Employer Expense (default: 6030)")
    employer_shif_expense_code = models.CharField(max_length=20, default='6020', help_text="SHIF Employer Expense (default: 6020)")
    employer_housing_levy_expense_code = models.CharField(max_length=20, default='6040', help_text="Housing Levy Employer Expense (default: 6040)")
    employer_nita_expense_code = models.CharField(max_length=20, default='6050', help_text="NITA Employer Expense (default: 6050)")
    
    net_salaries_payable_code = models.CharField(max_length=20, default='2200', help_text="Net Salaries Payable (default: 2200)")
    paye_payable_code = models.CharField(max_length=20, default='2110', help_text="PAYE Payable (default: 2110)")
    nssf_payable_code = models.CharField(max_length=20, default='2120', help_text="NSSF Deductions Payable (default: 2120)")
    shif_payable_code = models.CharField(max_length=20, default='2130', help_text="SHIF Deductions Payable (default: 2130)")
    housing_levy_payable_code = models.CharField(max_length=20, default='2140', help_text="Housing Levy Payable (default: 2140)")
    helb_payable_code = models.CharField(max_length=20, default='2150', help_text="HELB Deductions Payable (default: 2150)")
    nita_payable_code = models.CharField(max_length=20, default='2160', help_text="NITA Levy Payable (default: 2160)")
    staff_advances_asset_code = models.CharField(max_length=20, default='1310', help_text="Staff Advances Asset (default: 1310)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'HR GL Mapping'
        verbose_name_plural = 'HR GL Mappings'

    def __str__(self):
        return f"HR GL Mapping for {self.business.name}"

    @classmethod
    def get_for_business(cls, business):
        """Retrieve or create default mapping for a business."""
        if not business:
            return None
        mapping, _ = cls.objects.get_or_create(business=business)
        return mapping

