"""
Accounting Module Django Forms
"""
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from accounting.models import (
    Account, AccountType, AccountCategory, NormalBalance,
    FiscalYear, FiscalPeriod, JournalEntry, JournalEntryLine
)


class AccountForm(forms.ModelForm):
    """Form to create or update an Account in the Chart of Accounts."""
    class Meta:
        model = Account
        fields = [
            'code', 'name', 'account_type', 'category', 'normal_balance',
            'parent', 'currency', 'is_reconciliation', 'is_active', 'is_locked', 'description'
        ]
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'e.g. 1010, 2100, 4000'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Cash in Till'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'normal_balance': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'KES'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Account purpose and reporting classification'}),
            'is_reconciliation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_locked': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company:
            self.fields['parent'].queryset = Account.objects.filter(company=company, is_active=True).order_by('code')
            if self.instance and self.instance.pk:
                # Exclude self from parent choices
                self.fields['parent'].queryset = self.fields['parent'].queryset.exclude(pk=self.instance.pk)

    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip()
        if not code:
            raise ValidationError("Account Code is required.")
        qs = Account.objects.filter(company=self.company, code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"An account with code '{code}' already exists in your company.")
        return code


class ManualJournalEntryForm(forms.Form):
    """Header form for manual general journal entry creation."""
    date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Transaction Date"
    )
    narration = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Description and business justification'}),
        label="Narration / Purpose"
    )
    branch = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Analytic Branch (Optional)"
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            from core.models.organization import Branch
            self.fields['branch'].queryset = Branch.objects.filter(company=company, is_active=True).order_by('name')


class TrialBalanceFilterForm(forms.Form):
    """Filter form for Trial Balance & General Ledger reports."""
    as_of_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
        required=False,
        label="As of Date"
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
        required=False,
        label="From Date (Optional)"
    )
    branch = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label="Branch Filter"
    )

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            from core.models.organization import Branch
            self.fields['branch'].queryset = Branch.objects.filter(company=company, is_active=True).order_by('name')


class POSGLMappingForm(forms.Form):
    """Configuration form for POS integration GL account mappings."""
    cash_account_code = forms.ChoiceField(label="Cash in Till Account", widget=forms.Select(attrs={'class': 'form-select'}))
    mpesa_account_code = forms.ChoiceField(label="M-Pesa Clearing Account", widget=forms.Select(attrs={'class': 'form-select'}))
    card_account_code = forms.ChoiceField(label="Card / Swipe Clearing Account", widget=forms.Select(attrs={'class': 'form-select'}))
    credit_account_code = forms.ChoiceField(label="Customer AR Account", widget=forms.Select(attrs={'class': 'form-select'}))
    sales_revenue_code = forms.ChoiceField(label="Sales Revenue Account", widget=forms.Select(attrs={'class': 'form-select'}))
    vat_output_code = forms.ChoiceField(label="VAT Output Account", widget=forms.Select(attrs={'class': 'form-select'}))
    cogs_account_code = forms.ChoiceField(label="COGS Account", widget=forms.Select(attrs={'class': 'form-select'}))
    inventory_account_code = forms.ChoiceField(label="Inventory Asset Account", widget=forms.Select(attrs={'class': 'form-select'}))
    cash_variance_code = forms.ChoiceField(label="Cash Short/Over Account", widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, company=None, initial=None, **kwargs):
        super().__init__(*args, initial=initial, **kwargs)
        if company:
            accounts = Account.objects.filter(company=company, is_active=True).order_by('code')
        else:
            accounts = Account.objects.filter(is_active=True).order_by('code')
        choices = [(a.code, f"{a.code} - {a.name} ({a.get_account_type_display()})") for a in accounts]
        for field_name in self.fields:
            self.fields[field_name].choices = choices or [('', '-- Select Account --')]


class HRGLMappingForm(forms.Form):
    """Configuration form for HR & Payroll integration GL account mappings."""
    basic_salaries_expense_code = forms.ChoiceField(label="Salaries Expense Account", widget=forms.Select(attrs={'class': 'form-select'}))
    employer_nssf_expense_code = forms.ChoiceField(label="NSSF Employer Expense Account", widget=forms.Select(attrs={'class': 'form-select'}))
    employer_shif_expense_code = forms.ChoiceField(label="SHIF Employer Expense Account", widget=forms.Select(attrs={'class': 'form-select'}))
    employer_housing_levy_expense_code = forms.ChoiceField(label="Housing Levy Employer Expense", widget=forms.Select(attrs={'class': 'form-select'}))
    employer_nita_expense_code = forms.ChoiceField(label="NITA Employer Expense Account", widget=forms.Select(attrs={'class': 'form-select'}))
    net_salaries_payable_code = forms.ChoiceField(label="Net Salaries Payable Account", widget=forms.Select(attrs={'class': 'form-select'}))
    paye_payable_code = forms.ChoiceField(label="PAYE Payable Account", widget=forms.Select(attrs={'class': 'form-select'}))
    nssf_payable_code = forms.ChoiceField(label="NSSF Deductions Payable Account", widget=forms.Select(attrs={'class': 'form-select'}))
    shif_payable_code = forms.ChoiceField(label="SHIF Deductions Payable Account", widget=forms.Select(attrs={'class': 'form-select'}))
    housing_levy_payable_code = forms.ChoiceField(label="Housing Levy Payable Account", widget=forms.Select(attrs={'class': 'form-select'}))
    helb_payable_code = forms.ChoiceField(label="HELB Deductions Payable Account", widget=forms.Select(attrs={'class': 'form-select'}))
    staff_advances_asset_code = forms.ChoiceField(label="Staff Advances Asset Account", widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, company=None, initial=None, **kwargs):
        super().__init__(*args, initial=initial, **kwargs)
        if company:
            accounts = Account.objects.filter(company=company, is_active=True).order_by('code')
        else:
            accounts = Account.objects.filter(is_active=True).order_by('code')
        choices = [(a.code, f"{a.code} - {a.name} ({a.get_account_type_display()})") for a in accounts]
        for field_name in self.fields:
            self.fields[field_name].choices = choices or [('', '-- Select Account --')]


# ─── SUBLEDGER & RECONCILIATION FORMS ────────────────────────────────────────

class CustomerForm(forms.Form):
    name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Safaricom PLC'}))
    kra_pin = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'P051234567X'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    payment_terms_days = forms.IntegerField(initial=30, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    credit_limit = forms.DecimalField(initial=Decimal('0.00'), widget=forms.NumberInput(attrs={'class': 'form-control'}))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class VendorForm(forms.Form):
    name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Kenya Power & Lighting Co'}))
    kra_pin = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'P051100223A'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    payment_terms_days = forms.IntegerField(initial=30, widget=forms.NumberInput(attrs={'class': 'form-control'}))
    bank_account_details = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bank, Branch, Account No / Paybill'}))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class CustomerPaymentForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={'class': 'form-select'}))
    branch = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    receipt_number = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. REC-2026-001'}))
    payment_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    amount = forms.DecimalField(widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    payment_method = forms.ChoiceField(
        choices=[('mpesa', 'M-Pesa'), ('bank', 'Bank Transfer / RTGS'), ('cash', 'Cash'), ('cheque', 'Cheque'), ('card', 'Card')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    reference = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. M-Pesa Code QHD4829J1X'}))
    deposit_account = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={'class': 'form-select'}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            from accounting.models import Customer
            from core.models.organization import Branch
            self.fields['customer'].queryset = Customer.objects.filter(company=company, is_active=True).order_by('name')
            self.fields['branch'].queryset = Branch.objects.filter(company=company, is_active=True).order_by('name')
            self.fields['deposit_account'].queryset = Account.objects.filter(
                company=company,
                category__in=[AccountCategory.CASH_AND_BANK, AccountCategory.CURRENT_ASSET],
                is_active=True
            ).order_by('code')


class VendorPaymentForm(forms.Form):
    vendor = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={'class': 'form-select'}))
    branch = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    voucher_number = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. VOUCH-2026-001'}))
    payment_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    amount = forms.DecimalField(widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    payment_method = forms.ChoiceField(
        choices=[('bank', 'Bank Transfer / EFT / RTGS'), ('mpesa', 'M-Pesa B2B / Payout'), ('cash', 'Cash'), ('cheque', 'Cheque')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    reference = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. EFT Reference or Cheque #'}))
    paid_from_account = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={'class': 'form-select'}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            from accounting.models import Vendor
            from core.models.organization import Branch
            self.fields['vendor'].queryset = Vendor.objects.filter(company=company, is_active=True).order_by('name')
            self.fields['branch'].queryset = Branch.objects.filter(company=company, is_active=True).order_by('name')
            self.fields['paid_from_account'].queryset = Account.objects.filter(
                company=company,
                category__in=[AccountCategory.CASH_AND_BANK, AccountCategory.CURRENT_ASSET],
                is_active=True
            ).order_by('code')


class BankAccountForm(forms.Form):
    name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. KCB Operating Account'}))
    bank_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. KCB Bank Kenya / Safaricom'}))
    account_number = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'e.g. 1122334455 or Paybill 522522'}))
    gl_account = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs={'class': 'form-select'}))
    branch_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['gl_account'].queryset = Account.objects.filter(
                company=company,
                category=AccountCategory.CASH_AND_BANK,
                is_active=True
            ).order_by('code')


class BankStatementUploadForm(forms.Form):
    statement_type = forms.ChoiceField(
        choices=[('mpesa', 'Safaricom M-Pesa Statement CSV'), ('bank', 'Standard Kenyan Bank CSV Statement')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    csv_file = forms.FileField(widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}))


class DateRangeReportForm(forms.Form):
    start_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}))
    branch = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            from core.models.organization import Branch
            self.fields['branch'].queryset = Branch.objects.filter(company=company, is_active=True).order_by('name')


class BalanceSheetReportForm(forms.Form):
    as_of_date = forms.DateField(widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}))
    compare_as_of_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}))
    branch = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={'class': 'form-select form-select-sm'}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            from core.models.organization import Branch
            self.fields['branch'].queryset = Branch.objects.filter(company=company, is_active=True).order_by('name')


