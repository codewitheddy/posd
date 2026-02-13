"""
Multi-tenant URL configuration
Wraps existing URLs with business slug prefix
"""

from django.urls import path, include
from django.shortcuts import render, redirect
from . import views, tenant_views


def landing_page(request):
    """Landing page for visitors - always shows landing page"""
    return render(request, 'pos/landing.html')


def root_redirect(request):
    """Root URL - redirects logged-in users to business list, others to landing"""
    if request.user.is_authenticated:
        return redirect('business_list')
    return redirect('landing')


# Public URLs (no business context required)
public_urlpatterns = [
    # Root - smart redirect based on auth status
    path('', root_redirect, name='home'),
    
    # Landing page - always accessible
    path('home/', landing_page, name='landing'),
    
    # Platform Admin Dashboard (superuser only)
    path('platform-admin/', views.platform_admin_dashboard, name='platform_admin_dashboard'),
    
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    
    # Business Management
    path('register/', tenant_views.register_business, name='register_business'),
    path('businesses/', tenant_views.business_list, name='business_list'),
]

# Business-specific URLs (require business slug)
business_urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Business Setup & Settings
    path('setup/', tenant_views.business_setup, name='business_setup'),
    path('settings/', tenant_views.business_settings, name='business_settings_tenant'),
    path('members/', tenant_views.business_members, name='business_members'),
    path('members/invite/', tenant_views.invite_member, name='invite_member'),
    path('members/<int:member_id>/remove/', tenant_views.remove_member, name='remove_member'),
    
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/bulk-upload/', views.product_bulk_upload, name='product_bulk_upload'),
    path('products/export/', views.product_export_csv, name='product_export_csv'),
    path('products/template/', views.product_download_template, name='product_download_template'),
    
    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    
    # Units of Measurement
    path('units/', views.unit_list, name='unit_list'),
    path('units/create/', views.unit_create, name='unit_create'),
    path('units/<int:pk>/edit/', views.unit_edit, name='unit_edit'),
    path('units/<int:pk>/delete/', views.unit_delete, name='unit_delete'),
    
    # Stock Management
    path('stock/', views.stock_list, name='stock_list'),
    path('stock/<int:pk>/adjust/', views.stock_adjust, name='stock_adjust'),
    path('stock/<int:pk>/history/', views.stock_history, name='stock_history'),
    path('stock/alerts/', views.low_stock_alert, name='low_stock_alert'),
    path('stock/expiry/', views.expiry_alert, name='expiry_alert'),
    path('stock/<int:pk>/update-expiry/', views.update_expiry, name='update_expiry'),
    
    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),
    
    # Supplier Payments
    path('suppliers/<int:supplier_id>/payments/', views.supplier_payments, name='supplier_payments'),
    path('suppliers/<int:supplier_id>/payments/create/', views.create_payment, name='create_payment'),
    path('suppliers/<int:supplier_id>/statement/', views.supplier_statement, name='supplier_statement'),
    path('payments/<int:payment_id>/', views.payment_detail, name='payment_detail'),
    path('payments/<int:payment_id>/delete/', views.delete_payment, name='delete_payment'),
    path('supplier-balances/', views.supplier_balances, name='supplier_balances'),
    path('aging-analysis/', views.aging_analysis, name='aging_analysis'),
    
    # Purchases
    path('purchases/', views.purchase_list, name='purchase_list'),
    path('purchases/create/', views.purchase_create, name='purchase_create'),
    path('purchases/<int:pk>/', views.purchase_detail, name='purchase_detail'),
    path('purchases/<int:pk>/receive/', views.purchase_receive, name='purchase_receive'),
    path('purchases/<int:pk>/cancel/', views.purchase_cancel, name='purchase_cancel'),
    
    # POS
    path('pos/', views.pos_screen, name='pos_screen'),
    path('pos/complete/', views.complete_sale, name='complete_sale'),
    path('api/product/search/', views.search_product_by_code, name='search_product_by_code'),
    path('api/customer/search/', views.search_customer_by_phone, name='search_customer_by_phone'),
    
    # Invoices
    path('invoice/<int:pk>/', views.invoice_view, name='invoice_view'),
    path('invoice/<int:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),
    path('invoice/<int:pk>/thermal/', views.thermal_receipt, name='thermal_receipt'),
    
    # Sales
    path('sales/', views.sales_list, name='sales_list'),
    
    # Reports
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('reports/cashier/', views.cashier_report, name='cashier_report'),
    path('reports/writeoff/', views.writeoff_report, name='writeoff_report'),
    path('reports/z-report/', views.z_report, name='z_report'),
    path('reports/z-report/pdf/', views.z_report_pdf, name='z_report_pdf'),
    path('reports/payment-transactions/', views.payment_transactions_report, name='payment_transactions_report'),
    path('reports/payment-transactions/export/', views.payment_transactions_export, name='payment_transactions_export'),
    path('reports/payment-transactions/csv/', views.payment_transactions_csv, name='payment_transactions_csv'),
    
    # Analytics
    path('api/analytics/', views.analytics_api, name='analytics_api'),
    path('analytics/export/', views.analytics_export_pdf, name='analytics_export_pdf'),
    
    # User Management
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('profile/', views.user_profile, name='user_profile'),
    
    # Business Settings (legacy)
    path('business-settings/', views.business_settings, name='business_settings'),
    
    # Activity Log
    path('activity-log/', views.activity_log, name='activity_log'),
    
    # Customer Management
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    
    # Loyalty Program
    path('customers/<int:pk>/loyalty/', views.loyalty_dashboard, name='loyalty_dashboard'),
    path('customers/<int:pk>/loyalty/transactions/', views.loyalty_transactions, name='loyalty_transactions'),
    path('customers/<int:pk>/loyalty/redeem/', views.loyalty_redeem, name='loyalty_redeem'),
    path('customers/<int:pk>/loyalty/adjust/', views.loyalty_adjust, name='loyalty_adjust'),
    path('loyalty/rewards/', views.loyalty_rewards_list, name='loyalty_rewards_list'),
    path('loyalty/rewards/create/', views.loyalty_reward_create, name='loyalty_reward_create'),
    path('loyalty/rewards/<int:pk>/edit/', views.loyalty_reward_edit, name='loyalty_reward_edit'),
    
    # Payment Methods Management
    path('payment-methods/', views.payment_method_list, name='payment_method_list'),
    path('payment-methods/create/', views.payment_method_create, name='payment_method_create'),
    path('payment-methods/<int:pk>/edit/', views.payment_method_edit, name='payment_method_edit'),
    path('payment-methods/<int:pk>/delete/', views.payment_method_delete, name='payment_method_delete'),
]

# Combine all patterns
urlpatterns = public_urlpatterns + [
    # Business-specific routes with slug prefix
    path('b/<slug:slug>/', include(business_urlpatterns)),
]
