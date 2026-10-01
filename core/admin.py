"""
Django Admin Configuration for Platform Core
"""
from django.contrib import admin
from core.models import (
    Company,
    Branch,
    CompanyMembership,
    BranchMembership,
    UserProfile,
    ModuleActivation,
    CoreSetting,
    SensitiveDataAccessLog,
    LoginAuditLog,
    Job,
    AuditLog,
    DocumentSequence,
    Attachment,
    Notification,
    OutboxEvent,
    EventDelivery,
    WorkflowDefinition,
    WorkflowStep,
    ApprovalRequest,
    ApprovalAction,
    KenyaCounty,
    KenyaBank,
    Party,
    UnitOfMeasure,
    UOMConversion,
    TaxRate,
    Currency,
    ExchangeRate,
)


@admin.register(KenyaCounty)
class KenyaCountyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'capital', 'region']
    list_filter = ['region']
    search_fields = ['code', 'name']


@admin.register(KenyaBank)
class KenyaBankAdmin(admin.ModelAdmin):
    list_display = ['bank_code', 'name', 'swift_code', 'paybill_number', 'is_active']
    list_filter = ['is_active']
    search_fields = ['bank_code', 'name', 'paybill_number']


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'party_type', 'company', 'tax_pin', 'phone', 'credit_limit', 'is_active']
    list_filter = ['party_type', 'is_active', 'payment_terms', 'company']
    search_fields = ['code', 'name', 'tax_pin', 'phone', 'email']


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'category', 'is_base_unit', 'company', 'is_active']
    list_filter = ['category', 'is_base_unit', 'is_active', 'company']
    search_fields = ['code', 'name']


@admin.register(UOMConversion)
class UOMConversionAdmin(admin.ModelAdmin):
    list_display = ['from_uom', 'to_uom', 'conversion_factor', 'company']
    list_filter = ['company']
    search_fields = ['from_uom__name', 'to_uom__name']


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'rate', 'tax_type', 'kra_etims_code', 'is_default', 'is_active', 'company']
    list_filter = ['tax_type', 'is_default', 'is_active', 'company']
    search_fields = ['code', 'name', 'kra_etims_code']


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'symbol', 'decimal_places', 'is_active']
    list_filter = ['is_active']
    search_fields = ['code', 'name']


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['from_currency', 'to_currency', 'rate', 'effective_date', 'company', 'source']
    list_filter = ['from_currency', 'to_currency', 'company']
    search_fields = ['from_currency__code', 'to_currency__code']



@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'kra_pin', 'currency', 'city', 'county', 'is_active', 'created_at']
    list_filter = ['is_active', 'county', 'currency']
    search_fields = ['name', 'legal_name', 'kra_pin', 'registration_number']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'company', 'is_headquarters', 'city', 'county', 'is_active']
    list_filter = ['is_active', 'is_headquarters', 'company']
    search_fields = ['name', 'code', 'company__name']


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'company', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'company']
    search_fields = ['user__username', 'user__email', 'company__name']


@admin.register(BranchMembership)
class BranchMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'branch', 'is_primary', 'is_active', 'branch_role']
    list_filter = ['is_primary', 'is_active', 'branch__company']
    search_fields = ['user__username', 'branch__name']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'last_active_company', 'last_active_branch', 'failed_login_attempts', 'locked_until']
    search_fields = ['user__username', 'user__email', 'phone']


@admin.register(ModuleActivation)
class ModuleActivationAdmin(admin.ModelAdmin):
    list_display = ['module_key', 'company', 'is_enabled', 'enabled_by', 'updated_at']
    list_filter = ['is_enabled', 'module_key', 'company']
    search_fields = ['module_key', 'company__name']


@admin.register(CoreSetting)
class CoreSettingAdmin(admin.ModelAdmin):
    list_display = ['module_key', 'key', 'company', 'branch', 'value_type', 'raw_value']
    list_filter = ['module_key', 'value_type', 'company']
    search_fields = ['module_key', 'key', 'raw_value']


@admin.register(SensitiveDataAccessLog)
class SensitiveDataAccessLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'company', 'action', 'entity_type', 'entity_id', 'fields_accessed']
    list_filter = ['action', 'entity_type', 'company']
    search_fields = ['user__username', 'entity_id', 'reason']
    readonly_fields = [f.name for f in SensitiveDataAccessLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoginAuditLog)
class LoginAuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'username', 'is_successful', 'ip_address', 'failure_reason']
    list_filter = ['is_successful']
    search_fields = ['username', 'ip_address']
    readonly_fields = [f.name for f in LoginAuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ['name', 'status', 'priority', 'progress', 'attempts', 'max_attempts', 'scheduled_at', 'started_at', 'completed_at']
    list_filter = ['status', 'priority', 'company']
    search_fields = ['name', 'task_path', 'error_message']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'company', 'action', 'content_type', 'object_id', 'object_repr']
    list_filter = ['action', 'content_type', 'company']
    search_fields = ['object_repr', 'user__username', 'ip_address']
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ['document_type', 'prefix', 'fiscal_year', 'current_number', 'company', 'branch', 'format_pattern']
    list_filter = ['document_type', 'fiscal_year', 'company']
    search_fields = ['prefix', 'document_type', 'company__name']


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'content_type', 'object_id', 'file_size_bytes', 'mime_type', 'company', 'uploaded_by', 'created_at']
    list_filter = ['mime_type', 'company']
    search_fields = ['original_filename', 'description']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'recipient', 'notification_type', 'channel', 'is_read', 'created_at']
    list_filter = ['notification_type', 'channel', 'is_read', 'company']
    search_fields = ['title', 'message', 'recipient__username']


class WorkflowStepInline(admin.TabularInline):
    model = WorkflowStep
    extra = 1


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'company', 'content_type', 'is_active']
    list_filter = ['is_active', 'company']
    search_fields = ['name', 'code']
    inlines = [WorkflowStepInline]


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'company', 'content_type', 'object_id', 'requested_by', 'current_step', 'status', 'created_at']
    list_filter = ['status', 'workflow', 'company']
    search_fields = ['object_id', 'requested_by__username']


@admin.register(ApprovalAction)
class ApprovalActionAdmin(admin.ModelAdmin):
    list_display = ['request', 'actor', 'action', 'timestamp']
    list_filter = ['action']
    search_fields = ['actor__username', 'comments']


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ['event_name', 'status', 'attempts', 'max_attempts', 'created_at', 'dispatched_at']
    list_filter = ['status', 'event_name', 'company']
    search_fields = ['event_name', 'payload']


@admin.register(EventDelivery)
class EventDeliveryAdmin(admin.ModelAdmin):
    list_display = ['event', 'subscriber_name', 'status', 'attempt_number', 'timestamp']
    list_filter = ['status']
    search_fields = ['subscriber_name', 'error_message']
