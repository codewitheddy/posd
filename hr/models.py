from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


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


class Employee(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('terminated', 'Terminated'),
    ]

    user_account = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employee_profile',
        help_text="Leave blank for non-POS staff (cleaners, drivers, etc.)"
    )
    # For non-POS staff who have no system login, store their name directly
    first_name = models.CharField(max_length=100, blank=True, help_text="Required if no user account")
    last_name = models.CharField(max_length=100, blank=True)
    business = models.ForeignKey('pos.Business', on_delete=models.CASCADE, related_name='employees')
    branch = models.ForeignKey('pos.Branch', on_delete=models.PROTECT, related_name='employees')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    job_title = models.CharField(max_length=100)
    staff_code = models.CharField(max_length=20, unique=True, editable=False, null=True, help_text="Auto-generated staff code")
    id_number = models.CharField(max_length=50, null=True, help_text="National ID number")
    kra_pin = models.CharField(max_length=50, blank=True, null=True, help_text="KRA PIN for tax purposes")
    nssf_number = models.CharField(max_length=50, null=True, help_text="NSSF number")
    nhif_number = models.CharField(max_length=50, null=True, help_text="NHIF number")
    address = models.TextField(blank=True)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Basic Salary')
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    # Allowances
    house_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly house allowance")
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly transport allowance")
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly medical allowance")
    other_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Monthly other allowances")
    other_allowances = models.JSONField(default=dict, blank=True, help_text="Additional custom allowances as JSON {'name': amount, ...}")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    hire_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # unique_together only applies when user_account is set
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
            # For salaried employees: basic salary ÷ 208 hours (26 days × 8 hours)
            return self.basic_salary / Decimal('208')
        else:
            # For hourly employees: use the entered hourly_rate
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
        """Validate compulsory fields for staff registration."""
        from django.core.exceptions import ValidationError
        
        errors = {}
        
        # Check compulsory fields
        if not self.id_number:
            errors['id_number'] = 'National ID number is required.'
        if not self.kra_pin:
            errors['kra_pin'] = 'KRA PIN is required.'
        if not self.nssf_number:
            errors['nssf_number'] = 'NSSF number is required.'
        if not self.nhif_number:
            errors['nhif_number'] = 'NHIF number is required.'
        
        # Validate that either user_account or first_name/last_name is provided
        if not self.user_account and not (self.first_name and self.last_name):
            errors['first_name'] = 'Either select a user account or provide first and last name.'
            if not self.last_name:
                errors['last_name'] = 'Last name is required when no user account is selected.'
        
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Auto-generate staff code if not set
        if not self.staff_code:
            # Generate unique staff code: EMP001, EMP002, etc.
            last_employee = Employee.objects.filter(business=self.business).order_by('-id').first()
            if last_employee and last_employee.staff_code:
                try:
                    # Extract number from last code (e.g., EMP001 -> 1)
                    num = int(last_employee.staff_code[3:])  # Skip 'EMP'
                    new_num = num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.staff_code = f"EMP{new_num:03d}"

        # Sync UserProfile.is_active when status changes (only for employees with user accounts)
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
    # Deductions
    paye = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    shif = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='SHIF (Social Health Insurance Fund)')
    nssf = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    housing_levy = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Affordable Housing Levy (1.5%)')
    absence_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    advances_deducted = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
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
        return self.paye + self.shif + self.nssf + self.housing_levy + self.absence_deduction + self.other_deductions + self.advances_deducted


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
        ('annual', 'Annual'),
        ('sick', 'Sick'),
        ('emergency', 'Emergency'),
        ('unpaid', 'Unpaid'),
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
        ('warning', 'Warning'),
        ('suspension', 'Suspension'),
        ('termination', 'Termination'),
        ('other', 'Other'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='disciplinary_records')
    incident_date = models.DateField()
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPE_CHOICES)
    description = models.TextField()
    action_taken = models.TextField()
    issued_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='issued_disciplinaries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-incident_date']

    def __str__(self):
        return f"{self.employee} - {self.incident_type} on {self.incident_date}"
