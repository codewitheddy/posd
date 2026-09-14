"""
API Views for POS System
RESTful endpoints for offline-first architecture
"""

from rest_framework import viewsets, status, filters
from rest_framework.views import APIView
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q, F
from datetime import datetime, timedelta
from django_ratelimit.decorators import ratelimit
from .models import (
    Product, Category, Sale, SaleItem, Customer, Supplier,
    Purchase, PurchaseItem, StockAdjustment, UserProfile,
    BusinessSettings, ActivityLog, LoyaltyTransaction,
    LoyaltyReward, PaymentMethod, SalePayment, VATCode,
    Branch, BranchStock, StockMovement, StockRequisition, StockRequisitionItem,
    StockTransferRequest, StockTransferItem, Dispatch, DispatchItem, POSTerminal
)
from .serializers import (
    ProductSerializer, CategorySerializer, SaleSerializer,
    CustomerSerializer, SupplierSerializer, PurchaseSerializer,
    StockAdjustmentSerializer, UserSerializer, BusinessSettingsSerializer,
    ActivityLogSerializer, LoyaltyTransactionSerializer, LoyaltyRewardSerializer,
    PaymentMethodSerializer, SyncRequestSerializer, SyncResponseSerializer, VATCodeSerializer,
    BranchStockSerializer, StockMovementSerializer, StockRequisitionSerializer,
    StockTransferRequestSerializer, DispatchSerializer, POSTerminalSerializer
)
from .permissions import BranchScopeMixin, IsHQAdminOrOwner, IsBranchManagerOrHQ, get_request_business
from .branch_services import DistributionService
from .throttling import LoginThrottle, AuthThrottle
from .api_authentication import POSTerminalAuthentication, APIKeyAuthentication
from .terminal_sync_service import TerminalSyncService


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
        if self.request.user.is_authenticated and not self.request.user.is_superuser:
            memberships = getattr(self.request.user, 'business_memberships', None)
            if memberships is not None:
                active_memberships = memberships.filter(is_active=True).select_related('business')
                if active_memberships.count() == 1:
                    return active_memberships.first().business

        business = getattr(self.request, 'business', None)
        if business is not None:
            return business
        return None

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['business'] = self._get_request_business()
        return context
    
    def get_queryset(self):
        queryset = super().get_queryset()

        # Scope products to the current business context.
        if self.request.user.is_authenticated and not self.request.user.is_superuser:
            memberships = getattr(self.request.user, 'business_memberships', None)
            if memberships is not None:
                business_ids = memberships.filter(is_active=True).values_list('business_id', flat=True)
                if business_ids:
                    queryset = queryset.filter(business_id__in=business_ids)
                else:
                    return queryset.none()
        elif getattr(self.request, 'business', None) is not None:
            queryset = queryset.filter(business=self.request.business)
        
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


class VATCodeViewSet(viewsets.ModelViewSet):
    """
    API endpoint for VAT Codes
    Allows businesses to manage their VAT codes for tax treatment
    """
    serializer_class = VATCodeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'vat_rate', 'created_at']
    ordering = ['code']

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
        """Add business context to serializer"""
        context = super().get_serializer_context()
        context['business'] = self._get_request_business()
        return context

    def get_queryset(self):
        """Filter VAT codes by business context"""
        queryset = VATCode.objects.all().select_related('business')

        business = self._get_request_business()
        if business is not None:
            queryset = queryset.filter(business=business)
        elif self.request.user.is_superuser:
            queryset = queryset
        else:
            # Non-superuser without explicit business context
            memberships = getattr(self.request.user, 'business_memberships', None)
            if memberships is None:
                return queryset.none()
            business_ids = memberships.filter(is_active=True).values_list('business_id', flat=True)
            queryset = queryset.filter(business_id__in=business_ids)
        
        # Filter by active status if requested
        active = self.request.query_params.get('active', None)
        if active is not None:
            queryset = queryset.filter(is_active=active.lower() == 'true')
        
        return queryset

    def perform_create(self, serializer):
        """Auto-populate business when creating VAT code"""
        business = self._get_request_business()
        if business is None:
            raise ValidationError(
                'Unable to determine business for this VAT code creation. '
                'Use a business-scoped request context.'
            )
        serializer.save(business=business)
    
    @action(detail=False, methods=['get'])
    def by_rate(self, request):
        """Filter VAT codes by VAT rate
        
        Query params:
        - rate: VAT rate to filter by (e.g., 16.00)
        """
        rate = request.query_params.get('rate', None)
        if rate is None:
            return Response(
                {'error': 'rate parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from decimal import Decimal
            rate = Decimal(rate)
        except Exception:
            return Response(
                {'error': 'Invalid rate value'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(vat_rate=rate)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def excisable(self, request):
        """Get only excisable VAT codes"""
        queryset = self.get_queryset().filter(is_excisable=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """Get products using this VAT code"""
        vat_code = self.get_object()
        products = vat_code.products.filter(is_active=True)
        
        from .serializers import ProductSerializer
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


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
    
    def perform_create(self, serializer):
        """Create a sale with permission checks"""
        membership = getattr(self.request, 'business_membership', None)
        if not membership:
            raise PermissionDenied("No business membership found")
        
        if not membership.has_permission('can_create_sale'):
            raise PermissionDenied("You do not have permission to create sales")
        
        # Automatically set cashier to the current user
        serializer.save(cashier=self.request.user)
    
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


# ============================================================================
# MULTI-BRANCH DISTRIBUTION & LEDGER VIEWSETS
# ============================================================================

class StockRequisitionViewSet(BranchScopeMixin, viewsets.ModelViewSet):
    serializer_class = StockRequisitionSerializer
    permission_classes = [IsAuthenticated]
    branch_field = 'requesting_branch'

    def get_queryset(self):
        business = get_request_business(self.request)
        qs = StockRequisition.objects.filter(business=business).select_related(
            'requesting_branch', 'requested_by', 'approved_by'
        ).prefetch_related('items__product')
        return self.get_scoped_queryset(qs)

    def perform_create(self, serializer):
        business = get_request_business(self.request)
        requesting_branch = serializer.validated_data.get('requesting_branch')
        items_data = self.request.data.get('items', [])
        notes = serializer.validated_data.get('notes', '')
        req = DistributionService.create_requisition(
            business=business,
            requesting_branch=requesting_branch,
            items_data=items_data,
            user=self.request.user,
            notes=notes,
        )
        serializer.instance = req

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsHQAdminOrOwner])
    def approve(self, request, pk=None):
        requisition = self.get_object()
        approved_items = request.data.get('approved_items', {})
        try:
            req = DistributionService.approve_requisition(requisition, approved_items, request.user)
            return Response(StockRequisitionSerializer(req).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsHQAdminOrOwner])
    def reject(self, request, pk=None):
        requisition = self.get_object()
        reason = request.data.get('reason', '')
        try:
            req = DistributionService.reject_requisition(requisition, request.user, reason)
            return Response(StockRequisitionSerializer(req).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='dispatch', permission_classes=[IsAuthenticated, IsHQAdminOrOwner])
    def perform_dispatch(self, request, pk=None):
        requisition = self.get_object()
        items_data = request.data.get('items', [])
        notes = request.data.get('notes', '')
        if not items_data:
            # Default to all approved quantities
            items_data = [
                {'item_id': item.id, 'quantity': item.approved_quantity or item.requested_quantity}
                for item in requisition.items.all()
            ]
        try:
            dispatch_rec = DistributionService.dispatch(requisition, items_data, request.user, notes)
            return Response(DispatchSerializer(dispatch_rec).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockTransferRequestViewSet(BranchScopeMixin, viewsets.ModelViewSet):
    serializer_class = StockTransferRequestSerializer
    permission_classes = [IsAuthenticated]
    branch_field = 'source_or_dest'

    def get_queryset(self):
        business = get_request_business(self.request)
        qs = StockTransferRequest.objects.filter(business=business).select_related(
            'source_branch', 'destination_branch', 'requested_by', 'approved_by'
        ).prefetch_related('items__product')
        return self.get_scoped_queryset(qs)

    def perform_create(self, serializer):
        business = get_request_business(self.request)
        source_branch = serializer.validated_data.get('source_branch')
        dest_branch = serializer.validated_data.get('destination_branch')
        items_data = self.request.data.get('items', [])
        reason = serializer.validated_data.get('reason', '')
        trf = DistributionService.create_transfer_request(
            business=business,
            source_branch=source_branch,
            dest_branch=dest_branch,
            items_data=items_data,
            user=self.request.user,
            reason=reason,
        )
        serializer.instance = trf

    @action(detail=True, methods=['post'], permission_classes=[IsBranchManagerOrHQ])
    def approve(self, request, pk=None):
        transfer_req = self.get_object()
        approved_items = request.data.get('approved_items', {})
        try:
            trf = DistributionService.approve_transfer_request(transfer_req, approved_items, request.user)
            return Response(StockTransferRequestSerializer(trf).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsBranchManagerOrHQ])
    def reject(self, request, pk=None):
        transfer_req = self.get_object()
        reason = request.data.get('reason', '')
        try:
            trf = DistributionService.reject_transfer_request(transfer_req, request.user, reason)
            return Response(StockTransferRequestSerializer(trf).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='dispatch', permission_classes=[IsBranchManagerOrHQ])
    def perform_dispatch(self, request, pk=None):
        transfer_req = self.get_object()
        items_data = request.data.get('items', [])
        notes = request.data.get('notes', '')
        if not items_data:
            items_data = [
                {'item_id': item.id, 'quantity': item.approved_quantity or item.requested_quantity}
                for item in transfer_req.items.all()
            ]
        try:
            dispatch_rec = DistributionService.dispatch(transfer_req, items_data, request.user, notes)
            return Response(DispatchSerializer(dispatch_rec).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DispatchViewSet(BranchScopeMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = DispatchSerializer
    permission_classes = [IsAuthenticated]
    branch_field = 'source_or_dest'

    def get_queryset(self):
        business = get_request_business(self.request)
        qs = Dispatch.objects.filter(business=business).select_related(
            'source_branch', 'destination_branch', 'dispatched_by', 'received_by'
        ).prefetch_related('items__product')
        return self.get_scoped_queryset(qs)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def confirm_receipt(self, request, pk=None):
        dispatch_rec = self.get_object()
        received_items_data = request.data.get('received_items', {})
        try:
            dispatch_rec = DistributionService.confirm_receipt(dispatch_rec, received_items_data, request.user)
            return Response(DispatchSerializer(dispatch_rec).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class BranchStockViewSet(BranchScopeMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = BranchStockSerializer
    permission_classes = [IsAuthenticated]
    branch_field = 'branch'

    def get_queryset(self):
        business = get_request_business(self.request)
        qs = BranchStock.objects.filter(branch__business=business).select_related(
            'branch', 'product', 'product__category'
        )
        qs = self.get_scoped_queryset(qs)

        branch_id = self.request.query_params.get('branch_id')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        low_stock = self.request.query_params.get('low_stock')
        if low_stock and low_stock.lower() in ('1', 'true', 'yes'):
            qs = qs.filter(quantity__lte=F('reorder_level'))

        return qs.order_by('product__name')


class StockMovementViewSet(BranchScopeMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated]
    branch_field = 'branch'

    def get_queryset(self):
        business = get_request_business(self.request)
        qs = StockMovement.objects.filter(business=business).select_related(
            'branch', 'product', 'performed_by'
        )
        qs = self.get_scoped_queryset(qs)

        branch_id = self.request.query_params.get('branch_id')
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        product_id = self.request.query_params.get('product_id')
        if product_id:
            qs = qs.filter(product_id=product_id)

        movement_type = self.request.query_params.get('movement_type')
        if movement_type:
            qs = qs.filter(movement_type=movement_type)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        return qs.order_by('-created_at')


class POSTerminalViewSet(BranchScopeMixin, viewsets.ModelViewSet):
    serializer_class = POSTerminalSerializer
    permission_classes = [IsAuthenticated]
    branch_field = 'branch'

    def get_queryset(self):
        business = get_request_business(self.request)
        qs = POSTerminal.objects.filter(business=business).select_related('branch')
        return self.get_scoped_queryset(qs)

    def perform_create(self, serializer):
        business = get_request_business(self.request)
        serializer.save(business=business)

    @action(detail=True, methods=['post'], authentication_classes=[POSTerminalAuthentication, APIKeyAuthentication, SessionAuthentication, JWTAuthentication], permission_classes=[AllowAny])
    def sync(self, request, pk=None):
        terminal = self.get_object()
        auth_terminal = getattr(request, 'terminal', None)
        if auth_terminal and auth_terminal.pk != terminal.pk:
            return Response(
                {'error': 'Terminal token does not match the requested terminal ID.'},
                status=status.HTTP_403_FORBIDDEN
            )
        response_data = TerminalSyncService.process_sync(
            terminal=terminal,
            payload=request.data,
            performed_by=request.user if getattr(request.user, 'is_authenticated', False) else None
        )
        return Response(response_data, status=status.HTTP_200_OK)


class POSTerminalSyncView(APIView):
    """
    Dedicated endpoint for POS Terminal bidirectional synchronization.
    Accepts:
      - POST /api/terminals/{id}/sync/
      - POST /api/terminals/sync/
    """
    authentication_classes = [POSTerminalAuthentication, APIKeyAuthentication, SessionAuthentication, JWTAuthentication]
    permission_classes = [AllowAny]

    def post(self, request, pk=None):
        terminal = getattr(request, 'terminal', None)

        # 1. If not authenticated via POSTerminalAuthentication header, check request data / headers explicitly
        if not terminal:
            device_token = request.data.get('device_token') or request.headers.get('X-Terminal-Token') or request.META.get('HTTP_X_TERMINAL_TOKEN')
            if device_token:
                try:
                    terminal = POSTerminal.objects.select_related('business', 'branch').get(device_token=device_token)
                except POSTerminal.DoesNotExist:
                    return Response({'error': 'Invalid device token.'}, status=status.HTTP_401_UNAUTHORIZED)

        # 2. If pk is in URL
        if pk is not None:
            try:
                target_terminal = POSTerminal.objects.select_related('business', 'branch').get(pk=pk)
            except POSTerminal.DoesNotExist:
                return Response({'error': f'Terminal with ID {pk} not found.'}, status=status.HTTP_404_NOT_FOUND)

            if terminal and terminal.pk != target_terminal.pk:
                return Response({'error': 'Terminal token does not match requested terminal ID.'}, status=status.HTTP_403_FORBIDDEN)

            # If user is authenticated via session/JWT/APIKey (staff/admin), allow them to sync on behalf of terminal
            if not terminal and getattr(request.user, 'is_authenticated', False):
                terminal = target_terminal
            elif not terminal:
                # No token and not logged in as staff
                return Response({'error': 'Authentication required. Provide X-Terminal-Token header.'}, status=status.HTTP_401_UNAUTHORIZED)
            else:
                terminal = target_terminal

        if not terminal:
            return Response(
                {'error': 'Authentication required. Provide X-Terminal-Token header or device_token in payload.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not terminal.is_active:
            return Response({'error': 'Terminal is deactivated.'}, status=status.HTTP_403_FORBIDDEN)

        if terminal.branch and not terminal.branch.is_active:
            return Response({'error': 'Terminal branch is inactive.'}, status=status.HTTP_403_FORBIDDEN)

        if not terminal.business.is_active:
            return Response({'error': 'Business is inactive.'}, status=status.HTTP_403_FORBIDDEN)

        performed_by = request.user if getattr(request.user, 'is_authenticated', False) else None
        response_data = TerminalSyncService.process_sync(
            terminal=terminal,
            payload=request.data,
            performed_by=performed_by
        )
        return Response(response_data, status=status.HTTP_200_OK)


