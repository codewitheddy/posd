from django.contrib import admin
from .models import (
    Category, Product, Sale, SaleItem, StockAdjustment, 
    Supplier, Purchase, PurchaseItem, UserProfile, 
    BusinessSettings, ActivityLog, Customer, PaymentMethod,
    SalePayment, Shift, SaleReturn, SaleReturnItem, Promotion,
    ExpenseCategory, Expense, LoyaltyTransaction, LoyaltyReward,
    LoyaltyRedemption, SupplierPayment, PaymentAllocation
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
        # Only allow one instance
        return not BusinessSettings.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # Don't allow deletion
        return False


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
