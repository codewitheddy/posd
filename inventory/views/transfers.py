"""
Inter-Warehouse Transfer Views
Move stock atomically between warehouses with balanced dispatch and receipt entries.
"""
from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib import messages
from django.views.generic import ListView, View
from django.core.exceptions import ValidationError
from core.views.base import ModuleEnabledRequiredMixin
from core.scoping import CompanyBranchScopeMixin
from inventory.models import StockLedgerEntry, Warehouse
from inventory.forms import StockTransferForm
from inventory.services.stock_transfer_service import transfer_stock_between_warehouses
from pos.models import Product


class StockTransferListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    """List of all inter-warehouse transfers."""
    model = StockLedgerEntry
    template_name = 'inventory/transfers/list.html'
    context_object_name = 'transfers'
    paginate_by = 25
    module_key = 'inventory'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return StockLedgerEntry.objects.none()
        return (
            StockLedgerEntry.objects.filter(
                company=company,
                voucher_type__in=[
                    StockLedgerEntry.VOUCHER_TRANSFER_OUT,
                    StockLedgerEntry.VOUCHER_TRANSFER_IN,
                ],
            )
            .select_related('warehouse', 'product', 'created_by')
            .order_by('-posting_time', '-id')
        )


class StockTransferCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Create and execute an inter-warehouse stock transfer."""
    module_key = 'inventory'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        form = StockTransferForm(company=company)
        products = Product.objects.filter(is_active=True).order_by('name')
        return render(request, 'inventory/transfers/form.html', {
            'form': form,
            'products': products,
        })

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = StockTransferForm(request.POST, company=company)
        if not form.is_valid():
            products = Product.objects.filter(is_active=True).order_by('name')
            return render(request, 'inventory/transfers/form.html', {
                'form': form,
                'products': products,
            })

        source_warehouse = form.cleaned_data['source_warehouse']
        target_warehouse = form.cleaned_data['target_warehouse']
        narration = form.cleaned_data['narration']

        product_ids = request.POST.getlist('product_id[]')
        qtys = request.POST.getlist('quantity[]')

        items_data = []
        for pid, qty_str in zip(product_ids, qtys):
            if not pid or not qty_str:
                continue
            try:
                prod = Product.objects.get(pk=pid)
                qty = Decimal(str(qty_str))
                if qty > 0:
                    items_data.append({
                        'product': prod,
                        'quantity': qty,
                    })
            except Exception:
                continue

        if not items_data:
            messages.error(request, "Please add at least one product with a transfer quantity greater than 0.")
            products = Product.objects.filter(is_active=True).order_by('name')
            return render(request, 'inventory/transfers/form.html', {
                'form': form,
                'products': products,
            })

        try:
            trf_no, entries = transfer_stock_between_warehouses(
                company=company,
                source_warehouse=source_warehouse,
                target_warehouse=target_warehouse,
                items_data=items_data,
                narration=narration,
                user=request.user,
            )
            messages.success(
                request,
                f"Transfer '{trf_no}' completed successfully. Moved {len(items_data)} items from {source_warehouse.code} to {target_warehouse.code}."
            )
            return redirect('inventory_transfer_list')
        except ValidationError as e:
            messages.error(request, f"Transfer failed: {e}")
            products = Product.objects.filter(is_active=True).order_by('name')
            return render(request, 'inventory/transfers/form.html', {
                'form': form,
                'products': products,
            })
        except Exception as e:
            messages.error(request, f"Unexpected error during transfer: {e}")
            products = Product.objects.filter(is_active=True).order_by('name')
            return render(request, 'inventory/transfers/form.html', {
                'form': form,
                'products': products,
            })
