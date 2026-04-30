"""
Financial Suite: Expenses, Profit, and P&L views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek, Coalesce
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from decimal import Decimal
from datetime import date, timedelta
import csv
import json
import os

from .models import (
    Expense, ExpenseCategory, Sale, SaleItem, Product, Business
)
from .decorators import business_required, business_permission_required
import datetime as _dt

MAX_CUSTOM_FINANCE_RANGE_DAYS = 366


def _can_manage_expenses(request):
    if request.user.is_superuser:
        return True
    membership = getattr(request, 'business_membership', None)
    return bool(membership and membership.role in ('owner', 'admin', 'manager'))


def _can_view_finances(request):
    if request.user.is_superuser:
        return True
    membership = getattr(request, 'business_membership', None)
    return bool(membership and membership.role in ('owner', 'admin', 'manager'))


def _validate_expense_attachment(attachment):
    """Validate optional expense attachment type and size."""
    if not attachment:
        return None

    allowed_exts = {'.jpg', '.jpeg', '.png', '.webp', '.pdf'}
    max_size_bytes = 5 * 1024 * 1024  # 5 MB

    ext = os.path.splitext((attachment.name or '').lower())[1]
    if ext not in allowed_exts:
        return 'Attachment must be a PDF or image file (JPG, JPEG, PNG, WEBP).'

    if attachment.size and attachment.size > max_size_bytes:
        return 'Attachment size must be 5 MB or less.'

    return None


def _to_date(v):
    """Safely convert TruncMonth result to date — handles both datetime and date objects."""
    if isinstance(v, _dt.datetime):
        return v.date()
    return v


# ── helpers ──────────────────────────────────────────────────────────────────

def _date_range(period, custom_from=None, custom_to=None):
    today = timezone.now().date()
    if period == 'today':
        return today, today
    elif period == 'week':
        return today - timedelta(days=6), today
    elif period == 'month':
        return today.replace(day=1), today
    elif period == 'quarter':
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=q_start_month, day=1), today
    elif period == 'year':
        return today.replace(month=1, day=1), today
    elif period == 'custom' and custom_from and custom_to:
        return custom_from, custom_to
    return today.replace(month=1, day=1), today  # default: year


def _resolve_finance_period(period, custom_from, custom_to, fallback='month'):
    """Validate custom finance ranges and return (date_from, date_to, normalized_period, error)."""
    if period != 'custom':
        d_from, d_to = _date_range(period)
        return d_from, d_to, period, None

    if not custom_from or not custom_to:
        d_from, d_to = _date_range(fallback)
        return d_from, d_to, fallback, 'Custom range requires both start and end dates.'

    if custom_from > custom_to:
        d_from, d_to = _date_range(fallback)
        return d_from, d_to, fallback, 'Custom start date cannot be after end date.'

    span = (custom_to - custom_from).days + 1
    if span > MAX_CUSTOM_FINANCE_RANGE_DAYS:
        d_from, d_to = _date_range(fallback)
        return d_from, d_to, fallback, f'Custom range cannot exceed {MAX_CUSTOM_FINANCE_RANGE_DAYS} days.'

    return custom_from, custom_to, 'custom', None


def _ensure_expense_categories(business):
    """Create predefined categories for a business if they don't exist."""
    for name in ExpenseCategory.PREDEFINED:
        ExpenseCategory.objects.get_or_create(
            business=business, name=name,
            defaults={'is_predefined': True}
        )


def _sales_stats(business, date_from, date_to):
    qs = Sale.objects.filter(
        business=business,
        date__date__gte=date_from,
        date__date__lte=date_to,
    )
    revenue = qs.aggregate(v=Sum('total'))['v'] or Decimal('0')
    # Use snapshotted cost_price_at_sale when available, fall back to current product cost for old records
    cogs = SaleItem.objects.filter(
        business=business,
        sale__date__date__gte=date_from,
        sale__date__date__lte=date_to,
    ).annotate(
        effective_cost=Coalesce(F('cost_price_at_sale'), F('product__cost_price')),
        item_cogs=ExpressionWrapper(
            F('quantity') * Coalesce(F('cost_price_at_sale'), F('product__cost_price')),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    ).aggregate(v=Sum('item_cogs'))['v'] or Decimal('0')
    gross_profit = revenue - cogs
    return revenue, cogs, gross_profit


def _expense_total(business, date_from, date_to):
    return Expense.objects.filter(
        business=business,
        expense_date__gte=date_from,
        expense_date__lte=date_to,
    ).aggregate(v=Sum('amount'))['v'] or Decimal('0')


# ── Expense List ──────────────────────────────────────────────────────────────

@business_required
@business_permission_required('view')
def expense_list(request, slug=None):
    if not _can_view_finances(request):
        messages.error(request, 'You do not have permission to view financial reports in this business.')
        return redirect('dashboard', slug=request.business.slug)

    _ensure_expense_categories(request.business)
    today = timezone.now().date()

    # filters
    requested_period = request.GET.get('period', 'month')
    cat_id = request.GET.get('category', '')
    pm = request.GET.get('payment_method', '')
    custom_from = parse_date(request.GET.get('date_from', '')) or None
    custom_to = parse_date(request.GET.get('date_to', '')) or None
    date_from, date_to, resolved_period, period_error = _resolve_finance_period(requested_period, custom_from, custom_to)
    show_custom_picker = requested_period == 'custom'
    period = 'custom' if show_custom_picker else resolved_period
    if period_error:
        messages.error(request, period_error)

    qs = Expense.objects.filter(
        business=request.business,
        expense_date__gte=date_from,
        expense_date__lte=date_to,
    ).select_related('category', 'recorded_by')

    if cat_id:
        qs = qs.filter(category_id=cat_id)
    if pm:
        qs = qs.filter(payment_method=pm)

    # summary cards
    total = qs.aggregate(v=Sum('amount'))['v'] or Decimal('0')
    today_total = Expense.objects.filter(business=request.business, expense_date=today).aggregate(v=Sum('amount'))['v'] or Decimal('0')
    week_total = Expense.objects.filter(business=request.business, expense_date__gte=today - timedelta(days=6)).aggregate(v=Sum('amount'))['v'] or Decimal('0')
    month_total = Expense.objects.filter(business=request.business, expense_date__gte=today.replace(day=1)).aggregate(v=Sum('amount'))['v'] or Decimal('0')

    # by category breakdown
    by_cat = qs.values('category__name').annotate(total=Sum('amount')).order_by('-total')

    # by payment method breakdown
    by_pm = qs.values('payment_method').annotate(total=Sum('amount')).order_by('-total')

    # daily trend (last 30 days within filtered period)
    trend_qs = Expense.objects.filter(
        business=request.business,
        expense_date__gte=date_from,
        expense_date__lte=date_to,
    )
    daily_trend = trend_qs.annotate(day=TruncDay('expense_date')).values('day').annotate(
        total=Sum('amount')
    ).order_by('day')

    chart_labels = json.dumps([str(d['day']) for d in daily_trend])
    chart_values = json.dumps([float(d['total'] or 0) for d in daily_trend])
    pie_labels = json.dumps([c['category__name'] or 'Uncategorized' for c in by_cat])
    pie_values = json.dumps([float(c['total'] or 0) for c in by_cat])
    pm_labels = json.dumps([dict(Expense.PAYMENT_CHOICES).get(p['payment_method'], p['payment_method']) for p in by_pm])
    pm_values = json.dumps([float(p['total'] or 0) for p in by_pm])

    categories = ExpenseCategory.objects.filter(
        Q(business=request.business) | Q(business__isnull=True)
    )

    context = {
        'expenses': qs.order_by('-expense_date', '-created_at')[:200],
        'categories': categories,
        'by_cat': by_cat,
        'by_pm': by_pm,
        'total': total,
        'today_total': today_total,
        'week_total': week_total,
        'month_total': month_total,
        'period': period,
        'resolved_period': resolved_period,
        'periods': ['today', 'week', 'month', 'quarter', 'year', 'custom'],
        'cat_id': cat_id,
        'pm': pm,
        'date_from': date_from,
        'date_to': date_to,
        'date_from_input': custom_from,
        'date_to_input': custom_to,
        'show_custom_picker': show_custom_picker,
        'payment_choices': Expense.PAYMENT_CHOICES,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'pie_labels': pie_labels,
        'pie_values': pie_values,
        'pm_labels': pm_labels,
        'pm_values': pm_values,
    }
    return render(request, 'pos/expense_list.html', context)


# ── Expense Create ────────────────────────────────────────────────────────────

@business_required
@business_permission_required('create')
def expense_create(request, slug=None):
    if not _can_manage_expenses(request):
        messages.error(request, 'You do not have permission to manage expenses in this business.')
        return redirect('expense_list', slug=request.business.slug)

    _ensure_expense_categories(request.business)
    categories = ExpenseCategory.objects.filter(
        Q(business=request.business) | Q(business__isnull=True)
    )

    if request.method == 'POST':
        cat_id = request.POST.get('category')
        description = request.POST.get('description', '').strip()
        amount_str = request.POST.get('amount', '0')
        expense_date_raw = request.POST.get('expense_date', '').strip()
        payment_method = request.POST.get('payment_method', 'cash')
        reference_number = request.POST.get('reference_number', '').strip()
        notes = request.POST.get('notes', '').strip()
        attachment = request.FILES.get('attachment')

        attachment_error = _validate_expense_attachment(attachment)
        if attachment_error:
            messages.error(request, attachment_error)
            return render(request, 'pos/expense_form.html', {
                'categories': categories,
                'payment_choices': Expense.PAYMENT_CHOICES,
                'today': timezone.now().date(),
            })

        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValueError
        except Exception:
            messages.error(request, 'Enter a valid positive amount.')
            return render(request, 'pos/expense_form.html', {
                'categories': categories,
                'payment_choices': Expense.PAYMENT_CHOICES,
                'today': timezone.now().date(),
            })

        expense_date = parse_date(expense_date_raw) if expense_date_raw else timezone.now().date()
        if not expense_date:
            messages.error(request, 'Enter a valid expense date.')
            return render(request, 'pos/expense_form.html', {
                'categories': categories,
                'payment_choices': Expense.PAYMENT_CHOICES,
                'today': timezone.now().date(),
            })

        payment_codes = {code for code, _label in Expense.PAYMENT_CHOICES}
        if payment_method not in payment_codes:
            messages.error(request, 'Invalid payment method.')
            return render(request, 'pos/expense_form.html', {
                'categories': categories,
                'payment_choices': Expense.PAYMENT_CHOICES,
                'today': timezone.now().date(),
            })

        try:
            category = categories.get(pk=cat_id)
        except ExpenseCategory.DoesNotExist:
            messages.error(request, 'Invalid category.')
            return render(request, 'pos/expense_form.html', {
                'categories': categories,
                'payment_choices': Expense.PAYMENT_CHOICES,
                'today': timezone.now().date(),
            })

        expense = Expense(
            business=request.business,
            category=category,
            description=description,
            amount=amount,
            expense_date=expense_date,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            recorded_by=request.user,
        )
        if attachment:
            expense.attachment = attachment
        expense.full_clean()
        expense.save()
        messages.success(request, f'Expense {expense.expense_number} recorded.')
        return redirect('expense_list', slug=request.business.slug)

    return render(request, 'pos/expense_form.html', {
        'categories': categories,
        'payment_choices': Expense.PAYMENT_CHOICES,
        'today': timezone.now().date(),
    })


# ── Expense Edit ──────────────────────────────────────────────────────────────

@business_required
@business_permission_required('edit')
def expense_edit(request, pk, slug=None):
    if not _can_manage_expenses(request):
        messages.error(request, 'You do not have permission to manage expenses in this business.')
        return redirect('expense_list', slug=request.business.slug)

    expense = get_object_or_404(Expense, pk=pk, business=request.business)
    categories = ExpenseCategory.objects.filter(
        Q(business=request.business) | Q(business__isnull=True)
    )

    if request.method == 'POST':
        try:
            expense.category = categories.get(pk=request.POST.get('category'))
            expense.description = request.POST.get('description', '').strip()
            expense.amount = Decimal(request.POST.get('amount', '0').strip())
            if expense.amount <= 0:
                raise ValueError('Enter a valid positive amount.')

            expense_date_raw = request.POST.get('expense_date', '').strip()
            if expense_date_raw:
                parsed_date = parse_date(expense_date_raw)
                if not parsed_date:
                    raise ValueError('Enter a valid expense date.')
                expense.expense_date = parsed_date

            expense.payment_method = request.POST.get('payment_method', 'cash')
            payment_codes = {code for code, _label in Expense.PAYMENT_CHOICES}
            if expense.payment_method not in payment_codes:
                raise ValueError('Invalid payment method.')

            expense.reference_number = request.POST.get('reference_number', '').strip()
            expense.notes = request.POST.get('notes', '').strip()
            attachment = request.FILES.get('attachment')
            attachment_error = _validate_expense_attachment(attachment)
            if attachment_error:
                raise ValueError(attachment_error)
            if attachment:
                expense.attachment = attachment
            expense.full_clean()
            expense.save()
            messages.success(request, 'Expense updated.')
            return redirect('expense_list', slug=request.business.slug)
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return render(request, 'pos/expense_form.html', {
        'expense': expense,
        'categories': categories,
        'payment_choices': Expense.PAYMENT_CHOICES,
        'today': timezone.now().date(),
    })


# ── Expense Delete ────────────────────────────────────────────────────────────

@business_required
@business_permission_required('delete')
def expense_delete(request, pk, slug=None):
    if not _can_manage_expenses(request):
        messages.error(request, 'You do not have permission to manage expenses in this business.')
        return redirect('expense_list', slug=request.business.slug)

    expense = get_object_or_404(Expense, pk=pk, business=request.business)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted.')
        return redirect('expense_list', slug=request.business.slug)
    return render(request, 'pos/expense_confirm_delete.html', {'expense': expense})


# ── Expense CSV Export ────────────────────────────────────────────────────────

@business_required
@business_permission_required('view')
def expense_export_csv(request, slug=None):
    if not _can_view_finances(request):
        messages.error(request, 'You do not have permission to view financial reports in this business.')
        return redirect('dashboard', slug=request.business.slug)

    period = request.GET.get('period', 'month')
    cat_id = request.GET.get('category', '')
    pm = request.GET.get('payment_method', '')
    custom_from = parse_date(request.GET.get('date_from', '')) or None
    custom_to = parse_date(request.GET.get('date_to', '')) or None
    date_from, date_to, period, period_error = _resolve_finance_period(period, custom_from, custom_to)
    if period_error:
        messages.error(request, period_error)
        return redirect('expense_list', slug=request.business.slug)
    qs = Expense.objects.filter(
        business=request.business,
        expense_date__gte=date_from,
        expense_date__lte=date_to,
    ).select_related('category', 'recorded_by').order_by('-expense_date')

    if cat_id:
        qs = qs.filter(category_id=cat_id)
    if pm:
        qs = qs.filter(payment_method=pm)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="expenses_{date_from}_{date_to}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Expense #', 'Date', 'Category', 'Description', 'Amount (KES)', 'Payment Method', 'Reference', 'Recorded By', 'Notes'])
    for e in qs:
        writer.writerow([
            e.expense_number, e.expense_date, e.category.name,
            e.description, e.amount, e.get_payment_method_display(),
            e.reference_number, e.recorded_by.get_full_name() or e.recorded_by.username,
            e.notes,
        ])
    return response


# ── Profit Dashboard ──────────────────────────────────────────────────────────

@business_required
@business_permission_required('view')
def profit_dashboard(request, slug=None):
    if not _can_view_finances(request):
        messages.error(request, 'You do not have permission to view financial reports in this business.')
        return redirect('dashboard', slug=request.business.slug)

    today = timezone.now().date()
    period = request.GET.get('period', 'month')
    date_from, date_to = _date_range(period)

    revenue, cogs, gross_profit = _sales_stats(request.business, date_from, date_to)
    expenses = _expense_total(request.business, date_from, date_to)
    net_profit = gross_profit - expenses
    margin = (net_profit / revenue * 100) if revenue else Decimal('0')

    # Quick period cards
    def quick(d_from, d_to):
        r, c, g = _sales_stats(request.business, d_from, d_to)
        e = _expense_total(request.business, d_from, d_to)
        return {'revenue': r, 'cogs': c, 'gross': g, 'expenses': e, 'net': g - e}

    cards = {
        'today': quick(today, today),
        'week': quick(today - timedelta(days=6), today),
        'month': quick(today.replace(day=1), today),
        'year': quick(today.replace(month=1, day=1), today),
    }

    # Product-level profit (top 20)
    product_profit = SaleItem.objects.filter(
        business=request.business,
        sale__date__date__gte=date_from,
        sale__date__date__lte=date_to,
    ).values(
        'product__name', 'product__category__name'
    ).annotate(
        units=Sum('quantity'),
        revenue=Sum('total_price'),
        cogs=Sum(ExpressionWrapper(
            F('quantity') * Coalesce(F('cost_price_at_sale'), F('product__cost_price')),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )),
    ).annotate(
        profit=ExpressionWrapper(
            F('revenue') - F('cogs'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    ).order_by('-profit')[:20]

    # Daily trend for chart (last 30 days)
    trend_from = today - timedelta(days=29)
    daily = SaleItem.objects.filter(
        business=request.business,
        sale__date__date__gte=trend_from,
    ).annotate(day=TruncDay('sale__date')).values('day').annotate(
        rev=Sum('total_price'),
        cogs=Sum(ExpressionWrapper(
            F('quantity') * Coalesce(F('cost_price_at_sale'), F('product__cost_price')),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )),
    ).order_by('day')

    chart_labels = [str(d['day'].date()) for d in daily]
    chart_revenue = [float(d['rev'] or 0) for d in daily]
    chart_profit = [float((d['rev'] or 0) - (d['cogs'] or 0)) for d in daily]

    context = {
        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'revenue': revenue,
        'cogs': cogs,
        'gross_profit': gross_profit,
        'expenses': expenses,
        'net_profit': net_profit,
        'margin': margin,
        'cards': cards,
        'product_profit': product_profit,
        'chart_labels': json.dumps(chart_labels),
        'chart_revenue': json.dumps(chart_revenue),
        'chart_profit': json.dumps(chart_profit),
    }
    return render(request, 'pos/profit_dashboard.html', context)


# ── P&L Statement ─────────────────────────────────────────────────────────────

@business_required
@business_permission_required('view')
def pl_statement(request, slug=None):
    if not _can_view_finances(request):
        messages.error(request, 'You do not have permission to view financial reports in this business.')
        return redirect('dashboard', slug=request.business.slug)

    today = timezone.now().date()
    requested_period = request.GET.get('period', 'month')
    custom_from = parse_date(request.GET.get('date_from', '')) or None
    custom_to = parse_date(request.GET.get('date_to', '')) or None
    date_from, date_to, resolved_period, period_error = _resolve_finance_period(requested_period, custom_from, custom_to)
    show_custom_picker = requested_period == 'custom'
    period = 'custom' if show_custom_picker else resolved_period
    if period_error:
        messages.error(request, period_error)
        if request.GET.get('export') == 'csv':
            return redirect('pl_statement', slug=request.business.slug)

    revenue, cogs, gross_profit = _sales_stats(request.business, date_from, date_to)

    # Expenses by category
    expense_by_cat = Expense.objects.filter(
        business=request.business,
        expense_date__gte=date_from,
        expense_date__lte=date_to,
    ).values('category__name').annotate(total=Sum('amount')).order_by('-total')

    total_expenses = sum(e['total'] for e in expense_by_cat) or Decimal('0')
    net_profit = gross_profit - total_expenses
    gross_margin = (gross_profit / revenue * 100) if revenue else Decimal('0')
    net_margin = (net_profit / revenue * 100) if revenue else Decimal('0')

    # Monthly trend for chart (last 12 months)
    trend_from = (today.replace(day=1) - timedelta(days=335)).replace(day=1)
    monthly_sales = SaleItem.objects.filter(
        business=request.business,
        sale__date__date__gte=trend_from,
    ).annotate(month=TruncMonth('sale__date')).values('month').annotate(
        rev=Sum('total_price'),
        cogs=Sum(ExpressionWrapper(
            F('quantity') * Coalesce(F('cost_price_at_sale'), F('product__cost_price')),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )),
    ).order_by('month')

    monthly_expenses = Expense.objects.filter(
        business=request.business,
        expense_date__gte=trend_from,
        expense_date__lte=today,
    ).annotate(month=TruncMonth('expense_date')).values('month').annotate(
        total=Sum('amount')
    ).order_by('month')

    sales_map = {
        _to_date(row['month']).replace(day=1): {
            'rev': float(row['rev'] or 0),
            'cogs': float(row['cogs'] or 0),
        }
        for row in monthly_sales
    }
    exp_map = {_to_date(e['month']).replace(day=1): float(e['total'] or 0) for e in monthly_expenses}

    chart_labels, chart_rev, chart_profit, chart_exp = [], [], [], []
    month_cursor = trend_from.replace(day=1)
    month_end = today.replace(day=1)
    while month_cursor <= month_end:
        sales = sales_map.get(month_cursor, {'rev': 0.0, 'cogs': 0.0})
        r = float(sales['rev'])
        c = float(sales['cogs'])
        e = float(exp_map.get(month_cursor, 0))
        chart_labels.append(month_cursor.strftime('%b %Y'))
        chart_rev.append(r)
        chart_profit.append(round(r - c - e, 2))
        chart_exp.append(e)

        if month_cursor.month == 12:
            month_cursor = month_cursor.replace(year=month_cursor.year + 1, month=1)
        else:
            month_cursor = month_cursor.replace(month=month_cursor.month + 1)

    # Expense pie
    pie_labels = [e['category__name'] for e in expense_by_cat]
    pie_values = [float(e['total']) for e in expense_by_cat]

    # CSV export
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="pl_{date_from}_{date_to}.csv"'
        w = csv.writer(response)
        w.writerow([f'P&L Statement — {request.business.name}'])
        w.writerow([f'Period: {date_from} to {date_to}'])
        w.writerow([])
        w.writerow(['Item', 'Amount (KES)'])
        w.writerow(['Total Revenue', revenue])
        w.writerow(['Cost of Goods Sold', cogs])
        w.writerow(['Gross Profit', gross_profit])
        w.writerow([])
        w.writerow(['EXPENSES'])
        for e in expense_by_cat:
            w.writerow([e['category__name'], e['total']])
        w.writerow(['Total Expenses', total_expenses])
        w.writerow([])
        w.writerow(['Net Profit', net_profit])
        return response

    context = {
        'period': period,
        'resolved_period': resolved_period,
        'date_from': date_from,
        'date_to': date_to,
        'date_from_input': custom_from,
        'date_to_input': custom_to,
        'show_custom_picker': show_custom_picker,
        'revenue': revenue,
        'cogs': cogs,
        'gross_profit': gross_profit,
        'expense_by_cat': expense_by_cat,
        'total_expenses': total_expenses,
        'net_profit': net_profit,
        'gross_margin': gross_margin,
        'net_margin': net_margin,
        'chart_labels': json.dumps(chart_labels),
        'chart_rev': json.dumps(chart_rev),
        'chart_profit': json.dumps(chart_profit),
        'chart_exp': json.dumps(chart_exp),
        'pie_labels': json.dumps(pie_labels),
        'pie_values': json.dumps(pie_values),
    }
    return render(request, 'pos/pl_statement.html', context)
