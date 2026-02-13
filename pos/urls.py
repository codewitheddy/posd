from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    path('', views.dashboard, name='dashboard'),
    
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
    
    # Invoices
    path('invoice/<int:pk>/', views.invoice_view, name='invoice_view'),
    path('invoice/<int:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),
    path('invoice/<int:pk>/thermal/', views.thermal_receipt, name='thermal_receipt'),
    
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
    
    # Business Settings
    path('settings/', views.business_settings, name='business_settings'),
    
    # Activity Log
    path('activity-log/', views.activity_log, name='activity_log'),
    
    # Customer Management
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
]

