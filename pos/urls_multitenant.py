"""
Multi-tenant URL configuration
Wraps existing URLs with business slug prefix
"""

from django.urls import path, include
from django.shortcuts import render, redirect
from django.http import HttpResponse
from . import views, tenant_views, cash_float_views, user_management_views, support_access_views, zreport_views, sync_views, registration_admin_views, financial_views, crm_views


def ping(request):
    return HttpResponse('ok', content_type='text/plain')


def landing_page(request):
    """Landing page for visitors - always shows landing page"""
    return render(request, 'pos/landing.html')


def terms_page(request):
    """Terms of Service page"""
    return render(request, 'pos/terms.html')


def privacy_page(request):
    """Privacy Policy page"""
    return render(request, 'pos/privacy.html')


def refund_page(request):
    """Refund Policy page"""
    return render(request, 'pos/refund.html')


def root_redirect(request):
    """Root URL - redirects logged-in users to business list, others to landing"""
    if request.user.is_authenticated:
        # Redirect superusers to platform admin dashboard
        if request.user.is_superuser:
            return redirect('platform_admin_dashboard')
        return redirect('business_list')
    return redirect('landing')


# Public URLs (no business context required)
public_urlpatterns = [
    # Root - smart redirect based on auth status
    path('', root_redirect, name='home'),
    
    # Landing page - always accessible
    path('home/', landing_page, name='landing'),
    
    # Legal pages
    path('terms/', terms_page, name='terms'),
    path('privacy/', privacy_page, name='privacy'),
    path('refund/', refund_page, name='refund'),
    
    # Platform Admin Dashboard (superuser only)
    path('platform-admin/', views.platform_admin_dashboard, name='platform_admin_dashboard'),
    path('platform-admin/create-business/', views.admin_create_business, name='admin_create_business'),
    path('platform-admin/extend-license/', views.extend_license, name='extend_license'),
    path('platform-admin/activate-business/<int:business_id>/', views.activate_business, name='activate_business'),
    
    # Support Access Management (platform admin)
    path('support-access/my-requests/', support_access_views.my_support_access_requests, name='my_support_access_requests'),
    path('support-access/request/<int:business_id>/', support_access_views.request_support_access, name='request_support_access'),
    
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
    
    # Business Management
    path('register/', tenant_views.register_business, name='register_business'),
    path('verify-email/<str:token>/', tenant_views.verify_email, name='verify_email'),
    path('businesses/', tenant_views.business_list, name='business_list'),
    
    # Registration Admin (staff only) - Use 'registration-admin' prefix to avoid conflict with Django admin
    path('registration-admin/', registration_admin_views.registrations_list, name='registrations_list'),
    path('registration-admin/<int:registration_id>/approve/', registration_admin_views.registration_approve, name='registration_approve'),
    path('registration-admin/<int:registration_id>/reject/', registration_admin_views.registration_reject, name='registration_reject'),
    path('registration-admin/invitation-codes/', registration_admin_views.invitation_codes_list, name='invitation_codes_list'),
    path('registration-admin/invitation-codes/create/', registration_admin_views.invitation_code_create, name='invitation_code_create'),
    path('registration-admin/invitation-codes/<int:code_id>/toggle/', registration_admin_views.invitation_code_toggle, name='invitation_code_toggle'),
    path('registration-admin/settings/', registration_admin_views.registration_settings_view, name='registration_settings'),
]

# Business-specific URLs (require business slug)
business_urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Subscription & Billing
    path('subscription/', views.subscription, name='subscription'),
    
    # Business Setup & Settings
    path('setup/', tenant_views.business_setup, name='business_setup'),
    path('settings/', tenant_views.business_settings, name='business_settings_tenant'),
    path('members/', tenant_views.business_members, name='business_members'),
    path('members/invite/', tenant_views.invite_member, name='invite_member'),
    path('members/<int:member_id>/remove/', tenant_views.remove_member, name='remove_member'),
    
    # Data Backup
    path('backup/', tenant_views.backup_data, name='backup_data'),
    path('backup/download/', tenant_views.download_backup, name='download_backup'),
    
    # Support Access Management (business owner)
    path('support-access/', support_access_views.view_support_access_requests, name='view_support_access_requests'),
    path('support-access/<int:request_id>/approve/', support_access_views.approve_support_access, name='approve_support_access'),
    path('support-access/<int:request_id>/deny/', support_access_views.deny_support_access, name='deny_support_access'),
    path('support-access/<int:request_id>/revoke/', support_access_views.revoke_support_access, name='revoke_support_access'),
    
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<int:pk>/toggle-active/', views.product_toggle_active, name='product_toggle_active'),
    path('products/bulk-upload/', views.product_bulk_upload, name='product_bulk_upload'),
    path('products/export/', views.product_export_csv, name='product_export_csv'),
    path('products/template/', views.product_download_template, name='product_download_template'),
    path('api/products/create-category/', views.api_create_category, name='api_create_category'),
    path('api/products/create-brand/', views.api_create_brand, name='api_create_brand'),
    
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
    path('purchases/<int:pk>/submit/', views.purchase_submit, name='purchase_submit'),
    path('purchases/<int:pk>/approve/', views.purchase_approve, name='purchase_approve'),
    path('purchases/<int:pk>/send/', views.purchase_send_to_supplier, name='purchase_send_to_supplier'),
    path('purchases/<int:pk>/duplicate/', views.purchase_duplicate, name='purchase_duplicate'),
    path('purchases/<int:pk>/close/', views.purchase_close, name='purchase_close'),
    
    # Goods Received Notes
    path('goods-received/', views.goods_received_list, name='goods_received_list'),
    path('goods-received/<int:pk>/', views.goods_received_detail, name='goods_received_detail'),
    path('goods-received/<int:pk>/print/', views.goods_received_print, name='goods_received_print'),

    # Goods Returned Notes (GRN)
    path('grn/', views.grn_list, name='grn_list'),
    path('grn/create/', views.grn_create, name='grn_create'),
    path('grn/<int:pk>/', views.grn_detail, name='grn_detail'),
    path('grn/<int:pk>/submit/', views.grn_submit, name='grn_submit'),
    path('grn/<int:pk>/acknowledge/', views.grn_acknowledge, name='grn_acknowledge'),
    path('grn/<int:pk>/mark-collected/', views.grn_mark_collected, name='grn_mark_collected'),
    path('grn/<int:pk>/apply-credit/', views.grn_apply_credit, name='grn_apply_credit'),
    path('grn/<int:pk>/cancel/', views.grn_cancel, name='grn_cancel'),
    path('grn/<int:pk>/print/', views.grn_print, name='grn_print'),
    path('api/grn/supplier-purchases/', views.api_grn_supplier_purchases, name='api_grn_supplier_purchases'),
    
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
    
    # Cash Float Management
    path('cash-float/', include([
        path('', cash_float_views.cash_float_list, name='cash_float_list'),
        path('give/', cash_float_views.cash_float_give, name='cash_float_give'),
        path('<int:pk>/', cash_float_views.cash_float_detail, name='cash_float_detail'),
        path('<int:pk>/return/', cash_float_views.cash_float_return, name='cash_float_return'),
        path('<int:pk>/reconcile/', cash_float_views.cash_float_reconcile, name='cash_float_reconcile'),
    ])),
    
    # Reports
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('reports/cashier/', views.cashier_report, name='cashier_report'),
    path('reports/writeoff/', views.writeoff_report, name='writeoff_report'),
    
    # OLD Z-REPORT URLS - Redirected to new system
    path('reports/z-report/', views.z_report_redirect, name='z_report'),
    path('reports/z-report/pdf/', views.z_report_redirect, name='z_report_pdf'),
    path('reports/z-report/close-day/', views.z_report_redirect, name='close_day'),
    path('reports/z-report/open-new-day/', views.z_report_redirect, name='open_new_day'),
    
    path('reports/payment-transactions/', views.payment_transactions_report, name='payment_transactions_report'),
    path('reports/payment-transactions/export/', views.payment_transactions_export, name='payment_transactions_export'),
    path('reports/payment-transactions/csv/', views.payment_transactions_csv, name='payment_transactions_csv'),
    
    # NEW Z-REPORT SYSTEM
    path('z-reports/', include([
        # List and detail
        path('', zreport_views.zreport_list, name='zreport_list'),
        path('<int:z_number>/', zreport_views.zreport_detail, name='zreport_detail'),
        
        # Session management
        path('session/status/', zreport_views.session_status, name='zreport_session_status'),
        path('session/open/', zreport_views.session_open, name='zreport_session_open'),
        path('session/close/', zreport_views.session_close, name='zreport_session_close'),
        
        # Report actions
        path('<int:z_number>/verify/', zreport_views.zreport_verify, name='zreport_verify'),
        path('<int:z_number>/void/', zreport_views.zreport_void, name='zreport_void'),
        path('<int:z_number>/print/', zreport_views.zreport_print, name='zreport_print'),
        
        # Export
        path('<int:z_number>/export/json/', zreport_views.zreport_export_json, name='zreport_export_json'),
        path('<int:z_number>/export/csv/', zreport_views.zreport_export_csv, name='zreport_export_csv'),
        path('<int:z_number>/export/pdf/', zreport_views.zreport_export_pdf, name='zreport_export_pdf'),
        
        # API endpoints
        path('api/session/status/', zreport_views.api_session_status, name='api_session_status'),
        path('api/<int:z_number>/data/', zreport_views.api_zreport_data, name='api_zreport_data'),
    ])),
    
    # Global Search
    path('search/', views.global_search, name='global_search'),

    # Analytics
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/sales-trends/', views.analytics_sales_trends, name='analytics_sales_trends'),
    path('analytics/products/', views.analytics_products, name='analytics_products'),
    path('analytics/customers/', views.analytics_customers, name='analytics_customers'),
    path('analytics/api/', views.analytics_api, name='analytics_api'),

    # Financial Suite
    path('finances/expenses/', financial_views.expense_list, name='expense_list'),
    path('finances/expenses/create/', financial_views.expense_create, name='expense_create'),
    path('finances/expenses/<int:pk>/edit/', financial_views.expense_edit, name='expense_edit'),
    path('finances/expenses/<int:pk>/delete/', financial_views.expense_delete, name='expense_delete'),
    path('finances/expenses/export/', financial_views.expense_export_csv, name='expense_export_csv'),
    path('finances/profit/', financial_views.profit_dashboard, name='profit_dashboard'),
    path('finances/pl/', financial_views.pl_statement, name='pl_statement'),
    
    # User Management
    path('users/', include([
        path('', user_management_views.user_list_view, name='user_management_list'),
        path('create/', user_management_views.user_create_view, name='user_management_create'),
        path('<int:pk>/edit/', user_management_views.user_edit_view, name='user_management_edit'),
        path('<int:pk>/delete/', user_management_views.user_delete_view, name='user_management_delete'),
        path('<int:pk>/change-role/', user_management_views.user_change_role_view, name='user_management_change_role'),
    ])),
    path('users/roles-permissions/', views.roles_permissions, name='roles_permissions'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('profile/', views.user_profile, name='user_profile'),
    
    # Business Settings (legacy)
    path('business-settings/', views.business_settings, name='business_settings'),
    
    # Activity Log
    path('activity-log/', views.activity_log, name='activity_log'),
    path('activity-log/clear/', views.clear_old_logs, name='clear_old_logs'),
    
    # Customer Management
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:pk>/', crm_views.customer_detail_enhanced, name='customer_detail'),

    # Customer Credit
    path('customers/credit/', crm_views.customer_credit_list, name='customer_credit_list'),
    path('customers/<int:pk>/credit/', crm_views.customer_credit_detail, name='customer_credit_detail'),
    path('customers/<int:pk>/credit/payment/', crm_views.customer_credit_payment, name='customer_credit_payment'),
    path('customers/<int:pk>/statement/', crm_views.customer_statement, name='customer_statement'),
    path('customers/credit/aging/', crm_views.credit_aging_report, name='credit_aging_report'),

    # Customer Segments
    path('crm/segments/', crm_views.segment_list, name='segment_list'),
    path('crm/segments/create/', crm_views.segment_create, name='segment_create'),
    path('crm/segments/<int:pk>/edit/', crm_views.segment_edit, name='segment_edit'),
    path('crm/segments/<int:pk>/customers/', crm_views.segment_customers, name='segment_customers'),

    # Campaigns
    path('crm/campaigns/', crm_views.campaign_list, name='campaign_list'),
    path('crm/campaigns/create/', crm_views.campaign_create, name='campaign_create'),
    path('crm/campaigns/<int:pk>/', crm_views.campaign_detail, name='campaign_detail'),
    path('crm/campaigns/<int:pk>/send/', crm_views.campaign_send, name='campaign_send'),

    # CRM Reports
    path('crm/reports/', crm_views.crm_reports, name='crm_reports'),
    path('crm/reports/top-customers/', crm_views.report_top_customers, name='report_top_customers'),
    path('crm/reports/loyalty/', crm_views.report_loyalty, name='report_loyalty'),
    path('crm/reports/credit/', crm_views.report_credit, name='report_credit'),

    # CRM API
    path('api/customer/<int:pk>/credit/', crm_views.api_customer_credit_info, name='api_customer_credit_info'),
    
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
    
    # Offline Sync API
    path('api/sales/sync/', sync_views.sync_sale, name='api_sync_sale'),
    path('api/sync/status/', sync_views.sync_status, name='api_sync_status'),
]

# Combine all patterns
urlpatterns = public_urlpatterns + [
    # Business-specific routes with slug prefix
    path('b/<slug:slug>/', include(business_urlpatterns)),
    # Connectivity ping (used by connection status checker)
    path('ping/', ping, name='ping'),
]
