"""
Warehouse Management Views
List, Create, Update, and View details of multi-warehouse storage facilities.
"""
from decimal import Decimal
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from core.views.base import ModuleEnabledRequiredMixin
from core.scoping import CompanyBranchScopeMixin
from inventory.models import Warehouse, StockLedgerEntry
from inventory.forms import WarehouseForm
from inventory.services.valuation_service import get_inventory_valuation_summary


class WarehouseListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    """List all warehouses for the active company."""
    model = Warehouse
    template_name = 'inventory/warehouses/list.html'
    context_object_name = 'warehouses'
    module_key = 'inventory'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Warehouse.objects.none()
        qs = Warehouse.objects.filter(company=company).select_related('branch', 'manager')
        from core.models.organization import Branch as CoreBranch
        branch = self.get_branch()
        if branch:
            if not isinstance(branch, CoreBranch):
                branch = CoreBranch.objects.filter(company=company, code=getattr(branch, 'code', '')).first()
            if branch:
                qs = qs.filter(branch=branch)
        return qs.order_by('-is_primary', 'name')


class WarehouseCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, CreateView):
    """Create a new Warehouse."""
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouses/form.html'
    module_key = 'inventory'
    success_url = reverse_lazy('inventory_warehouse_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['company'] = self.get_company()
        return kwargs

    def form_valid(self, form):
        form.instance.company = self.get_company()
        form.instance.created_by = self.request.user
        if form.instance.is_primary:
            # Set other warehouses is_primary to False for this company
            Warehouse.objects.filter(company=self.get_company(), is_primary=True).update(is_primary=False)
        messages.success(self.request, f"Warehouse '{form.instance.name}' created successfully.")
        return super().form_valid(form)


class WarehouseUpdateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, UpdateView):
    """Update existing Warehouse."""
    model = Warehouse
    form_class = WarehouseForm
    template_name = 'inventory/warehouses/form.html'
    module_key = 'inventory'
    success_url = reverse_lazy('inventory_warehouse_list')

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Warehouse.objects.none()
        return Warehouse.objects.filter(company=company)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['company'] = self.get_company()
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        if form.instance.is_primary:
            Warehouse.objects.filter(company=self.get_company(), is_primary=True).exclude(pk=form.instance.pk).update(is_primary=False)
        messages.success(self.request, f"Warehouse '{form.instance.name}' updated successfully.")
        return super().form_valid(form)


class WarehouseDetailView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    """Detailed view of a warehouse with stock balances and recent transactions."""
    model = Warehouse
    template_name = 'inventory/warehouses/detail.html'
    context_object_name = 'warehouse'
    module_key = 'inventory'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Warehouse.objects.none()
        return Warehouse.objects.filter(company=company)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        warehouse = self.object

        # Stock summary for this warehouse
        summary = get_inventory_valuation_summary(company, warehouse=warehouse)
        ctx['stock_items'] = summary.get('items', [])
        ctx['total_valuation'] = summary.get('total_valuation', Decimal('0.00'))
        ctx['total_quantity'] = summary.get('total_units', Decimal('0.0000'))

        # Recent entries
        ctx['recent_movements'] = (
            StockLedgerEntry.objects.filter(company=company, warehouse=warehouse)
            .select_related('product', 'created_by')
            .order_by('-posting_time', '-id')[:25]
        )
        return ctx
