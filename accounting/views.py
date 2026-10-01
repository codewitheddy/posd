"""
Accounting & General Ledger Class-Based Views
Standards: IFRS for SMEs / ICPAK Practice
"""
import csv
from decimal import Decimal
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.views import View
from django.views.generic import TemplateView, ListView, DetailView, CreateView, UpdateView
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.exceptions import ValidationError

from core.views import ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, CSVExportMixin
from core.models.organization import Company, Branch
from accounting.models import (
    Account, AccountType, AccountCategory, NormalBalance,
    FiscalYear, FiscalPeriod, JournalEntry, JournalEntryLine,
    JournalEntryType, JournalEntryStatus, PostingQueue,
    Customer, Vendor,
    CustomerInvoice, CustomerInvoiceLine, InvoiceStatus,
    CustomerPayment, CustomerPaymentAllocation,
    VendorBill, VendorBillLine, BillStatus,
    VendorPayment, VendorPaymentAllocation,
    BankAccount, BankStatement, BankStatementLine, BankReconciliation,
    WithholdingTaxRecord, WHTType, WHTCategory
)
from accounting.forms import (
    AccountForm, ManualJournalEntryForm, TrialBalanceFilterForm,
    POSGLMappingForm, HRGLMappingForm,
    CustomerForm, VendorForm, CustomerPaymentForm, VendorPaymentForm,
    BankAccountForm, BankStatementUploadForm, DateRangeReportForm, BalanceSheetReportForm
)
from accounting.services import JournalPostingService, FiscalPeriodService, ARService, APService, BankReconciliationService, TaxService
from accounting.selectors import (
    TrialBalanceSelector, GeneralLedgerSelector,
    get_income_statement, get_balance_sheet, get_cash_flow_statement,
    get_vat_return_summary, get_wht_return_summary,
    get_ar_aging_report, get_ap_aging_report, get_bank_reconciliation_summary
)
from accounting import api


class AccountingDashboardView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, TemplateView):
    """
    Accounting Central Command Dashboard.
    Provides real-time financial health KPIs, period status, recent journals, and quick actions.
    """
    template_name = 'accounting/dashboard.html'
    module_key = 'accounting'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        if not company:
            return ctx

        today = timezone.localdate()
        current_period = FiscalPeriodService.get_period_for_date(company, today)
        current_year = current_period.fiscal_year if current_period else FiscalYear.objects.filter(company=company, is_closed=False).first()

        # Compute KPI Balances from Trial Balance selector
        tb_data = TrialBalanceSelector.get_trial_balance(company, as_of_date=today)

        total_assets = sum((r['closing_debit'] for r in tb_data['rows'] if r['account_type'] == AccountType.ASSET), Decimal('0.00'))
        total_liabilities = sum((r['closing_credit'] for r in tb_data['rows'] if r['account_type'] == AccountType.LIABILITY), Decimal('0.00'))
        total_equity = sum((r['closing_credit'] for r in tb_data['rows'] if r['account_type'] == AccountType.EQUITY), Decimal('0.00'))
        total_revenue = sum((r['closing_credit'] for r in tb_data['rows'] if r['account_type'] == AccountType.INCOME), Decimal('0.00'))
        total_expenses = sum((r['closing_debit'] for r in tb_data['rows'] if r['account_type'] == AccountType.EXPENSE), Decimal('0.00'))

        net_profit_loss = total_revenue - total_expenses

        # Recent Journals
        recent_journals = JournalEntry.objects.filter(
            company=company
        ).select_related('posted_by', 'branch').order_by('-date', '-created_at')[:10]

        # Accounts count
        accounts_count = Account.objects.filter(company=company, is_active=True).count()

        ctx.update({
            'company': company,
            'current_period': current_period,
            'current_year': current_year,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
            'total_revenue': total_revenue,
            'total_expenses': total_expenses,
            'net_profit_loss': net_profit_loss,
            'is_balanced': tb_data['is_balanced'],
            'trial_balance_difference': tb_data['difference'],
            'recent_journals': recent_journals,
            'accounts_count': accounts_count,
            'today': today,
        })
        return ctx


# ─── Chart of Accounts Views ──────────────────────────────────────────────────

class AccountListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    """List and tree hierarchy view for the Chart of Accounts."""
    template_name = 'accounting/accounts/account_list.html'
    context_object_name = 'accounts'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Account.objects.none()

        qs = Account.objects.filter(company=company).select_related('parent').order_by('code')

        acct_type = self.request.GET.get('type', '').strip()
        if acct_type in AccountType.values:
            qs = qs.filter(account_type=acct_type)

        search = self.request.GET.get('q', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search) | Q(system_tag__icontains=search))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['account_types'] = AccountType.choices
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class AccountCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, CreateView):
    """Create a new account in the Chart of Accounts."""
    model = Account
    form_class = AccountForm
    template_name = 'accounting/accounts/account_form.html'
    module_key = 'accounting'
    success_url = reverse_lazy('accounting_account_list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['company'] = self.get_company()
        return kwargs

    def form_valid(self, form):
        form.instance.company = self.get_company()
        form.instance.created_by = self.request.user
        messages.success(self.request, f"Account '{form.instance.code} - {form.instance.name}' created successfully.")
        return super().form_valid(form)


class AccountUpdateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, UpdateView):
    """Update an existing account in the Chart of Accounts."""
    model = Account
    form_class = AccountForm
    template_name = 'accounting/accounts/account_form.html'
    module_key = 'accounting'
    success_url = reverse_lazy('accounting_account_list')

    def get_queryset(self):
        return Account.objects.filter(company=self.get_company())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['company'] = self.get_company()
        return kwargs

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, f"Account '{form.instance.code} - {form.instance.name}' updated successfully.")
        return super().form_valid(form)


class AccountDetailView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    """Detail view showing account metadata and recent transactions."""
    model = Account
    template_name = 'accounting/accounts/account_detail.html'
    context_object_name = 'account'
    module_key = 'accounting'

    def get_queryset(self):
        return Account.objects.filter(company=self.get_company())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        account = self.object
        ledger_data = GeneralLedgerSelector.get_account_ledger(company, account)
        ctx.update(ledger_data)
        return ctx


# ─── Fiscal Years and Periods Views ──────────────────────────────────────────

class FiscalPeriodListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, TemplateView):
    """Manage Fiscal Years and Fiscal Periods."""
    template_name = 'accounting/periods/period_list.html'
    module_key = 'accounting'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        if not company:
            return ctx

        fiscal_years = FiscalYear.objects.filter(company=company).prefetch_related('periods').order_by('-start_date')
        ctx['fiscal_years'] = fiscal_years
        ctx['today'] = timezone.localdate()
        return ctx


class FiscalPeriodToggleCloseView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Toggle lock/unlock on a Fiscal Period."""
    module_key = 'accounting'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        period = get_object_or_404(FiscalPeriod, pk=pk, company=company)

        action = request.POST.get('action', 'toggle')
        reason = request.POST.get('reason', '')

        try:
            if period.is_closed:
                FiscalPeriodService.reopen_period(period, user=request.user, reason=reason)
                messages.success(request, f"Period '{period.name}' has been reopened.")
            else:
                FiscalPeriodService.close_period(period, user=request.user)
                messages.warning(request, f"Period '{period.name}' has been locked and closed.")
        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, 'message') else e))

        return redirect('accounting_period_list')


# ─── General Ledger Journal Entries Views ────────────────────────────────────

class JournalListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    """Browse and filter General Ledger Journal Entries."""
    template_name = 'accounting/journals/journal_list.html'
    context_object_name = 'journals'
    paginate_by = 25
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return JournalEntry.objects.none()

        qs = JournalEntry.objects.filter(company=company).select_related('posted_by', 'branch', 'reversal_entry').order_by('-date', '-created_at')

        # Filters
        source = self.request.GET.get('source', '').strip()
        if source:
            qs = qs.filter(source_module=source)

        entry_type = self.request.GET.get('type', '').strip()
        if entry_type:
            qs = qs.filter(entry_type=entry_type)

        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        search = self.request.GET.get('q', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(entry_number__icontains=search) | Q(source_ref__icontains=search) | Q(narration__icontains=search))

        start_d = self.request.GET.get('start_date')
        if start_d:
            qs = qs.filter(date__gte=start_d)

        end_d = self.request.GET.get('end_date')
        if end_d:
            qs = qs.filter(date__lte=end_d)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['entry_types'] = JournalEntryType.choices
        ctx['statuses'] = JournalEntryStatus.choices
        ctx['selected_source'] = self.request.GET.get('source', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class JournalDetailView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    """Detail view showing Journal Header and itemized Debit/Credit lines."""
    model = JournalEntry
    template_name = 'accounting/journals/journal_detail.html'
    context_object_name = 'journal'
    module_key = 'accounting'

    def get_queryset(self):
        return JournalEntry.objects.filter(company=self.get_company()).select_related('posted_by', 'reversed_by', 'branch', 'reversal_entry')


class JournalCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Create a Manual Multi-Line Journal Entry."""
    template_name = 'accounting/journals/journal_form.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        accounts = Account.objects.filter(company=company, is_active=True).order_by('code')
        form = ManualJournalEntryForm(company=company, initial={'date': timezone.localdate()})
        return render(request, self.template_name, {
            'form': form,
            'accounts': accounts,
            'company': company,
        })

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = ManualJournalEntryForm(request.POST, company=company)
        accounts = Account.objects.filter(company=company, is_active=True).order_by('code')

        if not form.is_valid():
            return render(request, self.template_name, {'form': form, 'accounts': accounts, 'company': company})

        date_val = form.cleaned_data['date']
        narration = form.cleaned_data['narration']
        branch = form.cleaned_data['branch']

        # Parse posted table rows
        account_ids = request.POST.getlist('line_account_id[]')
        debits = request.POST.getlist('line_debit[]')
        credits = request.POST.getlist('line_credit[]')
        descriptions = request.POST.getlist('line_desc[]')

        lines = []
        for i in range(len(account_ids)):
            acct_id = account_ids[i].strip()
            if not acct_id:
                continue

            dr_str = debits[i].strip() if i < len(debits) else '0'
            cr_str = credits[i].strip() if i < len(credits) else '0'
            desc_str = descriptions[i].strip() if i < len(descriptions) else ''

            dr = Decimal(dr_str) if dr_str else Decimal('0.00')
            cr = Decimal(cr_str) if cr_str else Decimal('0.00')

            if dr > 0 or cr > 0:
                lines.append({
                    'account_id': int(acct_id),
                    'debit': dr,
                    'credit': cr,
                    'description': desc_str,
                })

        try:
            entry = JournalPostingService.post_journal(
                company=company,
                source_module='accounting',
                source_ref='MANUAL-ENTRY',
                date_val=date_val,
                lines=lines,
                narration=narration,
                posted_by=request.user,
                branch=branch,
                entry_type=JournalEntryType.MANUAL,
                auto_approve=True,
            )
            messages.success(request, f"Journal Entry #{entry.entry_number} posted successfully (Total: KES {entry.total_amount:,.2f}).")
            return redirect('accounting_journal_detail', pk=entry.pk)
        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, 'message') else e))
            return render(request, self.template_name, {'form': form, 'accounts': accounts, 'company': company})


class JournalReverseView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Reverse a posted Journal Entry."""
    module_key = 'accounting'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        entry = get_object_or_404(JournalEntry, pk=pk, company=company)
        reason = request.POST.get('reason', '').strip()

        try:
            reversal = JournalPostingService.reverse_journal(
                entry=entry,
                reversed_by=request.user,
                reason=reason,
            )
            messages.success(request, f"Journal #{entry.entry_number} has been reversed via Reversal Entry #{reversal.entry_number}.")
            return redirect('accounting_journal_detail', pk=reversal.pk)
        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, 'message') else e))
            return redirect('accounting_journal_detail', pk=entry.pk)


# ─── Financial Reports Views ─────────────────────────────────────────────────

class TrialBalanceView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, TemplateView):
    """Standard IFRS Trial Balance Report."""
    template_name = 'accounting/reports/trial_balance.html'
    module_key = 'accounting'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        if not company:
            return ctx

        today = timezone.localdate()
        as_of_str = self.request.GET.get('as_of_date')
        start_str = self.request.GET.get('start_date')

        try:
            as_of_date = date.fromisoformat(as_of_str) if as_of_str else today
        except ValueError:
            as_of_date = today

        try:
            start_date = date.fromisoformat(start_str) if start_str else None
        except ValueError:
            start_date = None

        tb_data = TrialBalanceSelector.get_trial_balance(
            company=company,
            as_of_date=as_of_date,
            start_date=start_date
        )

        filter_form = TrialBalanceFilterForm(company=company, initial={
            'as_of_date': as_of_date,
            'start_date': start_date,
        })

        ctx.update({
            'tb': tb_data,
            'filter_form': filter_form,
            'as_of_date': as_of_date,
            'start_date': start_date,
            'today': today,
        })
        return ctx


class TrialBalanceExportCSVView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Download Trial Balance in CSV format."""
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        today = timezone.localdate()
        as_of_str = request.GET.get('as_of_date')
        try:
            as_of_date = date.fromisoformat(as_of_str) if as_of_str else today
        except ValueError:
            as_of_date = today

        tb_data = TrialBalanceSelector.get_trial_balance(company=company, as_of_date=as_of_date)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="Trial_Balance_{company.name.replace(" ", "_")}_{as_of_date.isoformat()}.csv"'

        writer = csv.writer(response)
        writer.writerow([f"TRIAL BALANCE - {company.name.upper()}"])
        writer.writerow([f"As of: {as_of_date.strftime('%d/%m/%Y')} | Currency: KES"])
        writer.writerow([])
        writer.writerow(['Account Code', 'Account Name', 'Type', 'Category', 'Normal Balance', 'Period Debits (KES)', 'Period Credits (KES)', 'Closing Debit (KES)', 'Closing Credit (KES)'])

        for r in tb_data['rows']:
            writer.writerow([
                r['account_code'],
                r['account_name'],
                r['account_type_display'],
                r['category'],
                r['normal_balance'].upper(),
                f"{r['period_debits']:.2f}",
                f"{r['period_credits']:.2f}",
                f"{r['closing_debit']:.2f}",
                f"{r['closing_credit']:.2f}",
            ])

        writer.writerow([])
        writer.writerow(['TOTALS', '', '', '', '', '', '', f"{tb_data['total_debits']:.2f}", f"{tb_data['total_credits']:.2f}"])
        writer.writerow(['DIFFERENCE', '', '', '', '', '', '', f"{tb_data['difference']:.2f}", 'BALANCED' if tb_data['is_balanced'] else 'UNBALANCED'])

        return response


class GeneralLedgerReportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, TemplateView):
    """Itemized General Ledger account transaction history."""
    template_name = 'accounting/reports/general_ledger.html'
    module_key = 'accounting'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        if not company:
            return ctx

        account_id = self.request.GET.get('account_id')
        accounts = Account.objects.filter(company=company, is_active=True).order_by('code')

        selected_account = None
        ledger_data = None

        if account_id:
            selected_account = Account.objects.filter(company=company, pk=account_id).first()
            if selected_account:
                ledger_data = GeneralLedgerSelector.get_account_ledger(company, selected_account)

        ctx.update({
            'accounts': accounts,
            'selected_account': selected_account,
            'ledger': ledger_data,
            'today': timezone.localdate(),
        })
        return ctx


class PostingExceptionListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    """List and manage queued / failed asynchronous journal postings."""
    model = PostingQueue
    template_name = 'accounting/posting_exceptions.html'
    context_object_name = 'queue_items'
    paginate_by = 25
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return PostingQueue.objects.none()

        qs = PostingQueue.objects.filter(company=company).order_by('-created_at')
        status_filter = self.request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        if company:
            ctx['failed_count'] = PostingQueue.objects.filter(company=company, status=PostingQueue.STATUS_FAILED).count()
            ctx['pending_count'] = PostingQueue.objects.filter(company=company, status=PostingQueue.STATUS_PENDING).count()
            ctx['processed_count'] = PostingQueue.objects.filter(company=company, status=PostingQueue.STATUS_PROCESSED).count()
        ctx['status_filter'] = self.request.GET.get('status', '')
        return ctx


class PostingExceptionRetryView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Retry a failed or pending queued journal posting."""
    module_key = 'accounting'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        queue_item = get_object_or_404(PostingQueue, pk=pk, company=company)

        # Attempt immediate execution
        from accounting import api
        try:
            queue_item.attempts += 1
            payload = queue_item.payload
            date_raw = payload.get('date') or payload.get('date_val')
            if isinstance(date_raw, str):
                date_val = date.fromisoformat(date_raw)
            else:
                date_val = timezone.localdate()

            entry = JournalPostingService.post_journal(
                company=company,
                source_module=queue_item.source_module,
                source_ref=queue_item.source_ref,
                date_val=date_val,
                lines=payload.get('lines', []),
                narration=payload.get('narration', ''),
                idempotency_key=payload.get('idempotency_key'),
                entry_type=payload.get('entry_type', JournalEntryType.MANUAL),
            )
            queue_item.status = PostingQueue.STATUS_PROCESSED
            queue_item.created_journal_entry = entry
            queue_item.processed_at = timezone.now()
            queue_item.error_message = ''
            queue_item.save()
            messages.success(request, f"Successfully posted Journal #{entry.entry_number} for {queue_item.source_ref}.")
        except Exception as e:
            queue_item.status = PostingQueue.STATUS_FAILED
            queue_item.error_message = str(e)
            queue_item.save()
            messages.error(request, f"Retry failed: {e}")

        return redirect('posting_exceptions')


class PostingExceptionDismissView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Dismiss a failed posting queue item."""
    module_key = 'accounting'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        queue_item = get_object_or_404(PostingQueue, pk=pk, company=company)
        ref = queue_item.source_ref
        queue_item.delete()
        messages.info(request, f"Dismissed queue item {ref}.")
        return redirect('posting_exceptions')


class POSGLMappingView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Configure default General Ledger account mappings for POS operations."""
    template_name = 'accounting/mappings/pos_mapping.html'
    module_key = 'accounting'

    def get_pos_business(self, company):
        from pos.models import Business
        if company and hasattr(company, 'name') and company.name:
            biz = Business.objects.filter(name=company.name).first() or Business.objects.filter(slug=getattr(company, 'slug', '')).first()
            if biz:
                return biz
        return getattr(self.request, 'business', None) or Business.objects.filter(is_active=True).first() or Business.objects.first()

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        business = self.get_pos_business(company)
        if not company and business:
            from core.models.organization import Company
            company, _ = Company.objects.get_or_create(
                slug=business.slug or 'default',
                defaults={
                    'name': business.name,
                    'currency': 'KES',
                    'city': 'Nairobi',
                    'county': 'Nairobi',
                    'is_active': True,
                }
            )
            request.company = company

        from pos.models import POSGLMapping
        mapping = POSGLMapping.get_for_business(business) if business else None
        initial = {}
        if mapping:
            initial = {
                'cash_account_code': mapping.cash_account_code,
                'mpesa_account_code': mapping.mpesa_account_code,
                'card_account_code': mapping.card_account_code,
                'credit_account_code': mapping.credit_account_code,
                'sales_revenue_code': mapping.sales_revenue_code,
                'vat_output_code': mapping.vat_output_code,
                'cogs_account_code': mapping.cogs_account_code,
                'inventory_account_code': mapping.inventory_account_code,
                'cash_variance_code': mapping.cash_variance_code,
            }
        form = POSGLMappingForm(company=company, initial=initial)
        return render(request, self.template_name, {
            'form': form,
            'mapping': mapping,
            'business': business,
            'company': company,
        })

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        business = self.get_pos_business(company)
        if not company and business:
            from core.models.organization import Company
            company, _ = Company.objects.get_or_create(
                slug=business.slug or 'default',
                defaults={
                    'name': business.name,
                    'currency': 'KES',
                    'city': 'Nairobi',
                    'county': 'Nairobi',
                    'is_active': True,
                }
            )
            request.company = company

        from pos.models import POSGLMapping
        mapping = POSGLMapping.get_for_business(business) if business else None
        form = POSGLMappingForm(request.POST, company=company)
        if form.is_valid() and mapping:
            for field, val in form.cleaned_data.items():
                setattr(mapping, field, val)
            mapping.save()
            messages.success(request, "POS General Ledger account mappings saved successfully.")
            return redirect('pos_mapping')
        return render(request, self.template_name, {
            'form': form,
            'mapping': mapping,
            'business': business,
            'company': company,
        })


class HRGLMappingView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    """Configure default General Ledger account mappings for HR & Payroll."""
    template_name = 'accounting/mappings/hr_mapping.html'
    module_key = 'accounting'

    def get_pos_business(self, company):
        from pos.models import Business
        if company and hasattr(company, 'name') and company.name:
            biz = Business.objects.filter(name=company.name).first() or Business.objects.filter(slug=getattr(company, 'slug', '')).first()
            if biz:
                return biz
        return getattr(self.request, 'business', None) or Business.objects.filter(is_active=True).first() or Business.objects.first()

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        business = self.get_pos_business(company)
        if not company and business:
            from core.models.organization import Company
            company, _ = Company.objects.get_or_create(
                slug=business.slug or 'default',
                defaults={
                    'name': business.name,
                    'currency': 'KES',
                    'city': 'Nairobi',
                    'county': 'Nairobi',
                    'is_active': True,
                }
            )
            request.company = company

        from hr.models import HRGLMapping
        mapping = HRGLMapping.get_for_business(business) if business else None
        initial = {}
        if mapping:
            initial = {
                'basic_salaries_expense_code': mapping.basic_salaries_expense_code,
                'employer_nssf_expense_code': mapping.employer_nssf_expense_code,
                'employer_shif_expense_code': mapping.employer_shif_expense_code,
                'employer_housing_levy_expense_code': mapping.employer_housing_levy_expense_code,
                'employer_nita_expense_code': mapping.employer_nita_expense_code,
                'net_salaries_payable_code': mapping.net_salaries_payable_code,
                'paye_payable_code': mapping.paye_payable_code,
                'nssf_payable_code': mapping.nssf_payable_code,
                'shif_payable_code': mapping.shif_payable_code,
                'housing_levy_payable_code': mapping.housing_levy_payable_code,
                'helb_payable_code': mapping.helb_payable_code,
                'staff_advances_asset_code': mapping.staff_advances_asset_code,
            }
        form = HRGLMappingForm(company=company, initial=initial)
        return render(request, self.template_name, {
            'form': form,
            'mapping': mapping,
            'business': business,
            'company': company,
        })

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        business = self.get_pos_business(company)
        if not company and business:
            from core.models.organization import Company
            company, _ = Company.objects.get_or_create(
                slug=business.slug or 'default',
                defaults={
                    'name': business.name,
                    'currency': 'KES',
                    'city': 'Nairobi',
                    'county': 'Nairobi',
                    'is_active': True,
                }
            )
            request.company = company

        from hr.models import HRGLMapping
        mapping = HRGLMapping.get_for_business(business) if business else None
        form = HRGLMappingForm(request.POST, company=company)
        if form.is_valid() and mapping:
            for field, val in form.cleaned_data.items():
                setattr(mapping, field, val)
            mapping.save()
            messages.success(request, "HR & Payroll General Ledger account mappings saved successfully.")
            return redirect('hr_mapping')
        return render(request, self.template_name, {
            'form': form,
            'mapping': mapping,
            'business': business,
            'company': company,
        })


# ─── ACCOUNTS RECEIVABLE (AR) VIEWS ─────────────────────────────────────────

class CustomerListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    model = Customer
    template_name = 'accounting/ar/customer_list.html'
    context_object_name = 'customers'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Customer.objects.none()
        return Customer.objects.filter(company=company).order_by('name')


class CustomerCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/ar/customer_form.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        form = CustomerForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = CustomerForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            Customer.objects.create(
                company=company,
                name=data['name'],
                kra_pin=data['kra_pin'],
                email=data['email'],
                phone=data['phone'],
                credit_limit=data['credit_limit'],
                address=data['address'],
                created_by=request.user
            )
            messages.success(request, f"Customer '{data['name']}' created successfully.")
            return redirect('accounting_customer_list')
        return render(request, self.template_name, {'form': form})


class CustomerInvoiceListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    model = CustomerInvoice
    template_name = 'accounting/ar/invoice_list.html'
    context_object_name = 'invoices'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return CustomerInvoice.objects.none()
        qs = CustomerInvoice.objects.filter(company=company).select_related('customer', 'branch').order_by('-invoice_date', '-id')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = InvoiceStatus.choices
        ctx['selected_status'] = self.request.GET.get('status', '')
        return ctx


class CustomerInvoiceDetailView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    model = CustomerInvoice
    template_name = 'accounting/ar/invoice_detail.html'
    context_object_name = 'invoice'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        return CustomerInvoice.objects.filter(company=company).select_related('customer', 'branch', 'journal_entry').prefetch_related('lines__account', 'payment_allocations__payment')


class CustomerInvoicePostView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    module_key = 'accounting'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        inv = get_object_or_404(CustomerInvoice, pk=pk, company=company)
        try:
            entry = api.post_customer_invoice(inv, user=request.user)
            messages.success(request, f"Invoice #{inv.invoice_number} successfully posted to GL (Journal #{entry.entry_number}).")
        except Exception as e:
            messages.error(request, f"Posting failed: {e}")
        return redirect('accounting_invoice_detail', pk=inv.pk)


class CustomerPaymentListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    model = CustomerPayment
    template_name = 'accounting/ar/payment_list.html'
    context_object_name = 'payments'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return CustomerPayment.objects.none()
        return CustomerPayment.objects.filter(company=company).select_related('customer', 'deposit_account', 'journal_entry').order_by('-payment_date', '-id')


class CustomerPaymentCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/ar/payment_form.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        form = CustomerPaymentForm(company=company)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = CustomerPaymentForm(request.POST, company=company)
        if form.is_valid():
            data = form.cleaned_data
            payment = CustomerPayment.objects.create(
                company=company,
                customer=data['customer'],
                branch=data['branch'],
                receipt_number=data['receipt_number'],
                payment_date=data['payment_date'],
                amount=data['amount'],
                payment_method=data['payment_method'],
                reference=data['reference'],
                deposit_account=data['deposit_account'],
                notes=data['notes'],
                created_by=request.user
            )
            try:
                entry = api.record_customer_payment(payment, user=request.user)
                messages.success(request, f"Payment #{payment.receipt_number} recorded & posted to GL (Journal #{entry.entry_number}).")
                return redirect('accounting_customer_payment_list')
            except Exception as e:
                messages.error(request, f"Payment recorded but GL posting failed: {e}")
                return redirect('accounting_customer_payment_list')
        return render(request, self.template_name, {'form': form})


class ARAgingReportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/reports/ar_aging.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        as_of_raw = request.GET.get('as_of_date')
        as_of = date.fromisoformat(as_of_raw) if as_of_raw else timezone.localdate()
        report = get_ar_aging_report(company, as_of_date=as_of)
        return render(request, self.template_name, {'report': report, 'as_of_date': as_of})


# ─── ACCOUNTS PAYABLE (AP) VIEWS ─────────────────────────────────────────

class VendorListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    model = Vendor
    template_name = 'accounting/ap/vendor_list.html'
    context_object_name = 'vendors'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Vendor.objects.none()
        return Vendor.objects.filter(company=company).order_by('name')


class VendorCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/ap/vendor_form.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        form = VendorForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = VendorForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            Vendor.objects.create(
                company=company,
                name=data['name'],
                kra_pin=data['kra_pin'],
                email=data['email'],
                phone=data['phone'],
                payment_terms_days=data['payment_terms_days'],
                address=data['address'],
                created_by=request.user
            )
            messages.success(request, f"Vendor '{data['name']}' created successfully.")
            return redirect('accounting_vendor_list')
        return render(request, self.template_name, {'form': form})


class VendorBillListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    model = VendorBill
    template_name = 'accounting/ap/bill_list.html'
    context_object_name = 'bills'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return VendorBill.objects.none()
        qs = VendorBill.objects.filter(company=company).select_related('vendor', 'branch').order_by('-bill_date', '-id')
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['status_choices'] = BillStatus.choices
        ctx['selected_status'] = self.request.GET.get('status', '')
        return ctx


class VendorBillDetailView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    model = VendorBill
    template_name = 'accounting/ap/bill_detail.html'
    context_object_name = 'bill'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        return VendorBill.objects.filter(company=company).select_related('vendor', 'branch', 'journal_entry').prefetch_related('lines__account', 'payment_allocations__payment')


class VendorBillPostView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    module_key = 'accounting'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        bill = get_object_or_404(VendorBill, pk=pk, company=company)
        try:
            entry = api.post_vendor_bill(bill, user=request.user)
            messages.success(request, f"Vendor Bill #{bill.bill_number} successfully posted to GL (Journal #{entry.entry_number}).")
        except Exception as e:
            messages.error(request, f"Posting failed: {e}")
        return redirect('accounting_bill_detail', pk=bill.pk)


class VendorPaymentListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    model = VendorPayment
    template_name = 'accounting/ap/payment_list.html'
    context_object_name = 'payments'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return VendorPayment.objects.none()
        return VendorPayment.objects.filter(company=company).select_related('vendor', 'paid_from_account', 'journal_entry').order_by('-payment_date', '-id')


class VendorPaymentCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/ap/payment_form.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        form = VendorPaymentForm(company=company)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = VendorPaymentForm(request.POST, company=company)
        if form.is_valid():
            data = form.cleaned_data
            payment = VendorPayment.objects.create(
                company=company,
                vendor=data['vendor'],
                branch=data['branch'],
                voucher_number=data['voucher_number'],
                payment_date=data['payment_date'],
                amount=data['amount'],
                payment_method=data['payment_method'],
                reference=data['reference'],
                paid_from_account=data['paid_from_account'],
                notes=data['notes'],
                created_by=request.user
            )
            try:
                entry = api.record_vendor_payment(payment, user=request.user)
                messages.success(request, f"Voucher #{payment.voucher_number} recorded & posted to GL (Journal #{entry.entry_number}).")
                return redirect('accounting_vendor_payment_list')
            except Exception as e:
                messages.error(request, f"Voucher recorded but GL posting failed: {e}")
                return redirect('accounting_vendor_payment_list')
        return render(request, self.template_name, {'form': form})


class APAgingReportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/reports/ap_aging.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        as_of_raw = request.GET.get('as_of_date')
        as_of = date.fromisoformat(as_of_raw) if as_of_raw else timezone.localdate()
        report = get_ap_aging_report(company, as_of_date=as_of)
        return render(request, self.template_name, {'report': report, 'as_of_date': as_of})


# ─── BANK & M-PESA RECONCILIATION VIEWS ─────────────────────────────────────

class BankAccountListView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, ListView):
    model = BankAccount
    template_name = 'accounting/banking/account_list.html'
    context_object_name = 'accounts'
    module_key = 'accounting'

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return BankAccount.objects.none()
        return BankAccount.objects.filter(company=company).select_related('gl_account').order_by('name')


class BankAccountCreateView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/banking/account_form.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        form = BankAccountForm(company=company)
        return render(request, self.template_name, {'form': form})

    def post(self, request, *args, **kwargs):
        company = self.get_company()
        form = BankAccountForm(request.POST, company=company)
        if form.is_valid():
            data = form.cleaned_data
            BankAccount.objects.create(
                company=company,
                name=data['name'],
                bank_name=data['bank_name'],
                account_number=data['account_number'],
                gl_account=data['gl_account'],
                created_by=request.user
            )
            messages.success(request, f"Bank Account '{data['name']}' added successfully.")
            return redirect('accounting_bank_account_list')
        return render(request, self.template_name, {'form': form})


class BankAccountDetailView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, DetailView):
    model = BankAccount
    template_name = 'accounting/banking/account_detail.html'
    context_object_name = 'bank_account'
    module_key = 'accounting'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        bank_account = self.object
        ctx['statements'] = bank_account.statements.order_by('-statement_date', '-id')[:10]
        ctx['recon_summary'] = get_bank_reconciliation_summary(bank_account)
        return ctx


class BankStatementImportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/banking/statement_import.html'
    module_key = 'accounting'

    def get(self, request, pk, *args, **kwargs):
        company = self.get_company()
        bank_account = get_object_or_404(BankAccount, pk=pk, company=company)
        form = BankStatementUploadForm()
        return render(request, self.template_name, {'bank_account': bank_account, 'form': form})

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        bank_account = get_object_or_404(BankAccount, pk=pk, company=company)
        form = BankStatementUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            content = csv_file.read().decode('utf-8-sig', errors='replace')
            stmt_type = form.cleaned_data['statement_type']
            try:
                if stmt_type == 'mpesa':
                    stmt = api.parse_mpesa_statement(bank_account, content, user=request.user)
                else:
                    stmt = api.parse_bank_statement(bank_account, content, user=request.user)
                messages.success(request, f"Statement imported successfully: {stmt.lines.count()} transactions parsed.")
                return redirect('accounting_bank_account_detail', pk=bank_account.pk)
            except Exception as e:
                messages.error(request, f"Import failed: {e}")
        return render(request, self.template_name, {'bank_account': bank_account, 'form': form})


class BankReconciliationActionView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    module_key = 'accounting'

    def post(self, request, pk, *args, **kwargs):
        company = self.get_company()
        stmt = get_object_or_404(BankStatement, pk=pk, company=company)
        res = api.auto_reconcile_statement(stmt)
        messages.success(request, f"Auto-reconciliation complete: {res['matched']} matched, {res['unmatched']} unmatched.")
        return redirect('accounting_bank_account_detail', pk=stmt.bank_account.pk)


class BankReconciliationReportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/reports/bank_reconciliation.html'
    module_key = 'accounting'

    def get(self, request, pk, *args, **kwargs):
        company = self.get_company()
        bank_account = get_object_or_404(BankAccount, pk=pk, company=company)
        as_of_raw = request.GET.get('as_of_date')
        as_of = date.fromisoformat(as_of_raw) if as_of_raw else timezone.localdate()
        recon = get_bank_reconciliation_summary(bank_account, as_of_date=as_of)
        return render(request, self.template_name, {'recon': recon, 'bank_account': bank_account, 'as_of_date': as_of})


# ─── KENYAN TAX VIEWS ───────────────────────────────────────────────────────

class VATReturnView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/tax/vat_return.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        today = timezone.localdate()
        start_d = date(today.year, today.month, 1)
        if today.month == 12:
            end_d = date(today.year, 12, 31)
        else:
            end_d = date(today.year, today.month + 1, 1) - timezone.timedelta(days=1)

        start_raw = request.GET.get('start_date')
        end_raw = request.GET.get('end_date')
        if start_raw:
            start_d = date.fromisoformat(start_raw)
        if end_raw:
            end_d = date.fromisoformat(end_raw)

        vat_data = get_vat_return_summary(company, start_date=start_d, end_date=end_d)
        return render(request, self.template_name, {
            'vat': vat_data,
            'start_date': start_d,
            'end_date': end_d,
        })


class VATSalesCSVExportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        start_d = date.fromisoformat(request.GET.get('start_date'))
        end_d = date.fromisoformat(request.GET.get('end_date'))
        content = api.export_itax_vat_sales_csv(company, start_date=start_d, end_date=end_d)
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="KRA_iTax_VAT_Sales_{start_d}_{end_d}.csv"'
        return response


class VATPurchasesCSVExportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        start_d = date.fromisoformat(request.GET.get('start_date'))
        end_d = date.fromisoformat(request.GET.get('end_date'))
        content = api.export_itax_vat_purchases_csv(company, start_date=start_d, end_date=end_d)
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="KRA_iTax_VAT_Purchases_{start_d}_{end_d}.csv"'
        return response


class WHTScheduleView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/tax/wht_schedule.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        today = timezone.localdate()
        start_d = date(today.year, 1, 1)
        end_d = date(today.year, 12, 31)
        start_raw = request.GET.get('start_date')
        end_raw = request.GET.get('end_date')
        wht_type = request.GET.get('wht_type')
        if start_raw:
            start_d = date.fromisoformat(start_raw)
        if end_raw:
            end_d = date.fromisoformat(end_raw)

        wht_data = get_wht_return_summary(company, start_date=start_d, end_date=end_d, wht_type=wht_type)
        return render(request, self.template_name, {
            'wht': wht_data,
            'start_date': start_d,
            'end_date': end_d,
            'wht_type': wht_type or '',
        })


class WHTCSVExportView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        start_d = date.fromisoformat(request.GET.get('start_date'))
        end_d = date.fromisoformat(request.GET.get('end_date'))
        wht_type = request.GET.get('wht_type') or None
        content = api.export_itax_wht_csv(company, start_date=start_d, end_date=end_d, wht_type=wht_type)
        response = HttpResponse(content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="KRA_iTax_WHT_Schedule_{start_d}_{end_d}.csv"'
        return response


# ─── FINANCIAL STATEMENTS VIEWS ─────────────────────────────────────────────

class IncomeStatementView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/reports/income_statement.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        today = timezone.localdate()
        start_d = date(today.year, 1, 1)
        end_d = today

        start_raw = request.GET.get('start_date')
        end_raw = request.GET.get('end_date')
        comp_start_raw = request.GET.get('compare_start_date')
        comp_end_raw = request.GET.get('compare_end_date')

        if start_raw:
            start_d = date.fromisoformat(start_raw)
        if end_raw:
            end_d = date.fromisoformat(end_raw)

        comp_start_d = date.fromisoformat(comp_start_raw) if comp_start_raw else None
        comp_end_d = date.fromisoformat(comp_end_raw) if comp_end_raw else None

        branch_id = request.GET.get('branch')
        branch = Branch.objects.filter(company=company, pk=branch_id).first() if branch_id else None

        report = get_income_statement(
            company=company,
            start_date=start_d,
            end_date=end_d,
            branch=branch,
            compare_start_date=comp_start_d,
            compare_end_date=comp_end_d,
        )

        return render(request, self.template_name, {
            'report': report,
            'start_date': start_d,
            'end_date': end_d,
            'compare_start_date': comp_start_d,
            'compare_end_date': comp_end_d,
            'branch': branch,
            'branches': Branch.objects.filter(company=company, is_active=True),
        })


class BalanceSheetView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/reports/balance_sheet.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        today = timezone.localdate()
        as_of = today

        as_of_raw = request.GET.get('as_of_date')
        comp_as_of_raw = request.GET.get('compare_as_of_date')

        if as_of_raw:
            as_of = date.fromisoformat(as_of_raw)
        comp_as_of = date.fromisoformat(comp_as_of_raw) if comp_as_of_raw else None

        branch_id = request.GET.get('branch')
        branch = Branch.objects.filter(company=company, pk=branch_id).first() if branch_id else None

        report = get_balance_sheet(
            company=company,
            as_of_date=as_of,
            branch=branch,
            compare_as_of_date=comp_as_of,
        )

        return render(request, self.template_name, {
            'report': report,
            'as_of_date': as_of,
            'compare_as_of_date': comp_as_of,
            'branch': branch,
            'branches': Branch.objects.filter(company=company, is_active=True),
        })


class CashFlowStatementView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, View):
    template_name = 'accounting/reports/cash_flow.html'
    module_key = 'accounting'

    def get(self, request, *args, **kwargs):
        company = self.get_company()
        today = timezone.localdate()
        start_d = date(today.year, 1, 1)
        end_d = today

        start_raw = request.GET.get('start_date')
        end_raw = request.GET.get('end_date')

        if start_raw:
            start_d = date.fromisoformat(start_raw)
        if end_raw:
            end_d = date.fromisoformat(end_raw)

        branch_id = request.GET.get('branch')
        branch = Branch.objects.filter(company=company, pk=branch_id).first() if branch_id else None

        report = get_cash_flow_statement(
            company=company,
            start_date=start_d,
            end_date=end_d,
            branch=branch,
        )

        return render(request, self.template_name, {
            'report': report,
            'start_date': start_d,
            'end_date': end_d,
            'branch': branch,
            'branches': Branch.objects.filter(company=company, is_active=True),
        })


