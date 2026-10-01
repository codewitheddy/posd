"""
Stock Adjustment Views
Stock Count Reconciliation, Physical Audits, Shrinkage/Damage Write-Offs.
"""
import json
from decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.views.generic import ListView, DetailView, CreateView, View
from django.core.exceptions import ValidationError
from core.views.base import ModuleEnabledRequiredMixin
from core.scoping import CompanyBranchScopeMixin
from inventory.models import StockAdjustmentDocument, StockAdjustmentLine, Warehouse
from inventory.forms import StockAdjustmentForm
from inventory.services.stock_adjustment_service import create_stock_adjustment, post_stock_adjustment
from pos.models import Product


class StockAdjustmentListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    """List of all stock adjustment documents."""
    model = StockAdjustmentDocument
    template_name = 'inventory/adjustments/list.html'
    context_object_name = 'adjustments'
    paginate_by = 25
    module_key = 'inventory'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return StockAdjustmentDocument.objects.none()
        qs = StockAdjustmentDocument.objects.filter(company=company).select_related('warehouse', 'created_by')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-adjustment_date', '-created_at')


class StockAdjustmentCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Create a new stock adjustment document with line items."""
    module_key = 'inventory'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        form = StockAdjustmentForm(company=company)
        warehouses = Warehouse.objects.filter(company=company, is_active=True)
        products = Product.objects.filter(is_active=True).order_by('name')
        return render(request, 'inventory/adjustments/form.html', {
            'form': form,
            'warehouses': warehouses,
            'products': products,
        })

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = StockAdjustmentForm(request.POST, company=company)
        if not form.is_valid():
            warehouses = Warehouse.objects.filter(company=company, is_active=True)
            products = Product.objects.filter(is_active=True).order_by('name')
            return render(request, 'inventory/adjustments/form.html', {
                'form': form,
                'warehouses': warehouses,
                'products': products,
            })

        warehouse = form.cleaned_data['warehouse']
        reason = form.cleaned_data['reason']
        notes = form.cleaned_data['notes']
        adjustment_date = form.cleaned_data['adjustment_date']

        # Parse line items
        product_ids = request.POST.getlist('product_id[]')
        counted_qtys = request.POST.getlist('counted_qty[]')

        lines_data = []
        for pid, qty_str in zip(product_ids, counted_qtys):
            if not pid or not qty_str:
                continue
            try:
                prod = Product.objects.get(pk=pid)
                qty = Decimal(str(qty_str))
                lines_data.append({
                    'product': prod,
                    'counted_quantity': qty,
                })
            except Exception as e:
                continue

        if not lines_data:
            messages.error(request, "Please add at least one product with a counted quantity.")
            warehouses = Warehouse.objects.filter(company=company, is_active=True)
            products = Product.objects.filter(is_active=True).order_by('name')
            return render(request, 'inventory/adjustments/form.html', {
                'form': form,
                'warehouses': warehouses,
                'products': products,
            })

        try:
            doc = create_stock_adjustment(
                company=company,
                warehouse=warehouse,
                reason=reason,
                lines_data=lines_data,
                notes=notes,
                adjustment_date=adjustment_date,
                created_by=request.user,
            )
            messages.success(request, f"Stock Adjustment '{doc.adjustment_number}' draft created successfully.")
            return redirect('inventory_adjustment_detail', pk=doc.pk)
        except ValidationError as e:
            messages.error(request, str(e))
            warehouses = Warehouse.objects.filter(company=company, is_active=True)
            products = Product.objects.filter(is_active=True).order_by('name')
            return render(request, 'inventory/adjustments/form.html', {
                'form': form,
                'warehouses': warehouses,
                'products': products,
            })


class StockAdjustmentDetailView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    """View details of a stock adjustment document."""
    model = StockAdjustmentDocument
    template_name = 'inventory/adjustments/detail.html'
    context_object_name = 'adjustment'
    module_key = 'inventory'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return StockAdjustmentDocument.objects.none()
        return StockAdjustmentDocument.objects.filter(company=company).select_related('warehouse', 'created_by')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['lines'] = self.object.lines.select_related('product').all()
        return ctx


class StockAdjustmentPostView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Post an approved stock adjustment draft to the immutable Stock Ledger."""
    module_key = 'inventory'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        doc = get_object_or_404(StockAdjustmentDocument, pk=pk, company=company)
        if doc.status == StockAdjustmentDocument.STATUS_POSTED:
            messages.info(request, f"Stock Adjustment '{doc.adjustment_number}' is already posted.")
            return redirect('inventory_adjustment_detail', pk=doc.pk)

        try:
            posted_entries = post_stock_adjustment(doc, user=request.user)
            messages.success(
                request,
                f"Successfully posted {len(posted_entries)} movement entries to the Stock Ledger for {doc.adjustment_number}."
            )
        except ValidationError as e:
            messages.error(request, f"Cannot post adjustment: {e}")
        except Exception as e:
            messages.error(request, f"Error posting adjustment: {e}")

        return redirect('inventory_adjustment_detail', pk=doc.pk)
