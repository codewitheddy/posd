"""
Inventory & Stock Ledger Module Manifest
Registers the module with Platform Core Backoffice navigation, roles, and dashboard.
"""
from core.registry import ModuleManifest, MenuSection, MenuItem, DashboardCard

manifest = ModuleManifest(
    key='inventory',
    name='Inventory & Stock Ledger',
    version='1.0.0',
    description='Perpetual Stock Ledger, Moving Weighted Average Valuation, Multi-Warehouse Management, FIFO Layers, Adjustments & Transfers',
    icon='bi bi-boxes',
    dependencies=[],
    permission_prefix='inventory',
    default_roles={
        'Inventory Director': [
            'inventory.view_all',
            'inventory.manage_warehouses',
            'inventory.post_adjustments',
            'inventory.transfer_stock',
            'inventory.view_valuation',
            'inventory.reverse_movements',
        ],
        'Warehouse Manager': [
            'inventory.view_all',
            'inventory.manage_warehouses',
            'inventory.post_adjustments',
            'inventory.transfer_stock',
            'inventory.view_valuation',
        ],
        'Storekeeper': [
            'inventory.view_all',
            'inventory.transfer_stock',
            'inventory.create_adjustments',
        ],
        'Stock Auditor': [
            'inventory.view_all',
            'inventory.view_valuation',
        ],
    },
    menu_sections=[
        MenuSection(
            title='Warehouses & Locations',
            order=30,
            items=[
                MenuItem(
                    title='Inventory Hub',
                    url_name='inventory_dashboard',
                    icon='bi bi-speedometer2',
                    order=10,
                ),
                MenuItem(
                    title='Warehouses',
                    url_name='inventory_warehouse_list',
                    icon='bi bi-building',
                    order=20,
                ),
            ],
        ),
        MenuSection(
            title='Stock Movement & Valuation',
            order=35,
            items=[
                MenuItem(
                    title='Stock Ledger',
                    url_name='inventory_ledger_list',
                    icon='bi bi-receipt-cutoff',
                    order=10,
                ),
                MenuItem(
                    title='Valuation Report',
                    url_name='inventory_valuation_report',
                    icon='bi bi-graph-up-arrow',
                    order=20,
                ),
            ],
        ),
        MenuSection(
            title='Stock Operations',
            order=40,
            items=[
                MenuItem(
                    title='Stock Adjustments',
                    url_name='inventory_adjustment_list',
                    icon='bi bi-sliders',
                    order=10,
                ),
                MenuItem(
                    title='Inter-Warehouse Transfers',
                    url_name='inventory_transfer_list',
                    icon='bi bi-arrow-left-right',
                    order=20,
                ),
            ],
        ),
    ],
    dashboard_cards=[],
    url_prefix='/inventory/',
)
