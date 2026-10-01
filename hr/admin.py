from django.contrib import admin
from .models import (
    Department, KenyanBank, Employee,
    StatutoryRuleSet, PAYETaxBand, NSSFTierRule, SHIFRule,
    HousingLevyRule, NITARule, StatutoryReliefRule,
    ConsentRecord, DataSubjectRequest, DataBreachIncident, SensitiveDataAccessLog,
    Attendance, Payroll, StaffAdvance, Leave,
    PerformanceRecord, DisciplinaryRecord
)


class PAYETaxBandInline(admin.TabularInline):
    model = PAYETaxBand
    extra = 0
    fields = ('band_order', 'lower_limit', 'upper_limit', 'rate_percentage', 'description')
    ordering = ('band_order',)


class NSSFTierRuleInline(admin.TabularInline):
    model = NSSFTierRule
    extra = 0
    fields = ('tier_name', 'lower_limit', 'upper_limit', 'employee_rate', 'employer_rate', 'max_employee_deduction', 'max_employer_contribution')


class StatutoryReliefRuleInline(admin.TabularInline):
    model = StatutoryReliefRule
    extra = 0
    fields = ('relief_type', 'monthly_amount', 'percentage', 'maximum_monthly_limit')


class SHIFRuleInline(admin.StackedInline):
    model = SHIFRule
    extra = 0


class HousingLevyRuleInline(admin.StackedInline):
    model = HousingLevyRule
    extra = 0


class NITARuleInline(admin.StackedInline):
    model = NITARule
    extra = 0


@admin.register(StatutoryRuleSet)
class StatutoryRuleSetAdmin(admin.ModelAdmin):
    list_display = ('name', 'version_code', 'business', 'effective_from', 'effective_to', 'is_active', 'updated_at')
    list_filter = ('business', 'is_active', 'effective_from')
    search_fields = ('name', 'version_code', 'notes')
    inlines = [
        PAYETaxBandInline,
        NSSFTierRuleInline,
        SHIFRuleInline,
        HousingLevyRuleInline,
        NITARuleInline,
        StatutoryReliefRuleInline,
    ]


@admin.register(KenyanBank)
class KenyanBankAdmin(admin.ModelAdmin):
    list_display = ('name', 'bank_code', 'swift_code', 'is_active')
    search_fields = ('name', 'bank_code', 'swift_code')
    list_filter = ('is_active',)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('staff_code', 'get_full_name', 'id_number', 'kra_pin', 'nssf_number', 'sha_number', 'job_title', 'branch', 'basic_salary', 'status')
    list_filter = ('business', 'branch', 'department', 'status', 'is_secondary_employee', 'is_non_resident', 'disability_status')
    search_fields = ('staff_code', 'first_name', 'last_name', 'id_number', 'kra_pin', 'nssf_number', 'sha_number', 'phone_number', 'user_account__username', 'user_account__email')
    readonly_fields = ('staff_code', 'created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('business', 'branch', 'department', 'user_account', 'staff_code', 'first_name', 'last_name', 'job_title', 'status', 'hire_date')
        }),
        ('Kenyan Statutory Identifiers', {
            'fields': ('id_type', 'id_number', 'kra_pin', 'nssf_number', 'sha_number', 'nhif_number', 'helb_number', 'nita_number')
        }),
        ('Disbursement & Banking', {
            'fields': ('phone_number', 'mpesa_number', 'bank_name', 'bank_code', 'bank_branch', 'bank_branch_code', 'bank_account_number')
        }),
        ('Tax Classification & PWD Exemption', {
            'fields': ('is_secondary_employee', 'is_non_resident', 'disability_status', 'disability_cert_number', 'disability_exemption_cert', 'disability_exemption_expiry')
        }),
        ('Demographics & Work Permits', {
            'fields': ('county', 'nationality', 'work_permit_type', 'work_permit_number', 'work_permit_expiry')
        }),
        ('Compensation & Allowances', {
            'fields': ('basic_salary', 'hourly_rate', 'house_allowance', 'transport_allowance', 'medical_allowance', 'other_allowance', 'other_allowances')
        }),
        ('Emergency Contact & Notes', {
            'fields': ('emergency_contact_name', 'emergency_contact_phone', 'address', 'notes', 'created_at', 'updated_at')
        }),
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'manager', 'created_at')
    list_filter = ('business',)
    search_fields = ('name',)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'clock_in', 'clock_out', 'total_hours', 'status')
    list_filter = ('status', 'date', 'employee__business', 'employee__branch')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__staff_code', 'notes')


@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('employee', 'period_start', 'period_end', 'gross_salary', 'paye', 'nssf', 'shif', 'housing_levy', 'employer_nssf', 'employer_housing_levy', 'net_salary', 'status')
    list_filter = ('status', 'period_start', 'period_end', 'employee__business')
    search_fields = ('employee__first_name', 'employee__last_name', 'employee__staff_code')
    readonly_fields = ('gross_salary', 'total_deductions', 'total_employer_cost')


@admin.register(StaffAdvance)
class StaffAdvanceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'amount', 'date_taken', 'deduction_per_month', 'balance_remaining', 'status')
    list_filter = ('status', 'date_taken', 'employee__business')
    search_fields = ('employee__first_name', 'employee__last_name', 'reason')


@admin.register(Leave)
class LeaveAdmin(admin.ModelAdmin):
    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'days_count', 'status', 'approved_by')
    list_filter = ('leave_type', 'status', 'start_date', 'employee__business')
    search_fields = ('employee__first_name', 'employee__last_name', 'reason')


@admin.register(PerformanceRecord)
class PerformanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'period_start', 'period_end', 'total_sales', 'total_transactions', 'performance_score')
    list_filter = ('period_start', 'period_end', 'employee__business')


@admin.register(DisciplinaryRecord)
class DisciplinaryRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'incident_date', 'incident_type', 'hearing_held', 'issued_by')
    list_filter = ('incident_type', 'hearing_held', 'incident_date', 'employee__business')
    search_fields = ('employee__first_name', 'employee__last_name', 'description', 'action_taken')


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'purpose', 'is_consented', 'privacy_policy_version', 'consented_at', 'ip_address')
    list_filter = ('is_consented', 'privacy_policy_version', 'consented_at')
    search_fields = ('employee__first_name', 'employee__last_name', 'purpose')


@admin.register(DataSubjectRequest)
class DataSubjectRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'request_type', 'status', 'received_at', 'due_date', 'completed_at', 'handled_by')
    list_filter = ('request_type', 'status', 'received_at', 'due_date')
    search_fields = ('employee__first_name', 'employee__last_name', 'details', 'resolution_notes')


@admin.register(DataBreachIncident)
class DataBreachIncidentAdmin(admin.ModelAdmin):
    list_display = ('title', 'business', 'severity', 'status', 'detected_at', 'odpc_notification_deadline', 'odpc_notified_at')
    list_filter = ('severity', 'status', 'detected_at')
    search_fields = ('title', 'description', 'odpc_reference_number')


@admin.register(SensitiveDataAccessLog)
class SensitiveDataAccessLogAdmin(admin.ModelAdmin):
    list_display = ('employee', 'data_category', 'action', 'user', 'timestamp', 'ip_address')
    list_filter = ('data_category', 'action', 'timestamp')
    search_fields = ('employee__first_name', 'employee__last_name', 'reason', 'user__username')
