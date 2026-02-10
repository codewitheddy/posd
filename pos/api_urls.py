"""
API URL Configuration for POS System
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .api_views import (
    ProductViewSet, CategoryViewSet, CustomerViewSet, SupplierViewSet,
    SaleViewSet, PurchaseViewSet, StockAdjustmentViewSet,
    PaymentMethodViewSet, LoyaltyTransactionViewSet, LoyaltyRewardViewSet,
    BusinessSettingsViewSet, UserViewSet,
    sync_pull, sync_push, sync_status
)

# Create router and register viewsets
router = DefaultRouter()
router.register(r'products', ProductViewSet, basename='product')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'sales', SaleViewSet, basename='sale')
router.register(r'purchases', PurchaseViewSet, basename='purchase')
router.register(r'stock-adjustments', StockAdjustmentViewSet, basename='stockadjustment')
router.register(r'payment-methods', PaymentMethodViewSet, basename='paymentmethod')
router.register(r'loyalty-transactions', LoyaltyTransactionViewSet, basename='loyaltytransaction')
router.register(r'loyalty-rewards', LoyaltyRewardViewSet, basename='loyaltyreward')
router.register(r'business-settings', BusinessSettingsViewSet, basename='businesssettings')
router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # Authentication endpoints
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Sync endpoints
    path('sync/pull/', sync_pull, name='sync_pull'),
    path('sync/push/', sync_push, name='sync_push'),
    path('sync/status/', sync_status, name='sync_status'),
    
    # API documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    
    # Router URLs
    path('', include(router.urls)),
]
