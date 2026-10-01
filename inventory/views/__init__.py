"""
Inventory Views Package
"""
from inventory.views.dashboard import InventoryDashboardView
from inventory.views.warehouses import (
    WarehouseListView,
    WarehouseCreateView,
    WarehouseUpdateView,
    WarehouseDetailView,
)
from inventory.views.stock_ledger import StockLedgerListView
from inventory.views.valuation import StockValuationReportView
from inventory.views.adjustments import (
    StockAdjustmentListView,
    StockAdjustmentCreateView,
    StockAdjustmentDetailView,
    StockAdjustmentPostView,
)
from inventory.views.transfers import (
    StockTransferListView,
    StockTransferCreateView,
)

__all__ = [
    'InventoryDashboardView',
    'WarehouseListView',
    'WarehouseCreateView',
    'WarehouseUpdateView',
    'WarehouseDetailView',
    'StockLedgerListView',
    'StockValuationReportView',
    'StockAdjustmentListView',
    'StockAdjustmentCreateView',
    'StockAdjustmentDetailView',
    'StockAdjustmentPostView',
    'StockTransferListView',
    'StockTransferCreateView',
]
