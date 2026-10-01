"""
HR & Payroll Module Manifest
Declares navigation, dashboard cards, default roles, and Kenya statutory health checks.
"""
from core.registry import ModuleManifest, MenuSection, MenuItem, DashboardCard, HealthCheck


def hr_statutory_health_check():
    """Verify Kenya statutory rule sets are seeded and active."""
    from hr.models import StatutoryRuleSet, PAYETaxBand
    rule_sets = StatutoryRuleSet.objects.filter(is_active=True).count()
    bands = PAYETaxBand.objects.count()
    if rule_sets > 0:
        return True, f"{rule_sets} statutory rule set(s) active, {bands} PAYE tax bands configured."
    return False, "No active statutory rule set configured. Run seed_kenya_statutory_data."


def hr_dashboard_card_context(request, company, branch):
    """Context data callback for HR Summary Dashboard Card."""
    from hr.models import Employee, Leave
    from django.utils import timezone
    total_staff = Employee.objects.filter(status='active').count()
    today = timezone.now().date()
    on_leave = Leave.objects.filter(status='approved', start_date__lte=today, end_date__gte=today).count()
    return {
        'total_active_staff': total_staff,
        'staff_on_leave_today': on_leave,
    }


manifest = ModuleManifest(
    key='hr',
    name='Human Resources & Payroll',
    version='2.0.0',
    description='Employee records, Kenya statutory deductions (PAYE, NSSF, SHA, Housing Levy), leave management, and attendance.',
    icon='bi bi-people-fill',
    dependencies=[],
    permission_prefix='hr',
    default_roles={
        'HR Manager': [
            'hr.view_employee',
            'hr.add_employee',
            'hr.change_employee',
            'hr.view_payroll',
            'hr.add_payroll',
            'hr.change_payroll',
            'hr.view_leave',
            'hr.change_leave',
            'hr.view_attendance',
        ],
        'HR Staff': [
            'hr.view_employee',
            'hr.view_attendance',
            'hr.view_leave',
        ],
    },
    menu_sections=[
        MenuSection(
            title='Human Resources',
            order=40,
            items=[
                MenuItem(
                    title='Staff Directory',
                    url_name='hr_employee_list',
                    icon='bi bi-people',
                    permission='hr.view_employee',
                    order=10,
                ),
                MenuItem(
                    title='Attendance',
                    url_name='hr_attendance_list',
                    icon='bi bi-clock-history',
                    order=20,
                ),
                MenuItem(
                    title='Leave Management',
                    url_name='hr_leave_list',
                    icon='bi bi-calendar-check',
                    order=30,
                ),
                MenuItem(
                    title='Payroll & P9',
                    url_name='hr_payroll_list',
                    icon='bi bi-cash-stack',
                    permission='hr.view_payroll',
                    order=40,
                ),
                MenuItem(
                    title='Statutory Returns',
                    url_name='hr_statutory_returns',
                    icon='bi bi-file-earmark-arrow-down',
                    permission='hr.view_payroll',
                    order=45,
                ),
                MenuItem(
                    title='Departments',
                    url_name='hr_department_list',
                    icon='bi bi-diagram-3',
                    order=50,
                ),
                MenuItem(
                    title='Tax Bands & Rules',
                    url_name='hr_statutory_rules',
                    icon='bi bi-sliders',
                    permission='hr.view_payroll',
                    order=60,
                ),
            ],
        ),
    ],
    dashboard_cards=[
        DashboardCard(
            key='hr_staff_summary',
            title='Active Personnel',
            template_name='hr/components/card_staff_summary.html',
            context_callback=hr_dashboard_card_context,
            order=20,
        ),
    ],
    health_checks=[
        HealthCheck(name='Kenya Statutory Payroll Rules', check_callback=hr_statutory_health_check),
    ],
    url_prefix='/hr/',
)
