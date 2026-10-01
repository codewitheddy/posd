"""
HR Module Public Interface (api.py)
Version: 1.0.0

This file defines the ONLY public functions that sibling modules (e.g. POS, Accounting)
are permitted to call. Direct imports of hr.models or hr.views are strictly prohibited.
"""
from typing import Any, Dict, List, Optional
from django.utils import timezone


def get_employee_by_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Return employee details associated with a Django auth User ID."""
    from hr.models import Employee
    emp = Employee.objects.filter(user_account_id=user_id).first()
    if not emp:
        return None

    return {
        'employee_id': emp.id,
        'user_id': emp.user_account_id,
        'staff_code': emp.staff_code,
        'first_name': emp.first_name,
        'last_name': emp.last_name,
        'full_name': emp.get_full_name(),
        'department': emp.department.name if emp.department else None,
        'status': emp.status,
        'kra_pin': emp.kra_pin,
        'is_active': emp.status == 'active',
    }


def is_user_on_leave(user_id: int, date_val=None) -> bool:
    """Check if the user is on approved leave on the given date."""
    from hr.models import Leave
    if not date_val:
        date_val = timezone.now().date()

    return Leave.objects.filter(
        employee__user_account_id=user_id,
        status='approved',
        start_date__lte=date_val,
        end_date__gte=date_val,
    ).exists()


def get_active_staff_count() -> int:
    """Return total count of active employees."""
    from hr.models import Employee
    return Employee.objects.filter(status='active').count()
