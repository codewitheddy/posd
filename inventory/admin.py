"""
Django Admin Configuration for Inventory & Stock Ledger
"""
from django.contrib import admin
from inventory.models import (
    Warehouse,
    StockItemSettings,
    StockLedgerEntry,
    ValuationLayer,
    StockAdjustmentDocument,
    StockAdjustmentLine,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'warehouse_type', 'company', 'branch', 'is_primary', 'is_active']
    list_filter = ['warehouse_type', 'is_primary', 'is_active', 'company']
    search_fields = ['code', 'name']


@admin.register(StockItemSettings)
class StockItemSettingsAdmin(admin.ModelAdmin):
    list_display = ['product', 'valuation_method', 'allow_negative_stock', 'reorder_level', 'reorder_quantity', 'company']
    list_filter = ['valuation_method', 'allow_negative_stock', 'company']
    search_fields = ['product__name', 'product__product_code']


@admin.register(StockLedgerEntry)
class StockLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ['posting_time', 'voucher_type', 'voucher_no', 'product', 'warehouse', 'quantity', 'unit_cost', 'balance_quantity', 'valuation_rate', 'balance_value', 'is_reversal']
    list_filter = ['voucher_type', 'is_reversal', 'warehouse', 'company']
    search_fields = ['voucher_no', 'product__name', 'batch_number', 'serial_number']
    readonly_fields = [f.name for f in StockLedgerEntry._meta.fields]

    def has_add_permission(self, request):
        return False  # Append-only ledger; entries created via services only

    def has_delete_permission(self, request, obj=None):
        return False  # Immutable ledger; no deletions allowed


@admin.register(ValuationLayer)
class ValuationLayerAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'batch_number', 'original_quantity', 'remaining_quantity', 'unit_cost', 'received_date', 'is_exhausted']
    list_filter = ['is_exhausted', 'warehouse', 'company']
    search_fields = ['product__name', 'batch_number']
    readonly_fields = [f.name for f in ValuationLayer._meta.fields]


class StockAdjustmentLineInline(admin.TabularInline):
    model = StockAdjustmentLine
    extra = 0
    readonly_fields = ['system_quantity', 'variance_quantity', 'unit_cost', 'total_variance_cost']


@admin.register(StockAdjustmentDocument)
class StockAdjustmentDocumentAdmin(admin.ModelAdmin):
    list_display = ['adjustment_number', 'warehouse', 'reason', 'status', 'adjustment_date', 'total_variance_value', 'company']
    list_filter = ['status', 'reason', 'warehouse', 'company']
    search_fields = ['adjustment_number']
    inlines = [StockAdjustmentLineInline]
