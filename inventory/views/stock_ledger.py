"""
Stock Ledger Views
Immutable append-only transaction history explorer with multi-dimensional filtering, pagination, and CSV export.
"""
import csv
from decimal import Decimal
from django.http import HttpResponse
from django.views.generic import ListView
from core.views.base import ModuleEnabledRequiredMixin, CSVExportMixin
from core.scoping import CompanyBranchScopeMixin
from inventory.models import StockLedgerEntry, Warehouse
from inventory.selectors.stock_selectors import get_stock_ledger_entries
from pos.models import Product


class StockLedgerListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, CSVExportMixin, ListView):
    """
    Searchable, filterable ledger view of all immutable inventory stock movements.
    """
    model = StockLedgerEntry
    template_name = 'inventory/ledger/list.html'
    context_object_name = 'entries'
    paginate_by = 30
    module_key = 'inventory'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return StockLedgerEntry.objects.none()

        qs = StockLedgerEntry.objects.filter(company=company).select_related(
            'warehouse', 'product', 'created_by'
        )

        # Filters
        warehouse_id = self.request.GET.get('warehouse')
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)

        product_id = self.request.GET.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)

        voucher_type = self.request.GET.get('voucher_type')
        if voucher_type:
            qs = qs.filter(voucher_type=voucher_type)

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(voucher_no__icontains=q) | qs.filter(product__name__icontains=q) | qs.filter(product__product_code__icontains=q)

        start_date = self.request.GET.get('start_date')
        if start_date:
            qs = qs.filter(posting_date__gte=start_date)

        end_date = self.request.GET.get('end_date')
        if end_date:
            qs = qs.filter(posting_date__lte=end_date)

        return qs.order_by('-posting_time', '-id')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        ctx['warehouses'] = Warehouse.objects.filter(company=company, is_active=True)
        ctx['voucher_types'] = StockLedgerEntry.VOUCHER_TYPE_CHOICES
        ctx['current_warehouse'] = self.request.GET.get('warehouse', '')
        ctx['current_voucher_type'] = self.request.GET.get('voucher_type', '')
        ctx['current_q'] = self.request.GET.get('q', '')
        ctx['current_start_date'] = self.request.GET.get('start_date', '')
        ctx['current_end_date'] = self.request.GET.get('end_date', '')
        return ctx

    def render_to_response(self, context, **response_kwargs):
        if self.request.GET.get('export') == 'csv':
            return self.export_as_csv(self.get_queryset())
        return super().render_to_response(context, **response_kwargs)

    def export_as_csv(self, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="stock_ledger_export.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Posting Date',
            'Posting Time',
            'Warehouse',
            'Product Code',
            'Product Name',
            'Voucher Type',
            'Voucher No',
            'Quantity Delta',
            'Unit Cost (KES)',
            'Total Cost (KES)',
            'Balance Qty',
            'Valuation Rate (KES)',
            'Balance Value (KES)',
            'Created By',
        ])
        for entry in queryset:
            writer.writerow([
                entry.posting_date.isoformat(),
                entry.posting_time.strftime('%Y-%m-%d %H:%M:%S'),
                entry.warehouse.code,
                getattr(entry.product, 'product_code', ''),
                entry.product.name,
                entry.get_voucher_type_display(),
                entry.voucher_no,
                f"{entry.quantity:+.4f}",
                f"{entry.unit_cost:.4f}",
                f"{entry.total_cost:.2f}",
                f"{entry.balance_quantity:.4f}",
                f"{entry.valuation_rate:.4f}",
                f"{entry.balance_value:.2f}",
                entry.created_by.username if entry.created_by else 'System',
            ])
        return response
