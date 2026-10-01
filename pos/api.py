"""
POS Module Public Interface (api.py)
Version: 1.1.0

This file defines the ONLY public functions that sibling modules (e.g. HR, Accounting)
are permitted to call. Direct imports of pos.models or pos.views are strictly prohibited.
"""
from typing import Any, Dict, List, Optional
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Q


def get_sales_for_cashier(
    cashier_user_id: int,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Return sales totals and transaction count for a cashier/staff user.
    Used by HR performance metrics and payroll commissions.
    """
    from pos.models import Sale
    qs = Sale.objects.filter(cashier_id=cashier_user_id)
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    total_amount = sum((s.total for s in qs), Decimal('0.00'))
    return {
        'cashier_id': cashier_user_id,
        'transaction_count': qs.count(),
        'total_sales_amount': total_amount,
    }


def get_cashier_performance_metrics(
    business_id: int,
    cashier_user_id: Optional[int],
    period_start: Any,
    period_end: Any,
) -> Dict[str, Any]:
    """
    Return comprehensive performance metrics for a cashier user within a period.
    Used by HR PerformanceService.
    """
    if not cashier_user_id:
        return {
            'total_sales': 0,
            'total_transactions': 0,
            'total_discounts_given': Decimal('0.00'),
            'total_voids': 0,
            'total_refunds': 0,
            'shift_shortages': Decimal('0.00'),
        }

    from pos.models import Sale, SaleReturn, Shift

    sales_qs = Sale.objects.filter(
        business_id=business_id,
        cashier_id=cashier_user_id,
        date__date__gte=period_start,
        date__date__lte=period_end,
    )
    total_sales = sales_qs.count()
    total_transactions = sales_qs.aggregate(
        items=Sum('items__quantity')
    )['items'] or 0
    total_discounts = sales_qs.aggregate(
        disc=Sum('discount_amount')
    )['disc'] or Decimal('0.00')
    total_voids = sales_qs.filter(total=0).count()
    total_refunds = SaleReturn.objects.filter(
        original_sale__cashier_id=cashier_user_id,
        return_date__date__gte=period_start,
        return_date__date__lte=period_end,
    ).count()

    shift_shortages = Shift.objects.filter(
        cashier_id=cashier_user_id,
        start_time__date__gte=period_start,
        start_time__date__lte=period_end,
        cash_difference__lt=0,
    ).aggregate(total=Sum('cash_difference'))['total'] or Decimal('0.00')

    return {
        'total_sales': total_sales,
        'total_transactions': int(total_transactions),
        'total_discounts_given': Decimal(str(total_discounts)),
        'total_voids': total_voids,
        'total_refunds': total_refunds,
        'shift_shortages': Decimal(str(abs(shift_shortages))),
    }


def get_shift_cash_difference_report(
    business_id: int,
    date_from: Optional[Any] = None,
    date_to: Optional[Any] = None,
    cashier_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Return shift cash difference aggregation and raw shifts for HR views.
    """
    from pos.models import Shift

    qs = Shift.objects.filter(
        cashier__business_memberships__business_id=business_id
    ).select_related('cashier')

    if date_from:
        qs = qs.filter(start_time__date__gte=date_from)
    if date_to:
        qs = qs.filter(start_time__date__lte=date_to)
    if cashier_user_id:
        qs = qs.filter(cashier_id=cashier_user_id)

    aggregated = list(qs.values(
        'cashier__id', 'cashier__username', 'cashier__first_name', 'cashier__last_name'
    ).annotate(
        total_cash_difference=Sum('cash_difference'),
        shift_count=Count('id'),
    ).order_by('total_cash_difference'))

    return {
        'aggregated': aggregated,
        'shifts': list(qs.order_by('-start_time')[:100]),
    }


def get_working_hours_settings(business_id: int) -> Dict[str, Any]:
    """
    Return business workday hours and overtime settings for HR AttendanceService.
    """
    from pos.models import BusinessSettings
    try:
        settings = BusinessSettings.objects.filter(business_id=business_id).first()
        if settings:
            return {
                'workday_start_time': settings.workday_start_time,
                'workday_end_time': settings.workday_end_time,
                'late_grace_minutes': settings.late_grace_minutes,
                'overtime_rate_multiplier': settings.overtime_rate_multiplier,
            }
    except Exception:
        pass
    return {
        'workday_start_time': None,
        'workday_end_time': None,
        'late_grace_minutes': 15,
        'overtime_rate_multiplier': Decimal('1.50'),
    }


def get_shift_summary(shift_id: int) -> Optional[Dict[str, Any]]:
    """Return summary data for a POS shift."""
    from pos.models import Shift
    shift = Shift.objects.filter(id=shift_id).first()
    if not shift:
        return None

    return {
        'shift_id': shift.id,
        'cashier_id': shift.cashier_id,
        'start_time': shift.start_time,
        'end_time': shift.end_time,
        'opening_cash': shift.opening_cash,
        'expected_cash': shift.expected_cash,
        'closing_cash': shift.closing_cash,
        'is_closed': shift.end_time is not None,
    }


def get_daily_sales_total(date_val=None, branch_id=None) -> Decimal:
    """Return total sales revenue for a specific date."""
    from pos.models import Sale
    if not date_val:
        date_val = timezone.now().date()

    qs = Sale.objects.filter(date__date=date_val)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)

    return sum((s.total for s in qs), Decimal('0.00'))
