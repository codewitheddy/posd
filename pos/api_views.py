"""
API Views for POS System
RESTful endpoints for offline-first architecture
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q, F
from datetime import datetime, timedelta
from django_ratelimit.decorators import ratelimit
from .models import (
    Product, Category, Sale, SaleItem, Customer, Supplier,
    Purchase, PurchaseItem, StockAdjustment, UserProfile,
    BusinessSettings, ActivityLog, LoyaltyTransaction,
    LoyaltyReward, PaymentMethod, SalePayment
)
from .serializers import (
    ProductSerializer, CategorySerializer, SaleSerializer,
    CustomerSerializer, SupplierSerializer, PurchaseSerializer,
    StockAdjustmentSerializer, UserSerializer, BusinessSettingsSerializer,
    ActivityLogSerializer, LoyaltyTransactionSerializer, LoyaltyRewardSerializer,
    PaymentMethodSerializer, SyncRequestSerializer, SyncResponseSerializer
)
from .throttling import LoginThrottle, AuthThrottle


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom token obtain view with rate limiting for login attempts
    """
    throttle_classes = [LoginThrottle]


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view with rate limiting
    """
    throttle_classes = [AuthThrottle]


class ProductViewSet(viewsets.ModelViewSet):
    """
    API endpoint for products
    Supports filtering, searching, and pagination
    """
    queryset = Product.objects.all().select_related('category', 'brand')
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'product_code', 'barcode']
    ordering_fields = ['name', 'unit_price', 'stock_quantity', 'created_at']
    ordering = ['-created_at']

    def _get_request_business(self):
        """Resolve the business context for the current request."""
        business = getattr(self.request, 'business', None)
        if business is not None:
            return business

        if self.request.user.is_superuser:
            return None

        memberships = getattr(self.request.user, 'business_memberships', None)
        if memberships is None:
            return None

        active_memberships = memberships.filter(is_active=True).select_related('business')
        if active_memberships.count() == 1:
            return active_memberships.first().business
        return None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['business'] = self._get_request_business()
        return context
    
    def get_queryset(self):
        queryset = super().get_queryset()

        # Scope products to the current business context.
        business = getattr(self.request, 'business', None)
        if business is not None:
            queryset = queryset.filter(business=business)
        elif self.request.user.is_superuser:
            queryset = queryset
        else:
            memberships = getattr(self.request.user, 'business_memberships', None)
            if memberships is None:
                return queryset.none()
            business_ids = memberships.filter(is_active=True).values_list('business_id', flat=True)
            queryset = queryset.filter(business_id__in=business_ids)
        
        # Filter by category
        category_id = self.request.query_params.get('category', None)
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by low stock
        low_stock = self.request.query_params.get('low_stock', None)
        if low_stock == 'true':
            queryset = queryset.filter(stock_quantity__lte=F('low_stock_threshold'))
        
        # Filter by updated since (for sync)
        updated_since = self.request.query_params.get('updated_since', None)
        if updated_since:
            try:
                dt = datetime.fromisoformat(updated_since.replace('Z', '+00:00'))
                queryset = queryset.filter(updated_at__gte=dt)
            except ValueError:
                pass
        
        return queryset

    def perform_create(self, serializer):
        business = self._get_request_business()
        if business is None:
            raise ValidationError(
                'Unable to determine business for this product creation request. '
                'Use a business-scoped request context.'
            )
        serializer.save(business=business)
    
    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Get products with low stock"""
        products = self.get_queryset().filter(
            stock_quantity__lte=F('low_stock_threshold'),
            is_active=True
        )
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """Get products expiring soon"""
        days = int(request.query_params.get('days', 30))
        cutoff_date = timezone.now().date() + timedelta(days=days)
        
        products = self.get_queryset().filter(
            expiry_date__lte=cutoff_date,
            expiry_date__gte=timezone.now().date(),
            is_active=True
        )
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ModelViewSet):
    """API endpoint for categories"""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering = ['name']


class CustomerViewSet(viewsets.ModelViewSet):
    """API endpoint for customers"""
    queryset = Customer.objects.all().select_related('business')
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'email', 'phone']
    ordering_fields = ['name', 'total_purchases', 'loyalty_points', 'created_at']
    ordering = ['-created_at']

    def _get_request_business(self):
        """Resolve the business context for the current request."""
        business = getattr(self.request, 'business', None)
        if business is not None:
            return business

        if self.request.user.is_superuser:
            return None

        memberships = getattr(self.request.user, 'business_memberships', None)
        if memberships is None:
            return None

        active_memberships = memberships.filter(is_active=True).select_related('business')
        if active_memberships.count() == 1:
            return active_memberships.first().business
        return None

    def get_queryset(self):
        queryset = super().get_queryset()

        business = getattr(self.request, 'business', None)
        if business is not None:
            queryset = queryset.filter(business=business)
        elif self.request.user.is_superuser:
            queryset = queryset
        else:
            memberships = getattr(self.request.user, 'business_memberships', None)
            if memberships is None:
                return queryset.none()
            business_ids = memberships.filter(is_active=True).values_list('business_id', flat=True)
            queryset = queryset.filter(business_id__in=business_ids)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['business'] = self._get_request_business()
        return context

    def perform_create(self, serializer):
        business = self._get_request_business()
        if business is None:
            raise ValidationError(
                'Unable to determine business for this customer creation request. '
                'Use a business-scoped request context.'
            )
        serializer.save(business=business)
    
    @action(detail=True, methods=['post'])
    def add_points(self, request, pk=None):
        """Add loyalty points to customer"""
        customer = self.get_object()
        points = request.data.get('points', 0)
        description = request.data.get('description', 'Manual adjustment')
        
        if points > 0:
            customer.loyalty_points += points
            customer.lifetime_points += points
            customer.save()
            
            LoyaltyTransaction.objects.create(
                customer=customer,
                transaction_type='earn',
                points=points,
                description=description
            )
            
            return Response({'status': 'points added', 'new_balance': customer.loyalty_points})
        return Response({'error': 'Invalid points value'}, status=status.HTTP_400_BAD_REQUEST)


class SupplierViewSet(viewsets.ModelViewSet):
    """API endpoint for suppliers"""
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'contact_person', 'email', 'phone']
    ordering = ['name']

    def get_queryset(self):
        queryset = super().get_queryset()

        # Prefer middleware-provided business context.
        business = getattr(self.request, 'business', None)
        if business is not None:
            return queryset.filter(business=business)

        # Fallback for API clients: scope by active business memberships.
        if self.request.user.is_superuser:
            return queryset

        memberships = getattr(self.request.user, 'business_memberships', None)
        if memberships is None:
            return queryset.none()

        business_ids = memberships.filter(is_active=True).values_list('business_id', flat=True)
        return queryset.filter(business_id__in=business_ids)


class SaleViewSet(viewsets.ModelViewSet):
    """API endpoint for sales"""
    queryset = Sale.objects.all().select_related('customer', 'cashier').prefetch_related('items', 'payments')
    serializer_class = SaleSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['created_at', 'total']
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date', None)
        end_date = self.request.query_params.get('end_date', None)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Filter by customer
        customer_id = self.request.query_params.get('customer', None)
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        
        # Filter by cashier
        cashier_id = self.request.query_params.get('cashier', None)
        if cashier_id:
            queryset = queryset.filter(cashier_id=cashier_id)
        
        # Filter by updated since (for sync)
        updated_since = self.request.query_params.get('updated_since', None)
        if updated_since:
            try:
                dt = datetime.fromisoformat(updated_since.replace('Z', '+00:00'))
                queryset = queryset.filter(updated_at__gte=dt)
            except ValueError:
                pass
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's sales"""
        today = timezone.now().date()
        sales = self.queryset.filter(created_at__date=today)
        serializer = self.get_serializer(sales, many=True)
        return Response(serializer.data)


class PurchaseViewSet(viewsets.ModelViewSet):
    """API endpoint for purchases"""
    queryset = Purchase.objects.all().select_related('supplier').prefetch_related('items')
    serializer_class = PurchaseSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order_date', 'total_amount']
    ordering = ['-order_date']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by supplier
        supplier_id = self.request.query_params.get('supplier', None)
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        return queryset


class StockAdjustmentViewSet(viewsets.ModelViewSet):
    """API endpoint for stock adjustments"""
    queryset = StockAdjustment.objects.all().select_related('product', 'user')
    serializer_class = StockAdjustmentSerializer
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class PaymentMethodViewSet(viewsets.ModelViewSet):
    """API endpoint for payment methods"""
    queryset = PaymentMethod.objects.filter(is_active=True)
    serializer_class = PaymentMethodSerializer
    ordering = ['name']


class LoyaltyTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for loyalty transactions (read-only)"""
    queryset = LoyaltyTransaction.objects.all().select_related('customer', 'sale')
    serializer_class = LoyaltyTransactionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering = ['-created_at']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by customer
        customer_id = self.request.query_params.get('customer', None)
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)
        
        return queryset


class LoyaltyRewardViewSet(viewsets.ModelViewSet):
    """API endpoint for loyalty rewards"""
    serializer_class = LoyaltyRewardSerializer
    ordering = ['points_required']
    
    def get_queryset(self):
        """Filter rewards by business"""
        business = getattr(self.request, 'business', None)
        if business:
            return LoyaltyReward.objects.filter(business=business, is_active=True)
        return LoyaltyReward.objects.filter(is_active=True)


class BusinessSettingsViewSet(viewsets.ModelViewSet):
    """API endpoint for business settings"""
    queryset = BusinessSettings.objects.all()
    serializer_class = BusinessSettingsSerializer
    
    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current business settings"""
        settings = BusinessSettings.objects.first()
        if settings:
            serializer = self.get_serializer(settings)
            return Response(serializer.data)
        return Response({'error': 'No settings found'}, status=status.HTTP_404_NOT_FOUND)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoint for users (read-only)"""
    queryset = User.objects.filter(is_active=True).select_related('userprofile').prefetch_related('groups')
    serializer_class = UserSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'first_name', 'last_name', 'email']


# Sync endpoints

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def sync_pull(request):
    """
    Pull updates from server
    Returns all data updated since last_sync timestamp
    """
    last_sync = request.data.get('last_sync')
    device_id = request.data.get('device_id')
    models_to_sync = request.data.get('models', [])
    
    if last_sync:
        try:
            last_sync_dt = datetime.fromisoformat(last_sync.replace('Z', '+00:00'))
        except ValueError:
            return Response({'error': 'Invalid last_sync format'}, status=status.HTTP_400_BAD_REQUEST)
    else:
        last_sync_dt = None
    
    response_data = {
        'timestamp': timezone.now().isoformat(),
        'has_more': False
    }
    
    # Sync products
    if not models_to_sync or 'products' in models_to_sync:
        products_qs = Product.objects.all()
        if last_sync_dt:
            products_qs = products_qs.filter(updated_at__gte=last_sync_dt)
        response_data['products'] = ProductSerializer(products_qs, many=True).data
    
    # Sync categories
    if not models_to_sync or 'categories' in models_to_sync:
        categories_qs = Category.objects.all()
        if last_sync_dt:
            categories_qs = categories_qs.filter(updated_at__gte=last_sync_dt)
        response_data['categories'] = CategorySerializer(categories_qs, many=True).data
    
    # Sync customers
    if not models_to_sync or 'customers' in models_to_sync:
        customers_qs = Customer.objects.all()
        if last_sync_dt:
            customers_qs = customers_qs.filter(updated_at__gte=last_sync_dt)
        response_data['customers'] = CustomerSerializer(customers_qs, many=True).data
    
    # Sync suppliers
    if not models_to_sync or 'suppliers' in models_to_sync:
        suppliers_qs = Supplier.objects.all()
        if last_sync_dt:
            suppliers_qs = suppliers_qs.filter(updated_at__gte=last_sync_dt)
        response_data['suppliers'] = SupplierSerializer(suppliers_qs, many=True).data
    
    # Sync payment methods
    if not models_to_sync or 'payment_methods' in models_to_sync:
        payment_methods_qs = PaymentMethod.objects.filter(is_active=True)
        if last_sync_dt:
            payment_methods_qs = payment_methods_qs.filter(updated_at__gte=last_sync_dt)
        response_data['payment_methods'] = PaymentMethodSerializer(payment_methods_qs, many=True).data
    
    return Response(response_data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ratelimit(key='user', rate='20/m', method='POST', block=True)
def sync_push(request):
    """
    Push local changes to server
    Accepts batch of changes and processes them
    """
    device_id = request.data.get('device_id')
    changes = request.data.get('changes', {})
    
    results = {
        'success': [],
        'errors': [],
        'conflicts': []
    }
    
    # Process sales (most critical)
    if 'sales' in changes:
        for sale_data in changes['sales']:
            try:
                # Create or update sale
                # Implementation depends on your conflict resolution strategy
                results['success'].append({'model': 'sale', 'id': sale_data.get('id')})
            except Exception as e:
                results['errors'].append({'model': 'sale', 'error': str(e)})
    
    # Process stock adjustments
    if 'stock_adjustments' in changes:
        for adjustment_data in changes['stock_adjustments']:
            try:
                serializer = StockAdjustmentSerializer(data=adjustment_data)
                if serializer.is_valid():
                    serializer.save(user=request.user)
                    results['success'].append({'model': 'stock_adjustment', 'id': serializer.data['id']})
                else:
                    results['errors'].append({'model': 'stock_adjustment', 'errors': serializer.errors})
            except Exception as e:
                results['errors'].append({'model': 'stock_adjustment', 'error': str(e)})
    
    return Response(results)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sync_status(request):
    """
    Get sync status and server info
    """
    return Response({
        'server_time': timezone.now().isoformat(),
        'version': '1.0.0',
        'status': 'online'
    })
