"""
Accounting Module URL Patterns
Standards: IFRS for SMEs / ICPAK Practice
"""
from django.urls import path
from accounting import views

urlpatterns = [
    # Dashboard
    path('', views.AccountingDashboardView.as_view(), name='accounting_dashboard'),
    
    # Chart of Accounts
    path('accounts/', views.AccountListView.as_view(), name='accounting_account_list'),
    path('accounts/create/', views.AccountCreateView.as_view(), name='accounting_account_create'),
    path('accounts/<int:pk>/', views.AccountDetailView.as_view(), name='accounting_account_detail'),
    path('accounts/<int:pk>/edit/', views.AccountUpdateView.as_view(), name='accounting_account_edit'),
    
    # Fiscal Periods & Years
    path('periods/', views.FiscalPeriodListView.as_view(), name='accounting_period_list'),
    path('periods/<int:pk>/toggle/', views.FiscalPeriodToggleCloseView.as_view(), name='accounting_period_toggle'),
    
    # General Ledger Journals
    path('journals/', views.JournalListView.as_view(), name='accounting_journal_list'),
    path('journals/create/', views.JournalCreateView.as_view(), name='accounting_journal_create'),
    path('journals/<int:pk>/', views.JournalDetailView.as_view(), name='accounting_journal_detail'),
    path('journals/<int:pk>/reverse/', views.JournalReverseView.as_view(), name='accounting_journal_reverse'),
    
    # Accounts Receivable (AR)
    path('customers/', views.CustomerListView.as_view(), name='accounting_customer_list'),
    path('customers/create/', views.CustomerCreateView.as_view(), name='accounting_customer_create'),
    path('invoices/', views.CustomerInvoiceListView.as_view(), name='accounting_invoice_list'),
    path('invoices/<int:pk>/', views.CustomerInvoiceDetailView.as_view(), name='accounting_invoice_detail'),
    path('invoices/<int:pk>/post/', views.CustomerInvoicePostView.as_view(), name='accounting_invoice_post'),
    path('payments/customer/', views.CustomerPaymentListView.as_view(), name='accounting_customer_payment_list'),
    path('payments/customer/create/', views.CustomerPaymentCreateView.as_view(), name='accounting_customer_payment_create'),
    path('reports/ar-aging/', views.ARAgingReportView.as_view(), name='accounting_ar_aging_report'),
    
    # Accounts Payable (AP)
    path('vendors/', views.VendorListView.as_view(), name='accounting_vendor_list'),
    path('vendors/create/', views.VendorCreateView.as_view(), name='accounting_vendor_create'),
    path('bills/', views.VendorBillListView.as_view(), name='accounting_bill_list'),
    path('bills/<int:pk>/', views.VendorBillDetailView.as_view(), name='accounting_bill_detail'),
    path('bills/<int:pk>/post/', views.VendorBillPostView.as_view(), name='accounting_bill_post'),
    path('payments/vendor/', views.VendorPaymentListView.as_view(), name='accounting_vendor_payment_list'),
    path('payments/vendor/create/', views.VendorPaymentCreateView.as_view(), name='accounting_vendor_payment_create'),
    path('reports/ap-aging/', views.APAgingReportView.as_view(), name='accounting_ap_aging_report'),
    
    # Bank & M-Pesa Reconciliation
    path('banking/accounts/', views.BankAccountListView.as_view(), name='accounting_bank_account_list'),
    path('banking/accounts/create/', views.BankAccountCreateView.as_view(), name='accounting_bank_account_create'),
    path('banking/accounts/<int:pk>/', views.BankAccountDetailView.as_view(), name='accounting_bank_account_detail'),
    path('banking/accounts/<int:pk>/import/', views.BankStatementImportView.as_view(), name='accounting_bank_statement_import'),
    path('banking/statements/<int:pk>/reconcile/', views.BankReconciliationActionView.as_view(), name='accounting_bank_statement_reconcile'),
    path('reports/bank-reconciliation/<int:pk>/', views.BankReconciliationReportView.as_view(), name='accounting_bank_reconciliation_report'),
    
    # Kenyan Tax Engine
    path('tax/vat-return/', views.VATReturnView.as_view(), name='accounting_vat_return'),
    path('tax/vat-schedule/', views.VATReturnView.as_view(), name='accounting_vat_schedule'),
    path('tax/vat-return/sales-csv/', views.VATSalesCSVExportView.as_view(), name='accounting_vat_sales_csv'),
    path('tax/vat-return/purchases-csv/', views.VATPurchasesCSVExportView.as_view(), name='accounting_vat_purchases_csv'),
    path('tax/wht/', views.WHTScheduleView.as_view(), name='accounting_wht_schedule'),
    path('tax/wht/csv/', views.WHTCSVExportView.as_view(), name='accounting_wht_csv'),
    
    # Financial Statements & Core Reports
    path('reports/income-statement/', views.IncomeStatementView.as_view(), name='accounting_income_statement'),
    path('reports/balance-sheet/', views.BalanceSheetView.as_view(), name='accounting_balance_sheet'),
    path('reports/cash-flow/', views.CashFlowStatementView.as_view(), name='accounting_cash_flow_statement'),
    path('reports/trial-balance/', views.TrialBalanceView.as_view(), name='accounting_trial_balance'),
    path('reports/trial-balance/csv/', views.TrialBalanceExportCSVView.as_view(), name='accounting_trial_balance_csv'),
    path('reports/general-ledger/', views.GeneralLedgerReportView.as_view(), name='accounting_general_ledger'),
    
    # Posting Queue & Exceptions
    path('posting-exceptions/', views.PostingExceptionListView.as_view(), name='posting_exceptions'),
    path('posting-exceptions/<int:pk>/retry/', views.PostingExceptionRetryView.as_view(), name='posting_exception_retry'),
    path('posting-exceptions/<int:pk>/dismiss/', views.PostingExceptionDismissView.as_view(), name='posting_exception_dismiss'),
    
    # Module GL Account Mappings
    path('mappings/pos/', views.POSGLMappingView.as_view(), name='pos_mapping'),
    path('mappings/hr/', views.HRGLMappingView.as_view(), name='hr_mapping'),
]
