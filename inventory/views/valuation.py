"""
Stock Valuation Views
Comprehensive valuation reports by warehouse, category, and FIFO layer breakdown.
"""
import csv
from decimal import Decimal
from django.http import HttpResponse
from django.views.generic import TemplateView
from core.views.base import ModuleEnabledRequiredMixin, CSVExportMixin
from core.scoping import CompanyBranchScopeMixin
from inventory.models import Warehouse, ValuationLayer
from inventory.services.valuation_service import get_inventory_valuation_summary
from pos.models import Category


class StockValuationReportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, CSVExportMixin, TemplateView):
    """
    Inventory Asset Valuation Report.
    Displays on-hand quantity, moving weighted average cost rate, total asset value, and open FIFO layers.
    """
    template_name = 'inventory/valuation/report.html'
    module_key = 'inventory'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        if not company:
            return ctx

        warehouse_id = self.request.GET.get('warehouse')
        warehouse = None
        if warehouse_id:
            warehouse = Warehouse.objects.filter(company=company, pk=warehouse_id).first()

        category_id = self.request.GET.get('category')

        summary = get_inventory_valuation_summary(company, warehouse=warehouse)
        items = summary.get('items', [])

        if category_id:
            items = [s for s in items if str(getattr(s['product'], 'category_id', '')) == str(category_id)]

        q = self.request.GET.get('q', '').strip().lower()
        if q:
            items = [
                s for s in items
                if q in s['product'].name.lower() or q in getattr(s['product'], 'product_code', '').lower()
            ]

        total_valuation = sum((item['total_value'] for item in items), Decimal('0.00'))
        total_quantity = sum((item['balance_quantity'] for item in items), Decimal('0.0000'))
        total_items_count = len(items)

        # Open FIFO layers for drilldown
        open_layers = (
            ValuationLayer.objects.filter(company=company, is_exhausted=False)
            .select_related('warehouse', 'product')
            .order_by('product__name', 'received_date')
        )
        if warehouse:
            open_layers = open_layers.filter(warehouse=warehouse)

        ctx.update({
            'valuation_items': summary,
            'total_valuation': total_valuation,
            'total_quantity': total_quantity,
            'total_items_count': total_items_count,
            'warehouses': Warehouse.objects.filter(company=company, is_active=True),
            'categories': Category.objects.all(),
            'open_layers': open_layers,
            'current_warehouse': warehouse_id or '',
            'current_category': category_id or '',
            'current_q': self.request.GET.get('q', ''),
        })
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'csv':
            return self.export_as_csv(context['valuation_items'])
        return super().render_to_response(context, **response_kwargs)

    def export_as_csv(self, items):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="inventory_valuation_report.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Warehouse',
            'Product Code',
            'Product Name',
            'Category',
            'Balance Quantity',
            'Valuation Rate (KES)',
            'Total Valuation (KES)',
        ])
        for item in items:
            p = item['product']
            writer.writerow([
                item['warehouse'].name,
                getattr(p, 'product_code', ''),
                p.name,
                getattr(p.category, 'name', 'N/A') if getattr(p, 'category', None) else 'N/A',
                f"{item['balance_quantity']:.4f}",
                f"{item['valuation_rate']:.4f}",
                f"{item['total_value']:.2f}",
            ])
        return response
