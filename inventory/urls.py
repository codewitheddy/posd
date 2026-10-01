"""
Inventory URL Configuration
"""
from django.urls import path
from inventory import views

urlpatterns = [
    # Dashboard
    path('', views.InventoryDashboardView.as_view(), name='inventory_dashboard'),

    # Warehouses
    path('warehouses/', views.WarehouseListView.as_view(), name='inventory_warehouse_list'),
    path('warehouses/create/', views.WarehouseCreateView.as_view(), name='inventory_warehouse_create'),
    path('warehouses/<int:pk>/', views.WarehouseDetailView.as_view(), name='inventory_warehouse_detail'),
    path('warehouses/<int:pk>/edit/', views.WarehouseUpdateView.as_view(), name='inventory_warehouse_update'),

    # Stock Ledger
    path('ledger/', views.StockLedgerListView.as_view(), name='inventory_ledger_list'),

    # Valuation & Reports
    path('valuation/', views.StockValuationReportView.as_view(), name='inventory_valuation_report'),

    # Stock Adjustments
    path('adjustments/', views.StockAdjustmentListView.as_view(), name='inventory_adjustment_list'),
    path('adjustments/create/', views.StockAdjustmentCreateView.as_view(), name='inventory_adjustment_create'),
    path('adjustments/<int:pk>/', views.StockAdjustmentDetailView.as_view(), name='inventory_adjustment_detail'),
    path('adjustments/<int:pk>/post/', views.StockAdjustmentPostView.as_view(), name='inventory_adjustment_post'),

    # Stock Transfers
    path('transfers/', views.StockTransferListView.as_view(), name='inventory_transfer_list'),
    path('transfers/create/', views.StockTransferCreateView.as_view(), name='inventory_transfer_create'),
]
