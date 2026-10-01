"""
Base Class-Based Views and Mixins for Platform Modules
"""
import csv
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
    TemplateView,
)
from core.registry import module_registry
from core.scoping import CompanyBranchScopeMixin, get_current_company


class ModuleEnabledRequiredMixin:
    """
    Ensures the business module owning this view is enabled for the current company.
    """
    module_key: str = ''

    def dispatch(self, request, *args, **kwargs):
        if self.module_key:
            company = get_current_company(request)
            company_id = company.id if company else None
            if not module_registry.is_enabled(self.module_key, company_id):
                messages.error(request, f"The '{self.module_key.upper()}' module is currently disabled.")
                raise PermissionDenied(f"Module '{self.module_key}' is not active for this company.")
        return super().dispatch(request, *args, **kwargs)


class CSVExportMixin:
    """
    Mixin that adds a `export_csv()` method to any ListView.
    """
    csv_filename = 'export.csv'
    csv_headers = []
    csv_fields = []

    def export_csv(self, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.csv_filename}"'

        writer = csv.writer(response)
        if self.csv_headers:
            writer.writerow(self.csv_headers)
        elif self.csv_fields:
            writer.writerow([f.replace('_', ' ').title() for f in self.csv_fields])

        for obj in queryset:
            row = []
            for field in self.csv_fields:
                val = getattr(obj, field, '')
                if callable(val):
                    val = val()
                row.append(str(val) if val is not None else '')
            writer.writerow(row)

        return response


class CoreListView(LoginRequiredMixin, ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    """Standard base ListView with authentication, scoping, and module enablement check."""
    paginate_by = 25


class CoreDetailView(LoginRequiredMixin, ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    """Standard base DetailView."""
    pass


class CoreCreateView(LoginRequiredMixin, ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, CreateView):
    """Standard base CreateView with auto-populated company and author fields."""
    success_message = "Record created successfully."

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response


class CoreUpdateView(LoginRequiredMixin, ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, UpdateView):
    """Standard base UpdateView."""
    success_message = "Record updated successfully."

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response


class CoreDeleteView(LoginRequiredMixin, ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DeleteView):
    """Standard base DeleteView."""
    success_message = "Record deleted successfully."

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        if self.success_message:
            messages.success(self.request, self.success_message)
        return response
