"""
API Serializers for POS System
Handles serialization/deserialization for REST API
"""

from rest_framework import serializers
from django.conf import settings
from django.db.models import Q
from django.contrib.auth.models import User
from .models import (
    Product, Category, Sale, SaleItem, Customer, Supplier,
    Purchase, PurchaseItem, StockAdjustment, UserProfile,
    BusinessSettings, ActivityLog, LoyaltyTransaction,
    LoyaltyReward, LoyaltyRedemption, PaymentMethod, SalePayment, VATCode,
    Branch, BranchStock, StockMovement, StockRequisition, StockRequisitionItem,
    StockTransferRequest, StockTransferItem, Dispatch, DispatchItem, POSTerminal
)


class UserSerializer(serializers.ModelSerializer):
    """User serializer with profile info"""
    profile = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'profile']
        read_only_fields = ['id']
    
    def get_profile(self, obj):
        try:
            profile = obj.userprofile
            return {
                'role': profile.role,
                'phone': profile.phone,
                'can_view_reports': profile.can_view_reports,
                'can_manage_inventory': profile.can_manage_inventory,
                'can_manage_users': profile.can_manage_users,
                'can_process_returns': profile.can_process_returns,
                'can_give_discounts': profile.can_give_discounts,
                'max_discount_percent': str(profile.max_discount_percent),
            }
        except UserProfile.DoesNotExist:
            return None


class CategorySerializer(serializers.ModelSerializer):
    """Category serializer"""
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'product_count', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_product_count(self, obj):
        return obj.product_set.count()


class VATCodeSerializer(serializers.ModelSerializer):
    """VAT Code serializer with tax calculations"""
    total_tax_rate = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()
    business_name = serializers.CharField(source='business.name', read_only=True)
    
    class Meta:
        model = VATCode
        fields = [
            'id', 'code', 'name', 'vat_rate', 'excise_rate', 'import_duty',
            'total_tax_rate', 'is_excisable', 'hs_code_chapter', 'description',
            'is_active', 'product_count', 'business_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'business_name']
    
    def get_total_tax_rate(self, obj):
        """Calculate and return total tax rate"""
        return float(obj.get_total_tax_rate())
    
    def get_product_count(self, obj):
        """Get count of products using this VAT code"""
        return obj.products.filter(is_active=True).count()
    
    def validate_code(self, value):
        """Validate VAT code is unique within business"""
        normalized = (value or '').strip().upper()
        if not normalized:
            raise serializers.ValidationError('VAT code is required.')
        
        business = self.context.get('business')
        if business is None and self.instance is not None:
            business = self.instance.business
        
        instance_pk = self.instance.pk if self.instance else None
        existing = VATCode.objects.filter(
            business=business,
            code__iexact=normalized
        )
        if instance_pk:
            existing = existing.exclude(pk=instance_pk)
        
        if existing.exists():
            raise serializers.ValidationError(f'VAT code "{normalized}" already exists in this business.')
        
        return normalized
    
    def validate_name(self, value):
        """Validate name is provided"""
        normalized = (value or '').strip()
        if not normalized:
            raise serializers.ValidationError('VAT code name is required.')
        return normalized
    
    def validate(self, attrs):
        """Validate VAT rates are within acceptable range"""
        # Validate VAT rate
        vat_rate = attrs.get('vat_rate')
        if vat_rate is not None:
            from decimal import Decimal
            if not (Decimal('0') <= vat_rate <= Decimal('100')):
                raise serializers.ValidationError({'vat_rate': 'VAT rate must be between 0 and 100'})
        
        # Validate excise rate
        excise_rate = attrs.get('excise_rate')
        if excise_rate is not None:
            from decimal import Decimal
            if not (Decimal('0') <= excise_rate <= Decimal('100')):
                raise serializers.ValidationError({'excise_rate': 'Excise rate must be between 0 and 100'})
        
        # Validate import duty
        import_duty = attrs.get('import_duty')
        if import_duty is not None:
            from decimal import Decimal
            if not (Decimal('0') <= import_duty <= Decimal('100')):
                raise serializers.ValidationError({'import_duty': 'Import duty must be between 0 and 100'})
        
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    """Product serializer with sync metadata"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'product_code', 'barcode', 'category', 'category_name',
            'unit_price', 'cost_price', 'stock_quantity', 'low_stock_threshold',
            'unit', 'expiry_date', 'expiry_alert_days',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_name(self, value):
        normalized = (value or '').strip()
        if not normalized:
            raise serializers.ValidationError('Product name is required.')
        return normalized

    def validate(self, attrs):
        business = self.context.get('business')
        if business is None and self.instance is not None:
            business = self.instance.business

        if business is None:
            raise serializers.ValidationError({'business': 'Business context is required.'})

        instance_pk = self.instance.pk if self.instance else None

        category = attrs.get('category')
        if category is not None and category.business_id != business.id:
            raise serializers.ValidationError({'category': 'Selected category does not belong to this business.'})

        unit = attrs.get('unit')
        if unit is not None and unit.business_id != business.id:
            raise serializers.ValidationError({'unit': 'Selected unit does not belong to this business.'})

        product_code = attrs.get('product_code', getattr(self.instance, 'product_code', None))
        barcode = attrs.get('barcode', getattr(self.instance, 'barcode', ''))
        name = attrs.get('name', getattr(self.instance, 'name', ''))

        normalized_code = (product_code or '').strip() or None
        normalized_barcode = (barcode or '').strip()

        attrs['name'] = (name or '').strip()
        attrs['product_code'] = normalized_code
        attrs['barcode'] = normalized_barcode

        product_qs = Product.objects.filter(business=business)
        if instance_pk is not None:
            product_qs = product_qs.exclude(pk=instance_pk)

        if normalized_code and product_qs.filter(product_code__iexact=normalized_code).exists():
            raise serializers.ValidationError({'product_code': 'This product code already exists in your business.'})

        if normalized_barcode:
            if product_qs.filter(Q(barcode__iexact=normalized_barcode) | Q(unit_barcode__iexact=normalized_barcode)).exists():
                raise serializers.ValidationError({'barcode': 'This barcode is already used by another product barcode or unit barcode in your business.'})

        return attrs


class CustomerSerializer(serializers.ModelSerializer):
    """Customer serializer with loyalty info"""
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'email', 'phone', 'address', 'date_of_birth', 'loyalty_points',
            'lifetime_points', 'tier', 'total_purchases', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_purchases']
    
    def validate_date_of_birth(self, value):
        """Validate that customer is at least 18 years old"""
        if value:
            from django.utils import timezone
            today = timezone.now().date()
            age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
            
            if age < 18:
                raise serializers.ValidationError(
                    f'Customer must be at least 18 years old. Current age: {age} years.'
                )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)

        business = self.context.get('business')
        if business is None:
            request = self.context.get('request')
            business = getattr(request, 'business', None) if request else None

        phone = Customer.normalize_phone(attrs.get('phone', getattr(self.instance, 'phone', '')))
        attrs['phone'] = phone

        if getattr(settings, 'ENFORCE_UNIQUE_CUSTOMER_PHONE', True) and business and phone:
            duplicate_customer = Customer.find_duplicate_by_phone(
                business,
                phone,
                exclude_pk=self.instance.pk if self.instance is not None else None,
            )
            if duplicate_customer is not None:
                raise serializers.ValidationError({'phone': 'This phone number is already used by another customer in this business.'})

        return attrs


class SupplierSerializer(serializers.ModelSerializer):
    """Supplier serializer"""
    
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'contact_person', 'email', 'phone', 'address', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class SaleItemSerializer(serializers.ModelSerializer):
    """Sale item serializer"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = SaleItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'total_price', 'note']
        read_only_fields = ['id', 'subtotal']


class SalePaymentSerializer(serializers.ModelSerializer):
    """Sale payment serializer"""
    payment_method_name = serializers.CharField(source='payment_method.name', read_only=True)
    
    class Meta:
        model = SalePayment
        fields = ['id', 'payment_method', 'payment_method_name', 'amount', 'reference_number']
        read_only_fields = ['id']


class SaleSerializer(serializers.ModelSerializer):
    """Sale serializer with items and payments"""
    items = SaleItemSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True, allow_null=True)
    cashier_name = serializers.CharField(source='cashier.username', read_only=True, allow_null=True)
    sale_number = serializers.CharField(source='invoice_number', read_only=True)
    
    class Meta:
        model = Sale
        fields = [
            'id', 'sale_number', 'customer', 'customer_name', 'cashier', 'cashier_name',
            'subtotal', 'vat_amount', 'discount_amount', 'total', 'amount_paid', 'change_given',
            'created_at', 'updated_at', 'items', 'payments'
        ]
        read_only_fields = ['id', 'sale_number', 'created_at', 'updated_at']


class PurchaseItemSerializer(serializers.ModelSerializer):
    """Purchase item serializer"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = PurchaseItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_cost', 'subtotal']
        read_only_fields = ['id', 'subtotal']


class PurchaseSerializer(serializers.ModelSerializer):
    """Purchase serializer with items"""
    items = PurchaseItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, allow_null=True)
    
    class Meta:
        model = Purchase
        fields = [
            'id', 'purchase_number', 'supplier', 'supplier_name', 'total_amount',
            'status', 'notes', 'date', 'expected_delivery', 'received_date',
            'created_at', 'updated_at', 'items'
        ]
        read_only_fields = ['id', 'purchase_number', 'created_at', 'updated_at']


class StockAdjustmentSerializer(serializers.ModelSerializer):
    """Stock adjustment serializer"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    user_name = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = StockAdjustment
        fields = [
            'id', 'product', 'product_name', 'adjustment_type', 'quantity',
            'reason', 'user', 'user_name', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class LoyaltyTransactionSerializer(serializers.ModelSerializer):
    """Loyalty transaction serializer"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = LoyaltyTransaction
        fields = [
            'id', 'customer', 'customer_name', 'transaction_type', 'points',
            'description', 'sale', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class LoyaltyRewardSerializer(serializers.ModelSerializer):
    """Loyalty reward serializer"""
    
    class Meta:
        model = LoyaltyReward
        fields = [
            'id', 'name', 'description', 'points_required', 'reward_type',
            'discount_value', 'product', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Payment method serializer"""
    
    class Meta:
        model = PaymentMethod
        fields = ['id', 'name', 'code', 'is_active']
        read_only_fields = ['id']


class BusinessSettingsSerializer(serializers.ModelSerializer):
    """Business settings serializer"""
    
    class Meta:
        model = BusinessSettings
        fields = [
            'id', 'business_name', 'business_address', 'business_phone', 'business_email', 'tax_id',
            'vat_rate', 'receipt_footer', 'logo', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ActivityLogSerializer(serializers.ModelSerializer):
    """Activity log serializer"""
    user_name = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = ['id', 'user', 'user_name', 'action', 'model_name', 'object_id', 'details', 'created_at']
        read_only_fields = ['id', 'created_at']


# Sync-specific serializers

class SyncMetadataSerializer(serializers.Serializer):
    """Metadata for sync operations"""
    last_sync = serializers.DateTimeField()
    device_id = serializers.CharField(max_length=100)
    sync_version = serializers.IntegerField(default=1)


class SyncRequestSerializer(serializers.Serializer):
    """Request payload for sync operations"""
    last_sync = serializers.DateTimeField(allow_null=True, required=False)
    device_id = serializers.CharField(max_length=100)
    models = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of models to sync. If empty, sync all."
    )


class SyncResponseSerializer(serializers.Serializer):
    """Response payload for sync operations"""
    timestamp = serializers.DateTimeField()
    products = ProductSerializer(many=True, required=False)
    categories = CategorySerializer(many=True, required=False)
    customers = CustomerSerializer(many=True, required=False)
    suppliers = SupplierSerializer(many=True, required=False)
    sales = SaleSerializer(many=True, required=False)
    purchases = PurchaseSerializer(many=True, required=False)
    payment_methods = PaymentMethodSerializer(many=True, required=False)
    has_more = serializers.BooleanField(default=False)


# ============================================================================
# MULTI-BRANCH DISTRIBUTION & STOCK LEDGER SERIALIZERS
# ============================================================================

class BranchStockSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.product_code', read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    stock_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = BranchStock
        fields = [
            'id', 'branch', 'branch_name', 'product', 'product_name', 'product_code',
            'quantity', 'average_cost', 'reorder_level', 'is_low_stock', 'stock_value', 'updated_at'
        ]
        read_only_fields = ['id', 'quantity', 'average_cost', 'updated_at']


class StockMovementSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.product_code', read_only=True)
    performed_by_name = serializers.CharField(source='performed_by.username', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'branch', 'branch_name', 'product', 'product_name', 'product_code',
            'quantity_delta', 'unit_cost', 'total_cost', 'movement_type', 'movement_type_display',
            'reference_number', 'balance_after', 'resulted_in_negative_stock',
            'performed_by', 'performed_by_name', 'note', 'created_at'
        ]
        read_only_fields = fields


class StockRequisitionItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.product_code', read_only=True)

    class Meta:
        model = StockRequisitionItem
        fields = [
            'id', 'product', 'product_name', 'product_code',
            'requested_quantity', 'approved_quantity',
            'dispatched_quantity', 'received_quantity', 'notes'
        ]
        read_only_fields = ['id', 'dispatched_quantity', 'received_quantity']


class StockRequisitionSerializer(serializers.ModelSerializer):
    items = StockRequisitionItemSerializer(many=True, required=False)
    requesting_branch_name = serializers.CharField(source='requesting_branch.name', read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.username', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = StockRequisition
        fields = [
            'id', 'reference_number', 'requesting_branch', 'requesting_branch_name',
            'requested_by', 'requested_by_name', 'approved_by', 'approved_by_name',
            'status', 'status_display', 'notes', 'rejection_reason',
            'items', 'created_at', 'updated_at', 'approved_at'
        ]
        read_only_fields = ['id', 'reference_number', 'requested_by', 'approved_by', 'status', 'created_at', 'updated_at', 'approved_at']


class StockTransferItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.product_code', read_only=True)

    class Meta:
        model = StockTransferItem
        fields = [
            'id', 'product', 'product_name', 'product_code',
            'requested_quantity', 'approved_quantity',
            'dispatched_quantity', 'received_quantity', 'notes'
        ]
        read_only_fields = ['id', 'dispatched_quantity', 'received_quantity']


class StockTransferRequestSerializer(serializers.ModelSerializer):
    items = StockTransferItemSerializer(many=True, required=False)
    source_branch_name = serializers.CharField(source='source_branch.name', read_only=True)
    destination_branch_name = serializers.CharField(source='destination_branch.name', read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.username', read_only=True)
    approved_by_name = serializers.CharField(source='approved_by.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = StockTransferRequest
        fields = [
            'id', 'reference_number', 'source_branch', 'source_branch_name',
            'destination_branch', 'destination_branch_name',
            'requested_by', 'requested_by_name', 'approved_by', 'approved_by_name',
            'reason', 'rejection_reason', 'status', 'status_display',
            'items', 'created_at', 'updated_at', 'approved_at'
        ]
        read_only_fields = ['id', 'reference_number', 'requested_by', 'approved_by', 'status', 'created_at', 'updated_at', 'approved_at']


class DispatchItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.product_code', read_only=True)

    class Meta:
        model = DispatchItem
        fields = [
            'id', 'product', 'product_name', 'product_code',
            'dispatched_quantity', 'unit_cost',
            'received_quantity', 'discrepancy_quantity', 'discrepancy_reason'
        ]
        read_only_fields = ['id', 'unit_cost', 'discrepancy_quantity']


class DispatchSerializer(serializers.ModelSerializer):
    items = DispatchItemSerializer(many=True, read_only=True)
    source_branch_name = serializers.CharField(source='source_branch.name', read_only=True)
    destination_branch_name = serializers.CharField(source='destination_branch.name', read_only=True)
    dispatched_by_name = serializers.CharField(source='dispatched_by.username', read_only=True)
    received_by_name = serializers.CharField(source='received_by.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Dispatch
        fields = [
            'id', 'reference_number', 'source_branch', 'source_branch_name',
            'destination_branch', 'destination_branch_name',
            'requisition', 'transfer_request',
            'dispatched_by', 'dispatched_by_name', 'dispatched_at',
            'received_by', 'received_by_name', 'received_at',
            'status', 'status_display', 'notes', 'items'
        ]
        read_only_fields = ['id', 'reference_number', 'dispatched_by', 'dispatched_at', 'received_by', 'received_at', 'status']


class POSTerminalSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = POSTerminal
        fields = [
            'id', 'name', 'terminal_code', 'device_token', 'branch', 'branch_name',
            'ip_address', 'is_active', 'last_active_at', 'last_sync_at', 'sync_status',
            'cu_number', 'cu_serial_number', 'tims_middleware_url', 'created_at'
        ]
        read_only_fields = ['id', 'device_token', 'last_active_at', 'last_sync_at', 'created_at']


