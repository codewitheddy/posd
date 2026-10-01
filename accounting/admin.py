"""
Accounting Django Admin Configuration
"""
from django.contrib import admin
from accounting.models import (
    Account, FiscalYear, FiscalPeriod,
    JournalEntry, JournalEntryLine, PostingQueue
)


class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 0
    fields = ['account_code', 'account_name', 'debit', 'credit', 'currency', 'branch', 'cost_center', 'description']
    readonly_fields = ['account_code', 'account_name', 'debit', 'credit', 'currency']


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'account_type', 'category', 'normal_balance', 'currency', 'is_system', 'is_active', 'is_locked', 'company']
    list_filter = ['account_type', 'category', 'is_system', 'is_active', 'is_locked', 'company']
    search_fields = ['code', 'name', 'system_tag']
    ordering = ['code']


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'is_closed', 'company']
    list_filter = ['is_closed', 'company']
    search_fields = ['name']


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(admin.ModelAdmin):
    list_display = ['name', 'fiscal_year', 'period_number', 'start_date', 'end_date', 'is_closed', 'company']
    list_filter = ['is_closed', 'fiscal_year', 'company']
    search_fields = ['name']
    ordering = ['fiscal_year', 'period_number']


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ['entry_number', 'date', 'entry_type', 'source_module', 'source_ref', 'total_amount', 'status', 'company']
    list_filter = ['entry_type', 'source_module', 'status', 'company', 'date']
    search_fields = ['entry_number', 'source_ref', 'narration', 'idempotency_key']
    inlines = [JournalEntryLineInline]
    readonly_fields = ['entry_number', 'total_amount', 'posted_at', 'reversed_at']


@admin.register(PostingQueue)
class PostingQueueAdmin(admin.ModelAdmin):
    list_display = ['id', 'source_module', 'source_ref', 'status', 'attempts', 'created_at', 'company']
    list_filter = ['status', 'source_module', 'company']
    search_fields = ['source_ref', 'error_message']
