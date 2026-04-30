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
    LoyaltyReward, LoyaltyRedemption, PaymentMethod, SalePayment
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
