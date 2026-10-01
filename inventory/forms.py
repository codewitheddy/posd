"""
Inventory Forms
Forms for Warehouse management, Stock Adjustments, Inter-Warehouse Transfers, and Stock Item Settings.
"""
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from inventory.models import (
    Warehouse,
    StockItemSettings,
    StockAdjustmentDocument,
    StockAdjustmentLine,
)
from core.models.organization import Company, Branch
from pos.models import Product


class WarehouseForm(forms.ModelForm):
    """Form for creating and updating Warehouses."""

    class Meta:
        model = Warehouse
        fields = [
            'name',
            'code',
            'warehouse_type',
            'branch',
            'is_primary',
            'is_active',
            'address',
            'manager',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Main Warehouse'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. WH-HQ'}),
            'warehouse_type': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Physical location or building address...'}),
            'manager': forms.Select(attrs={'class': 'form-select'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['branch'].queryset = Branch.objects.filter(company=self.company)
            # Filter users if needed
            from django.contrib.auth import get_user_model
            User = get_user_model()
            self.fields['manager'].queryset = User.objects.filter(is_active=True)

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip().upper()
        if not code:
            raise ValidationError("Warehouse code is required.")
        qs = Warehouse.objects.filter(code=code)
        if self.company:
            qs = qs.filter(company=self.company)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Warehouse with code '{code}' already exists.")
        return code


class StockItemSettingsForm(forms.ModelForm):
    """Form for product inventory valuation and negative stock settings."""

    class Meta:
        model = StockItemSettings
        fields = [
            'valuation_method',
            'allow_negative_stock',
            'reorder_level',
            'reorder_quantity',
            'default_warehouse',
        ]
        widgets = {
            'valuation_method': forms.Select(attrs={'class': 'form-select'}),
            'allow_negative_stock': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reorder_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'default_warehouse': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['default_warehouse'].queryset = Warehouse.objects.filter(
                company=self.company, is_active=True
            )


class StockAdjustmentForm(forms.ModelForm):
    """Form for creating a Stock Adjustment header."""

    class Meta:
        model = StockAdjustmentDocument
        fields = ['warehouse', 'adjustment_date', 'reason', 'notes']
        widgets = {
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'adjustment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Reason or recount audit reference...'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            self.fields['warehouse'].queryset = Warehouse.objects.filter(
                company=self.company, is_active=True
            )


class StockTransferForm(forms.Form):
    """Form for Inter-Warehouse Stock Transfers."""
    source_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Source Warehouse (From)",
    )
    target_warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Target Warehouse (To)",
    )
    narration = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reason for transfer (e.g. Retail shelf replenishment)'}),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if self.company:
            active_wh = Warehouse.objects.filter(company=self.company, is_active=True)
            self.fields['source_warehouse'].queryset = active_wh
            self.fields['target_warehouse'].queryset = active_wh

    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('source_warehouse')
        target = cleaned_data.get('target_warehouse')
        if source and target and source == target:
            raise ValidationError("Source and target warehouses cannot be the same.")
        return cleaned_data
