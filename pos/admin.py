from django.contrib import admin
from .models import (
    Category, Product, Sale, SaleItem, StockAdjustment, 
    Supplier, Purchase, PurchaseItem, UserProfile, 
    BusinessSettings, ActivityLog, Customer, PaymentMethod,
    SalePayment, Shift, SaleReturn, SaleReturnItem, Promotion,
    ExpenseCategory, Expense, LoyaltyTransaction, LoyaltyReward,
    LoyaltyRedemption, SupplierPayment, PaymentAllocation,
    Business, BusinessMembership, SubscriptionPayment, DayClosureReport,
    SupportAccessRequest
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'product_code', 'category', 'unit_price', 'stock_quantity', 'stock_status', 'created_at']
    list_filter = ['category']
    search_fields = ['name', 'product_code']
    
    def stock_status(self, obj):
        if obj.is_out_of_stock():
            return '🔴 Out of Stock'
        elif obj.is_low_stock():
            return '🟡 Low Stock'
        else:
            return '🟢 In Stock'
    stock_status.short_description = 'Status'


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ['total_price']


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'date', 'subtotal', 'vat_amount', 'discount_amount', 'total']
    list_filter = ['date']
    search_fields = ['invoice_number']
    readonly_fields = ['invoice_number', 'created_at']
    inlines = [SaleItemInline]


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['product', 'adjustment_type', 'quantity_change', 'previous_quantity', 'new_quantity', 'created_at']
    list_filter = ['adjustment_type', 'created_at']
    search_fields = ['product__name', 'reason']
    readonly_fields = ['previous_quantity', 'new_quantity', 'created_at']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'email', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'contact_person', 'email', 'phone']
    list_per_page = 20


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1
    fields = ['product', 'quantity', 'unit_cost', 'total_cost']
    readonly_fields = ['total_cost']


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ['purchase_number', 'supplier', 'date', 'status', 'total_amount', 'expected_delivery']
    list_filter = ['status', 'date']
    search_fields = ['purchase_number', 'supplier__name']
    readonly_fields = ['purchase_number', 'created_at', 'updated_at', 'received_date']
    inlines = [PurchaseItemInline]
    list_per_page = 20
    fieldsets = (
        ('Purchase Information', {
            'fields': ('purchase_number', 'supplier', 'date', 'expected_delivery', 'status')
        }),
        ('Financial Details', {
            'fields': ('subtotal', 'tax_amount', 'total_amount')
        }),
        ('Additional Information', {
            'fields': ('notes', 'received_date', 'created_at', 'updated_at')
        }),
    )



@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'employee_id', 'phone', 'hire_date', 'is_active']
    list_filter = ['is_active', 'hire_date']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'employee_id', 'phone']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'vat_rate', 'currency_symbol', 'updated_at']
    readonly_fields = ['updated_at']
    
    def has_add_permission(self, request):
        # Only allow one instance per business (handled by OneToOne relationship)
        return True
    
    def has_delete_permission(self, request, obj=None):
        # Allow deletion (will cascade when business is deleted)
        return request.user.is_superuser


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action_type', 'model_name', 'description', 'ip_address']
    list_filter = ['action_type', 'timestamp', 'model_name']
    search_fields = ['user__username', 'description', 'ip_address']
    readonly_fields = ['user', 'action_type', 'model_name', 'object_id', 'description', 'ip_address', 'timestamp']
    date_hierarchy = 'timestamp'
    list_per_page = 50
    
    def has_add_permission(self, request):
        # Don't allow manual creation
        return False
    
    def has_change_permission(self, request, obj=None):
        # Don't allow editing
        return False



@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['customer_code', 'name', 'phone', 'tier', 'customer_type', 'loyalty_points', 'lifetime_points', 'total_purchases', 'is_active']
    list_filter = ['tier', 'customer_type', 'is_active', 'created_at']
    search_fields = ['customer_code', 'name', 'phone', 'email']
    readonly_fields = ['customer_code', 'loyalty_points', 'lifetime_points', 'tier', 'total_purchases', 'visit_count', 'created_at', 'updated_at']


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = ['customer', 'transaction_type', 'points', 'amount', 'description', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['customer__name', 'customer__customer_code', 'description']
    readonly_fields = ['customer', 'transaction_type', 'points', 'amount', 'sale', 'description', 'created_by', 'created_at']
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LoyaltyReward)
class LoyaltyRewardAdmin(admin.ModelAdmin):
    list_display = ['name', 'reward_type', 'points_required', 'discount_value', 'is_active', 'redemption_count', 'max_redemptions']
    list_filter = ['reward_type', 'is_active']
    search_fields = ['name', 'description']
    list_editable = ['is_active']


@admin.register(LoyaltyRedemption)
class LoyaltyRedemptionAdmin(admin.ModelAdmin):
    list_display = ['customer', 'reward', 'points_used', 'redeemed_at', 'redeemed_by']
    list_filter = ['redeemed_at']
    search_fields = ['customer__name', 'reward__name']
    readonly_fields = ['customer', 'reward', 'points_used', 'sale', 'redeemed_at', 'redeemed_by']
    date_hierarchy = 'redeemed_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'requires_reference']
    list_filter = ['is_active']
    search_fields = ['name', 'code']


@admin.register(SalePayment)
class SalePaymentAdmin(admin.ModelAdmin):
    list_display = ['sale', 'payment_method', 'amount', 'reference_number', 'created_at']
    list_filter = ['payment_method', 'created_at']
    search_fields = ['sale__invoice_number', 'reference_number']
    readonly_fields = ['created_at']


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['shift_number', 'cashier', 'start_time', 'end_time', 'status', 'total_sales', 'total_revenue', 'cash_difference']
    list_filter = ['status', 'start_time', 'cashier']
    search_fields = ['shift_number', 'cashier__username']
    readonly_fields = ['shift_number', 'start_time', 'expected_cash', 'cash_difference', 'total_sales', 'total_revenue']


@admin.register(DayClosureReport)
class DayClosureReportAdmin(admin.ModelAdmin):
    list_display = ['report_date', 'business', 'closed_by', 'closed_at', 'declared_cash', 'expected_cash', 'variance', 'variance_status_display', 'total_transactions']
    list_filter = ['business', 'report_date', 'closed_by']
    search_fields = ['business__name', 'closed_by__username']
    readonly_fields = ['closed_at', 'variance']
    date_hierarchy = 'report_date'
    
    def variance_status_display(self, obj):
        if obj.is_balanced:
            return '✅ Balanced'
        elif obj.is_over:
            return f'⚠️ Over by KES {obj.variance:.2f}'
        else:
            return f'❌ Short by KES {abs(obj.variance):.2f}'
    variance_status_display.short_description = 'Status'


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ['return_number', 'original_sale', 'return_date', 'total_refund', 'reason', 'processed_by']
    list_filter = ['reason', 'return_date']
    search_fields = ['return_number', 'original_sale__invoice_number']
    readonly_fields = ['return_number', 'return_date']


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'discount_type', 'discount_value', 'start_date', 'end_date', 'is_active', 'uses_count']
    list_filter = ['discount_type', 'is_active', 'start_date']
    search_fields = ['name', 'code']
    filter_horizontal = ['applicable_products', 'applicable_categories']


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['expense_number', 'category', 'description', 'amount', 'expense_date', 'recorded_by']
    list_filter = ['category', 'expense_date', 'payment_method']
    search_fields = ['expense_number', 'description', 'reference_number']
    readonly_fields = ['expense_number', 'created_at']
    date_hierarchy = 'expense_date'


# ==================== SUPPLIER PAYMENT ADMIN ====================

class PaymentAllocationInline(admin.TabularInline):
    model = PaymentAllocation
    extra = 0
    readonly_fields = ['created_at']
    autocomplete_fields = ['purchase']


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'supplier', 'payment_date', 'amount', 'payment_method', 'created_by', 'created_at']
    list_filter = ['payment_date', 'payment_method', 'supplier']
    search_fields = ['payment_number', 'supplier__name', 'reference_number']
    readonly_fields = ['payment_number', 'created_at', 'updated_at', 'created_by']
    inlines = [PaymentAllocationInline]
    date_hierarchy = 'payment_date'
    
    fieldsets = (
        ('Payment Information', {
            'fields': ('payment_number', 'supplier', 'payment_date', 'amount')
        }),
        ('Payment Details', {
            'fields': ('payment_method', 'reference_number', 'notes')
        }),
        ('Audit Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Only set created_by on creation
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = ['payment', 'purchase', 'amount', 'created_at']
    list_filter = ['created_at']
    search_fields = ['payment__payment_number', 'purchase__purchase_number']
    readonly_fields = ['created_at']
    autocomplete_fields = ['payment', 'purchase']


# ==================== MULTI-TENANCY ADMIN ====================

class BusinessMembershipInline(admin.TabularInline):
    model = BusinessMembership
    extra = 0
    readonly_fields = ['joined_at']
    autocomplete_fields = ['user']


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'owner', 'subscription_plan', 'activation_status', 'is_trial', 'created_at']
    list_filter = ['is_active', 'is_trial', 'subscription_plan', 'created_at']
    search_fields = ['name', 'slug', 'owner__username', 'owner__email']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [BusinessMembershipInline]
    actions = ['deactivate_businesses', 'activate_businesses']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'owner', 'description')
        }),
        ('Contact Details', {
            'fields': ('email', 'phone', 'address', 'website', 'tax_id')
        }),
        ('Subscription', {
            'fields': ('subscription_plan', 'is_trial', 'trial_ends_at')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_prepopulated_fields(self, request, obj=None):
        """Only prepopulate slug when creating new business"""
        if obj is None:  # Creating new object
            return {'slug': ('name',)}
        return {}  # Editing existing object - no prepopulation
    
    def get_readonly_fields(self, request, obj=None):
        """Make slug readonly only when editing existing business"""
        if obj:  # Editing existing object
            return ['slug', 'created_at', 'updated_at']
        return ['created_at', 'updated_at']  # Creating new object
    
    def save_model(self, request, obj, form, change):
        """Ensure slug is generated and membership is created"""
        super().save_model(request, obj, form, change)
        
        # Create owner membership if this is a new business
        if not change:
            BusinessMembership.objects.get_or_create(
                user=obj.owner,
                business=obj,
                defaults={'role': 'owner', 'is_active': True}
            )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('owner')
    
    def activation_status(self, obj):
        """Display activation status with visual indicator"""
        if obj.is_active:
            return '✅ Active'
        else:
            return '⏳ Pending Activation'
    activation_status.short_description = 'Status'
    activation_status.admin_order_field = 'is_active'
    
    def deactivate_businesses(self, request, queryset):
        """Deactivate selected businesses (soft delete)"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'{count} business(es) have been deactivated.')
    deactivate_businesses.short_description = "Deactivate selected businesses (soft delete)"
    
    def activate_businesses(self, request, queryset):
        """Activate selected businesses and send activation email"""
        from django.core.mail import send_mail
        from django.conf import settings
        
        activated_count = 0
        for business in queryset:
            if not business.is_active:
                business.is_active = True
                business.save()
                activated_count += 1
                
                # Send activation email to business owner
                try:
                    login_url = f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/login/"
                    
                    subject = f'Your Business "{business.name}" Has Been Activated!'
                    message = f"""
Hello {business.owner.first_name or business.owner.username},

Great news! Your business "{business.name}" has been activated and is now ready to use.

You can now log in and start using the Marid POS:
Login URL: {login_url}
Username: {business.owner.username}

Your 30-day free trial has started. Explore all features and let us know if you need any help.

Need Support?
Email: info@marid.co.ke
Phone/WhatsApp: +254 717 147 700

Best regards,
Marid POS Team
                    """
                    
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [business.owner.email],
                        fail_silently=True,  # Don't fail if email fails
                    )
                except Exception as e:
                    # Log error but don't fail the activation
                    print(f"Failed to send activation email to {business.owner.email}: {e}")
        
        self.message_user(request, f'{activated_count} business(es) have been activated and notification emails sent.')
    activate_businesses.short_description = "Activate selected businesses and notify owners"


@admin.register(BusinessMembership)
class BusinessMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'business', 'role', 'is_active', 'joined_at']
    list_filter = ['role', 'is_active', 'joined_at']
    search_fields = ['user__username', 'user__email', 'business__name']
    readonly_fields = ['joined_at']
    autocomplete_fields = ['user', 'business']
    
    fieldsets = (
        ('Membership Details', {
            'fields': ('user', 'business', 'role', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('joined_at',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'business')


@admin.register(SubscriptionPayment)
class SubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ['business', 'amount_display', 'payment_method', 'payment_date', 'period_display', 'plan', 'status']
    list_filter = ['status', 'payment_method', 'plan', 'payment_date', 'created_at']
    search_fields = ['business__name', 'business__slug', 'payment_reference', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'recorded_by']
    date_hierarchy = 'payment_date'
    
    fieldsets = (
        ('Business', {
            'fields': ('business',)
        }),
        ('Payment Details', {
            'fields': ('amount', 'currency', 'payment_method', 'payment_reference', 'payment_date', 'status')
        }),
        ('Subscription Period', {
            'fields': ('plan', 'period_start', 'period_end')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('recorded_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def amount_display(self, obj):
        return f"{obj.currency} {obj.amount:,.2f}"
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'
    
    def period_display(self, obj):
        return f"{obj.period_start} to {obj.period_end}"
    period_display.short_description = 'Period'
    
    def save_model(self, request, obj, form, change):
        """Auto-set recorded_by to current user"""
        if not change:  # Only on creation
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('business', 'recorded_by')
    
    actions = ['mark_as_completed', 'mark_as_pending', 'export_payments']
    
    def mark_as_completed(self, request, queryset):
        """Mark selected payments as completed and update business license"""
        count = 0
        for payment in queryset:
            payment.status = 'completed'
            payment.save()  # This will trigger the save() method which updates license
            count += 1
        self.message_user(request, f'{count} payment(s) marked as completed and licenses updated.')
    mark_as_completed.short_description = "Mark as Completed (updates license)"
    
    def mark_as_pending(self, request, queryset):
        """Mark selected payments as pending"""
        count = queryset.update(status='pending')
        self.message_user(request, f'{count} payment(s) marked as pending.')
    mark_as_pending.short_description = "Mark as Pending"
    
    def export_payments(self, request, queryset):
        """Export selected payments to CSV"""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="subscription_payments.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['Business', 'Amount', 'Currency', 'Payment Method', 'Reference', 'Payment Date', 
                        'Period Start', 'Period End', 'Plan', 'Status', 'Notes', 'Recorded By'])
        
        for payment in queryset:
            writer.writerow([
                payment.business.name,
                payment.amount,
                payment.currency,
                payment.get_payment_method_display(),
                payment.payment_reference,
                payment.payment_date.strftime('%Y-%m-%d %H:%M'),
                payment.period_start,
                payment.period_end,
                payment.get_plan_display(),
                payment.get_status_display(),
                payment.notes,
                payment.recorded_by.username if payment.recorded_by else ''
            ])
        
        return response
    export_payments.short_description = "Export to CSV"


@admin.register(SupportAccessRequest)
class SupportAccessRequestAdmin(admin.ModelAdmin):
    list_display = ['business', 'requested_by', 'status', 'requested_at', 'approved_by', 'expires_at']
    list_filter = ['status', 'requested_at', 'approved_at']
    search_fields = ['business__name', 'requested_by__username', 'reason']
    readonly_fields = ['requested_at', 'approved_at']
    
    fieldsets = (
        ('Request Information', {
            'fields': ('business', 'requested_by', 'requested_at', 'reason')
        }),
        ('Status', {
            'fields': ('status', 'approved_by', 'approved_at', 'expires_at')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('business', 'requested_by', 'approved_by')
