"""
Inventory Dashboard View
Provides KPI overview of stock valuation, warehouse summaries, low stock warnings, and recent movements.
"""
from decimal import Decimal
from django.views.generic import TemplateView
from core.views.base import ModuleEnabledRequiredMixin
from core.scoping import CompanyBranchScopeMixin
from inventory.models import Warehouse, StockLedgerEntry, StockItemSettings
from inventory.services.valuation_service import get_inventory_valuation_summary
from inventory.selectors.stock_selectors import get_low_stock_items
from pos.models import Product


class InventoryDashboardView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, TemplateView):
    """Inventory Command Center & Dashboard."""
    template_name = 'inventory/dashboard.html'
    module_key = 'inventory'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        if not company:
            return ctx

        from core.models.organization import Branch as CoreBranch
        branch = self.get_branch()
        warehouses_qs = Warehouse.objects.filter(company=company, is_active=True)
        if branch:
            if not isinstance(branch, CoreBranch):
                branch = CoreBranch.objects.filter(company=company, code=getattr(branch, 'code', '')).first()
            if branch:
                warehouses_qs = warehouses_qs.filter(branch=branch)

        # 1. Valuation Summary
        valuation_summary = get_inventory_valuation_summary(company)
        total_valuation = valuation_summary.get('total_valuation', Decimal('0.00'))
        total_items_in_stock = valuation_summary.get('total_units', Decimal('0.0000'))

        # 2. Warehouses summary
        warehouses = list(warehouses_qs)

        # 3. Low stock alerts
        low_stock_alerts = get_low_stock_items(company)

        # 4. Recent Stock Movements (last 10)
        recent_movements = (
            StockLedgerEntry.objects.filter(company=company)
            .select_related('warehouse', 'product', 'created_by')
            .order_by('-posting_time', '-id')[:10]
        )

        ctx.update({
            'total_valuation': total_valuation,
            'total_items_in_stock': total_items_in_stock,
            'warehouses_count': len(warehouses),
            'warehouses': warehouses,
            'low_stock_alerts': low_stock_alerts,
            'low_stock_count': len(low_stock_alerts),
            'recent_movements': recent_movements,
            'total_skus': Product.objects.filter(is_active=True).count(),
        })
        return ctx
