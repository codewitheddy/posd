"""
POS URL configuration for Single-Store Architecture with Multi-Branch Support
"""

from django.urls import path, include
from django.shortcuts import render, redirect
from django.http import HttpResponse
from . import (
    views, tenant_views, cash_float_views, user_management_views,
    support_access_views, zreport_views, sync_views, financial_views,
    crm_views, webhook_views, branch_views, promotion_views, hscode_views,
    front_office_views, terminal_views, vatcode_views, cashier_assignment_views
)


def ping(request):
    return HttpResponse('ok', content_type='text/plain')


def service_worker(request):
    """Serve service worker from root scope so it can control all pages."""
    import os
    from django.conf import settings as django_settings
    sw_path = os.path.join(django_settings.BASE_DIR, 'pos', 'static', 'js', 'service-worker.js')
    try:
        with open(sw_path, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        return HttpResponse('// service worker not found', content_type='application/javascript', status=404)
    response = HttpResponse(content, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


def offline_page(request):
    """Offline fallback page served by the service worker."""
    return render(request, 'pos/offline.html')


def landing_page(request):
    """Landing page"""
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
    """Root URL - redirects logged-in users directly to dashboard, others to login"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


urlpatterns = [
    # Root & Public Routes
    path('', root_redirect, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('sw.js', service_worker, name='service_worker'),
    path('offline/', offline_page, name='offline'),
    path('home/', landing_page, name='landing'),
    path('terms/', terms_page, name='terms'),
    path('privacy/', privacy_page, name='privacy'),
    path('refund/', refund_page, name='refund'),
    path('ping/', ping, name='ping'),

    # Authentication & Registration
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', tenant_views.register_business, name='register_business'),
    path('verify-email/<str:token>/', tenant_views.verify_email, name='verify_email'),
    path('businesses/', tenant_views.business_list, name='business_list'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),

    # Platform Admin Dashboard
    path('platform-admin/', views.platform_admin_dashboard, name='platform_admin_dashboard'),
    path('platform-admin/create-business/', views.admin_create_business, name='admin_create_business'),
    path('platform-admin/extend-license/', views.extend_license, name='extend_license'),
    path('platform-admin/activate-business/<int:business_id>/', views.activate_business, name='activate_business'),
    path('platform-admin/reset-password/', views.admin_reset_password, name='admin_reset_password'),

    # Multi-Branch Management
    path('branches/', branch_views.branch_list, name='branch_list'),
    path('branches/assignments/', cashier_assignment_views.cashier_assignment_dashboard, name='cashier_assignment_dashboard'),
    path('branches/assignments/request-transfer/', cashier_assignment_views.request_transfer_view, name='request_transfer_view'),
    path('branches/assignments/transfers/<int:pk>/approve/', cashier_assignment_views.approve_transfer_view, name='approve_transfer_view'),
    path('branches/assignments/transfers/<int:pk>/reject/', cashier_assignment_views.reject_transfer_view, name='reject_transfer_view'),
    path('branches/assignments/transfers/<int:pk>/cancel/', cashier_assignment_views.cancel_transfer_view, name='cancel_transfer_view'),
    path('branches/assignments/assign-till/', cashier_assignment_views.assign_till_view, name='assign_till_view'),
    path('branches/assignments/tills/<int:pk>/activate/', cashier_assignment_views.activate_till_view, name='activate_till_view'),
    path('branches/assignments/tills/<int:pk>/release/', cashier_assignment_views.release_till_view, name='release_till_view'),
    path('branches/<int:branch_id>/', branch_views.branch_detail, name='branch_detail'),
    path('branches/<int:branch_id>/stock/', branch_views.branch_stock, name='branch_stock'),
    path('branches/<int:branch_id>/transfers/', branch_views.transfer_list, name='transfer_list'),
    path('branches/<int:branch_id>/transfers/create/', branch_views.transfer_create, name='transfer_create'),
    path('branches/<int:branch_id>/staff/', branch_views.branch_membership_list, name='branch_membership_list'),
    path('branches/<int:branch_id>/prices/', branch_views.price_override_list, name='price_override_list'),
    path('branches/switch/<int:branch_id>/', branch_views.switch_active_branch, name='switch_active_branch'),
    path('branches/login/<int:branch_id>/', branch_views.branch_login, name='branch_login'),
    path('transfers/', branch_views.business_transfer_list, name='business_transfer_list'),
    path('reports/consolidated/', branch_views.consolidated_report, name='consolidated_report'),
    path('api/branch/set/', branch_views.set_active_branch, name='set_active_branch'),

    # HQ Distribution (Stock Requisitions)
    path('requisitions/', branch_views.requisition_list, name='requisition_list'),
    path('requisitions/create/', branch_views.requisition_create, name='requisition_create'),
    path('requisitions/<int:pk>/', branch_views.requisition_detail, name='requisition_detail'),
    path('requisitions/<int:pk>/approve/', branch_views.requisition_approve, name='requisition_approve'),
    path('requisitions/<int:pk>/reject/', branch_views.requisition_reject, name='requisition_reject'),
    path('requisitions/<int:pk>/dispatch/', branch_views.requisition_dispatch, name='requisition_dispatch'),

    # Inter-Branch Transfer Requests
    path('transfers/requests/', branch_views.transfer_request_list, name='transfer_request_list'),
    path('transfers/requests/create/', branch_views.transfer_request_create, name='transfer_request_create'),
    path('transfers/requests/<int:pk>/', branch_views.transfer_request_detail, name='transfer_request_detail'),
    path('transfers/requests/<int:pk>/approve/', branch_views.transfer_request_approve, name='transfer_request_approve'),
    path('transfers/requests/<int:pk>/reject/', branch_views.transfer_request_reject, name='transfer_request_reject'),
    path('transfers/requests/<int:pk>/dispatch/', branch_views.transfer_request_dispatch, name='transfer_request_dispatch'),
    path('transfers/requests/<int:pk>/resolve-discrepancy/', branch_views.transfer_request_resolve_discrepancy, name='transfer_request_resolve_discrepancy'),
    path('transfers/rules/', branch_views.transfer_approval_rules_list, name='transfer_approval_rules'),

    # In-Transit Dispatches & Receiving
    path('dispatches/', branch_views.dispatch_list, name='dispatch_list'),
    path('dispatches/<int:pk>/', branch_views.dispatch_detail, name='dispatch_detail'),
    path('dispatches/<int:pk>/receive/', branch_views.dispatch_receive, name='dispatch_receive'),

    # Unified Stock Movement Ledger & Branch Low Stock
    path('stock/ledger/', branch_views.stock_ledger, name='stock_ledger'),
    path('stock/branch-low-stock/', branch_views.branch_low_stock, name='branch_low_stock'),
    path('branches/<int:branch_id>/low-stock/', branch_views.branch_low_stock, name='branch_low_stock_detail'),

    # Store Settings, Terminals & Members
    path('setup/', tenant_views.business_setup, name='business_setup'),
    path('setup/skip/', tenant_views.skip_setup, name='skip_setup'),
    path('settings/', tenant_views.business_settings, name='business_settings'),
    path('business-settings/', tenant_views.business_settings, name='business_settings_alias'),
    path('members/', tenant_views.business_members, name='business_members'),
    path('members/invite/', tenant_views.invite_member, name='invite_member'),
    path('members/<int:member_id>/remove/', tenant_views.remove_member, name='remove_member'),
    path('members/<int:member_id>/edit/', tenant_views.edit_member, name='edit_member'),

    # Front Office POS & PIN Authentication
    path('pos/login/', front_office_views.terminal_pin_login, name='terminal_pin_login'),
    path('pos/login/', front_office_views.terminal_pin_login, name='front_office_login'),
    path('pos/pin-login/', front_office_views.terminal_pin_login, name='pos_pin_login'),
    path('pos/lock/', front_office_views.terminal_lock, name='terminal_lock'),
    path('pos/terminals/register/', front_office_views.terminal_register, name='terminal_register'),
    path('pos/session/open/', front_office_views.terminal_session_open, name='terminal_session_open'),
    path('pos/session/open/', front_office_views.terminal_session_open, name='pos_session_open'),
    path('pos/session/close/', front_office_views.terminal_session_close, name='terminal_session_close'),
    path('pos/session/close/', front_office_views.terminal_session_close, name='pos_session_close'),
    path('pos/front-office/', front_office_views.front_office_pos, name='front_office_pos'),
    path('pos/shift/zreport/', front_office_views.front_office_zreport, name='front_office_zreport'),

    # Real-Time Sync & Offline Engine
    path('pos/api/sync/stream/', sync_views.sync_stream_view, name='pos_sync_stream'),
    path('pos/api/sync/poll/', sync_views.sync_poll_view, name='pos_sync_poll'),
    path('pos/api/sync/catalog/', sync_views.sync_products_catalog_view, name='pos_sync_catalog'),
    path('pos/api/sync/offline-sales/', sync_views.sync_offline_sales_view, name='pos_sync_offline_sales'),

    # POS Terminals Hardware & PIN Audit
    path('terminals/', terminal_views.terminal_list, name='terminal_list'),
    path('terminals/create/', terminal_views.terminal_create, name='terminal_create'),
    path('terminals/<int:pk>/edit/', terminal_views.terminal_edit, name='terminal_edit'),
    path('audit/pin-logins/', terminal_views.pin_audit_log_list, name='pin_audit_log_list'),

    # Data Backup
    path('backup/', tenant_views.backup_data, name='backup_data'),
    path('backup/download/', tenant_views.download_backup, name='download_backup'),
    path('backup/restore/', tenant_views.restore_backup, name='restore_backup'),

    # Products & Inventory
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<int:pk>/toggle-active/', views.product_toggle_active, name='product_toggle_active'),
    path('products/<int:pk>/break-bulk/', views.break_bulk, name='break_bulk'),
    path('products/bulk-upload/', views.product_bulk_upload, name='product_bulk_upload'),
    path('products/bulk-action/', views.product_bulk_action, name='product_bulk_action'),
    path('products/print-barcodes/', views.product_bulk_barcode_print, name='product_bulk_barcode_print'),
    path('products/export/', views.product_export_csv, name='product_export_csv'),
    path('products/template/', views.product_download_template, name='product_download_template'),
    path('api/products/create-category/', views.api_create_category, name='api_create_category'),
    path('api/products/create-brand/', views.api_create_brand, name='api_create_brand'),
    path('api/products/create-unit/', views.api_create_unit, name='api_create_unit'),

    # HS Codes
    path('hs-codes/', hscode_views.hscode_list, name='hscode_list'),
    path('hs-codes/create/', hscode_views.hscode_create, name='hscode_create'),
    path('hs-codes/<int:pk>/edit/', hscode_views.hscode_edit, name='hscode_edit'),
    path('hs-codes/<int:pk>/delete/', hscode_views.hscode_delete, name='hscode_delete'),
    path('api/hs-codes/search/', hscode_views.hscode_search, name='hscode_search'),
    path('api/hs-codes/<int:pk>/', hscode_views.hscode_detail, name='hscode_detail'),

    # VAT Codes
    path('vat-codes/', vatcode_views.vatcode_list, name='vatcode_list'),
    path('vat-codes/create/', vatcode_views.vatcode_create, name='vatcode_create'),
    path('vat-codes/<int:pk>/edit/', vatcode_views.vatcode_edit, name='vatcode_edit'),
    path('vat-codes/<int:pk>/delete/', vatcode_views.vatcode_delete, name='vatcode_delete'),
    path('vat-codes/<int:pk>/toggle-active/', vatcode_views.vatcode_toggle_active, name='vatcode_toggle_active'),
    path('vat-codes/seed-defaults/', vatcode_views.vatcode_seed_defaults, name='vatcode_seed_defaults'),

    # Categories & Units
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('units/', views.unit_list, name='unit_list'),
    path('units/create/', views.unit_create, name='unit_create'),
    path('units/<int:pk>/edit/', views.unit_edit, name='unit_edit'),
    path('units/<int:pk>/delete/', views.unit_delete, name='unit_delete'),

    # Stock Management & Multi-Branch Ledger
    path('stock/', views.stock_list, name='stock_list'),
    path('stock/<int:pk>/adjust/', views.stock_adjust, name='stock_adjust'),
    path('stock/<int:pk>/history/', views.stock_history, name='stock_history'),
    path('stock/alerts/', views.low_stock_alert, name='low_stock_alert'),
    path('stock/expiry/', views.expiry_alert, name='expiry_alert'),
    path('stock/<int:pk>/update-expiry/', views.update_expiry, name='update_expiry'),
    path('stock/ledger/', branch_views.stock_ledger, name='stock_ledger'),
    path('stock/branch-low-stock/', branch_views.branch_low_stock, name='branch_low_stock'),
    path('stock/branch-low-stock/<int:branch_id>/', branch_views.branch_low_stock, name='branch_low_stock_by_id'),

    # Multi-Branch Management
    path('branches/', branch_views.branch_list, name='branch_list'),
    path('branches/<int:branch_id>/', branch_views.branch_detail, name='branch_detail'),
    path('branches/<int:branch_id>/stock/', branch_views.branch_stock, name='branch_stock'),
    path('branches/<int:branch_id>/transfers/', branch_views.transfer_list, name='transfer_list'),
    path('branches/<int:branch_id>/transfers/create/', branch_views.transfer_create, name='transfer_create'),
    path('branches/transfers/', branch_views.business_transfer_list, name='business_transfer_list'),
    path('branches/<int:branch_id>/staff/', branch_views.branch_membership_list, name='branch_membership_list'),
    path('branches/<int:branch_id>/prices/', branch_views.price_override_list, name='price_override_list'),
    path('branches/reports/consolidated/', branch_views.consolidated_report, name='consolidated_report'),
    path('branches/switch/', branch_views.set_active_branch, name='set_active_branch'),
    path('branches/switch/<int:branch_id>/', branch_views.switch_active_branch, name='switch_active_branch'),
    path('branches/<int:branch_id>/login/', branch_views.branch_login, name='branch_login'),

    # HQ Stock Requisitions
    path('requisitions/', branch_views.requisition_list, name='requisition_list'),
    path('requisitions/create/', branch_views.requisition_create, name='requisition_create'),
    path('requisitions/<int:pk>/', branch_views.requisition_detail, name='requisition_detail'),
    path('requisitions/<int:pk>/approve/', branch_views.requisition_approve, name='requisition_approve'),
    path('requisitions/<int:pk>/reject/', branch_views.requisition_reject, name='requisition_reject'),
    path('requisitions/<int:pk>/dispatch/', branch_views.requisition_dispatch, name='requisition_dispatch'),

    # Inter-Branch Stock Transfers
    path('transfers/requests/', branch_views.transfer_request_list, name='transfer_request_list'),
    path('transfers/requests/create/', branch_views.transfer_request_create, name='transfer_request_create'),
    path('transfers/requests/<int:pk>/', branch_views.transfer_request_detail, name='transfer_request_detail'),
    path('transfers/requests/<int:pk>/approve/', branch_views.transfer_request_approve, name='transfer_request_approve'),
    path('transfers/requests/<int:pk>/reject/', branch_views.transfer_request_reject, name='transfer_request_reject'),
    path('transfers/requests/<int:pk>/dispatch/', branch_views.transfer_request_dispatch, name='transfer_request_dispatch'),
    path('transfers/requests/<int:pk>/resolve-discrepancy/', branch_views.transfer_request_resolve_discrepancy, name='transfer_request_resolve_discrepancy'),
    path('transfers/rules/', branch_views.transfer_approval_rules_list, name='transfer_approval_rules'),

    # Dispatches & Shipments
    path('dispatches/', branch_views.dispatch_list, name='dispatch_list'),
    path('dispatches/<int:pk>/', branch_views.dispatch_detail, name='dispatch_detail'),
    path('dispatches/<int:pk>/receive/', branch_views.dispatch_receive, name='dispatch_receive'),

    # Suppliers & Payments
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/create/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),
    path('suppliers/<int:supplier_id>/payments/', views.supplier_payments, name='supplier_payments'),
    path('suppliers/<int:supplier_id>/payments/create/', views.create_payment, name='create_payment'),
    path('suppliers/<int:supplier_id>/statement/', views.supplier_statement, name='supplier_statement'),
    path('payments/<int:payment_id>/', views.payment_detail, name='payment_detail'),
    path('payments/<int:payment_id>/delete/', views.delete_payment, name='delete_payment'),
    path('supplier-balances/', views.supplier_balances, name='supplier_balances'),
    path('aging-analysis/', views.aging_analysis, name='aging_analysis'),

    # Purchases & GRN
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
    path('goods-received/', views.goods_received_list, name='goods_received_list'),
    path('goods-received/<int:pk>/', views.goods_received_detail, name='goods_received_detail'),
    path('goods-received/<int:pk>/print/', views.goods_received_print, name='goods_received_print'),
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
    path('api/grn/purchase-defaults/', views.api_grn_purchase_defaults, name='api_grn_purchase_defaults'),

    # POS Screen & Sales
    path('pos/', views.pos_screen, name='pos_screen'),
    path('pos/customer-display/', views.customer_display, name='customer_display'),
    path('pos/complete/', views.complete_sale, name='complete_sale'),
    path('pos/supervisor-authorize/', views.supervisor_authorize, name='pos_supervisor_authorize'),
    path('pos/held-orders/', views.held_orders_list, name='held_orders_list'),
    path('pos/held-orders/save/', views.held_order_save, name='held_order_save'),
    path('pos/held-orders/<int:pk>/delete/', views.held_order_delete, name='held_order_delete'),
    path('api/product/search/', views.search_product_by_code, name='search_product_by_code'),
    path('api/customer/search/', views.search_customer_by_phone, name='search_customer_by_phone'),
    path('invoice/<int:pk>/', views.invoice_view, name='invoice_view'),
    path('invoice/<int:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),
    path('invoice/<int:pk>/thermal/', views.thermal_receipt, name='thermal_receipt'),
    path('sales/', views.sales_list, name='sales_list'),

    # Cash Float Management
    path('cash-float/', include([
        path('', cash_float_views.cash_float_list, name='cash_float_list'),
        path('give/', cash_float_views.cash_float_give, name='cash_float_give'),
        path('<int:pk>/', cash_float_views.cash_float_detail, name='cash_float_detail'),
        path('<int:pk>/return/', cash_float_views.cash_float_return, name='cash_float_return'),
        path('<int:pk>/reconcile/', cash_float_views.cash_float_reconcile, name='cash_float_reconcile'),
    ])),

    # Reports & Z-Reports
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('reports/cashier/', views.cashier_report, name='cashier_report'),
    path('reports/writeoff/', views.writeoff_report, name='writeoff_report'),
    path('reports/z-report/', views.z_report_redirect, name='z_report'),
    path('reports/z-report/pdf/', views.z_report_redirect, name='z_report_pdf'),
    path('reports/z-report/close-day/', views.z_report_redirect, name='close_day'),
    path('reports/z-report/open-new-day/', views.z_report_redirect, name='open_new_day'),
    path('reports/payment-transactions/', views.payment_transactions_report, name='payment_transactions_report'),
    path('reports/payment-transactions/export/', views.payment_transactions_export, name='payment_transactions_export'),
    path('reports/payment-transactions/csv/', views.payment_transactions_csv, name='payment_transactions_csv'),

    path('z-reports/', include([
        path('', zreport_views.zreport_list, name='zreport_list'),
        path('<int:z_number>/', zreport_views.zreport_detail, name='zreport_detail'),
        path('session/status/', zreport_views.session_status, name='zreport_session_status'),
        path('session/open/', zreport_views.session_open, name='zreport_session_open'),
        path('session/close/', zreport_views.session_close, name='zreport_session_close'),
        path('<int:z_number>/verify/', zreport_views.zreport_verify, name='zreport_verify'),
        path('<int:z_number>/void/', zreport_views.zreport_void, name='zreport_void'),
        path('<int:z_number>/print/', zreport_views.zreport_print, name='zreport_print'),
        path('<int:z_number>/export/json/', zreport_views.zreport_export_json, name='zreport_export_json'),
        path('<int:z_number>/export/csv/', zreport_views.zreport_export_csv, name='zreport_export_csv'),
        path('<int:z_number>/export/pdf/', zreport_views.zreport_export_pdf, name='zreport_export_pdf'),
        path('<int:z_number>/pdf/', zreport_views.zreport_export_pdf, name='zreport_pdf'),
        path('api/session/status/', zreport_views.api_session_status, name='api_session_status'),
        path('api/<int:z_number>/data/', zreport_views.api_zreport_data, name='api_zreport_data'),
    ])),

    # Search & Analytics
    path('search/', views.global_search, name='global_search'),
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

    # User Management & HR Hub
    path('users/', include([
        path('', user_management_views.user_list_view, name='user_management_list'),
        path('create/', user_management_views.user_create_view, name='user_management_create'),
        path('<int:pk>/edit/', user_management_views.user_edit_view, name='user_management_edit'),
        path('<int:pk>/delete/', user_management_views.user_delete_view, name='user_management_delete'),
        path('<int:pk>/change-role/', user_management_views.user_change_role_view, name='user_management_change_role'),
    ])),
    path('users/roles-permissions/', views.roles_permissions, name='roles_permissions'),
    path('hr-hub/', views.hr_hub, name='hr_hub'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('profile/', views.user_profile, name='user_profile'),

    # Activity Log
    path('activity-log/', views.activity_log, name='activity_log'),
    path('activity-log/clear/', views.clear_old_logs, name='clear_old_logs'),
    path('activity-log/user/<int:user_id>/', views.user_activity, name='user_activity'),

    # Customer Management & CRM
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('customers/<int:pk>/merge/', crm_views.customer_merge, name='customer_merge'),
    path('customers/<int:pk>/', crm_views.customer_detail_enhanced, name='customer_detail'),

    # Customer Credit
    path('customers/credit/', crm_views.customer_credit_list, name='customer_credit_list'),
    path('customers/<int:pk>/credit/', crm_views.customer_credit_detail, name='customer_credit_detail'),
    path('customers/<int:pk>/credit/payment/', crm_views.customer_credit_payment, name='customer_credit_payment'),
    path('customers/<int:pk>/statement/', crm_views.customer_statement, name='customer_statement'),
    path('customers/credit/aging/', crm_views.credit_aging_report, name='credit_aging_report'),

    # Customer Segments & Campaigns
    path('crm/segments/', crm_views.segment_list, name='segment_list'),
    path('crm/segments/create/', crm_views.segment_create, name='segment_create'),
    path('crm/segments/<int:pk>/edit/', crm_views.segment_edit, name='segment_edit'),
    path('crm/segments/<int:pk>/customers/', crm_views.segment_customers, name='segment_customers'),
    path('crm/campaigns/', crm_views.campaign_list, name='campaign_list'),
    path('crm/campaigns/create/', crm_views.campaign_create, name='campaign_create'),
    path('crm/campaigns/<int:pk>/', crm_views.campaign_detail, name='campaign_detail'),
    path('crm/campaigns/<int:pk>/send/', crm_views.campaign_send, name='campaign_send'),
    path('crm/reports/', crm_views.crm_reports, name='crm_reports'),
    path('crm/reports/top-customers/', crm_views.report_top_customers, name='report_top_customers'),
    path('crm/reports/loyalty/', crm_views.report_loyalty, name='report_loyalty'),
    path('crm/reports/credit/', crm_views.report_credit, name='report_credit'),
    path('api/customer/<int:pk>/credit/', crm_views.api_customer_credit_info, name='api_customer_credit_info'),

    # Loyalty Program
    path('customers/<int:pk>/loyalty/', views.loyalty_dashboard, name='loyalty_dashboard'),
    path('customers/<int:pk>/loyalty/transactions/', views.loyalty_transactions, name='loyalty_transactions'),
    path('customers/<int:pk>/loyalty/redeem/', views.loyalty_redeem, name='loyalty_redeem'),
    path('customers/<int:pk>/loyalty/adjust/', views.loyalty_adjust, name='loyalty_adjust'),
    path('loyalty/rewards/', views.loyalty_rewards_list, name='loyalty_rewards_list'),
    path('loyalty/rewards/create/', views.loyalty_reward_create, name='loyalty_reward_create'),
    path('loyalty/rewards/<int:pk>/edit/', views.loyalty_reward_edit, name='loyalty_reward_edit'),

    # Promotions & Payment Methods
    path('promotions/', promotion_views.promotion_list, name='promotion_list'),
    path('promotions/create/', promotion_views.promotion_create, name='promotion_create'),
    path('promotions/<int:pk>/edit/', promotion_views.promotion_edit, name='promotion_edit'),
    path('promotions/<int:pk>/toggle/', promotion_views.promotion_toggle, name='promotion_toggle'),
    path('promotions/<int:pk>/delete/', promotion_views.promotion_delete, name='promotion_delete'),
    path('api/promotions/validate/', promotion_views.validate_promo_code, name='validate_promo_code'),

    path('payment-methods/', views.payment_method_list, name='payment_method_list'),
    path('payment-methods/create/', views.payment_method_create, name='payment_method_create'),
    path('payment-methods/<int:pk>/edit/', views.payment_method_edit, name='payment_method_edit'),
    path('payment-methods/<int:pk>/delete/', views.payment_method_delete, name='payment_method_delete'),

    # Offline Sync API & Webhooks
    path('api/sales/sync/', sync_views.sync_sale, name='api_sync_sale'),
    path('api/sync/status/', sync_views.sync_status, name='api_sync_status'),
    path('webhooks/', webhook_views.webhook_list, name='webhook_list'),
    path('webhooks/create/', webhook_views.webhook_create, name='webhook_create'),
    path('webhooks/<int:pk>/edit/', webhook_views.webhook_edit, name='webhook_edit'),
    path('webhooks/<int:pk>/delete/', webhook_views.webhook_delete, name='webhook_delete'),
    path('webhooks/<int:pk>/test/', webhook_views.webhook_test, name='webhook_test'),
    path('webhooks/<int:pk>/deliveries/', webhook_views.webhook_deliveries, name='webhook_deliveries'),

    # Integration Hub + Exports
    path('integrations/', webhook_views.integration_hub, name='integration_hub'),
    path('integrations/export/sales.csv', webhook_views.export_sales_csv, name='export_sales_csv'),
    path('integrations/export/sales.json', webhook_views.export_sales_json, name='export_sales_json'),
    path('integrations/export/products.csv', webhook_views.export_products_csv, name='export_products_csv'),
    path('integrations/export/customers.csv', webhook_views.export_customers_csv, name='export_customers_csv'),
]
