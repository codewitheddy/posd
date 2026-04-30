from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    DepartmentViewSet, EmployeeViewSet, AttendanceViewSet,
    PayrollViewSet, StaffAdvanceViewSet, LeaveViewSet,
    PerformanceViewSet, DisciplinaryViewSet,
    ReportViewSet, DashboardViewSet,
)
from . import web_views

router = DefaultRouter()
router.register(r'departments', DepartmentViewSet, basename='hr-department')
router.register(r'employees', EmployeeViewSet, basename='hr-employee')
router.register(r'attendance', AttendanceViewSet, basename='hr-attendance')
router.register(r'payroll', PayrollViewSet, basename='hr-payroll')
router.register(r'advances', StaffAdvanceViewSet, basename='hr-advance')
router.register(r'leave', LeaveViewSet, basename='hr-leave')
router.register(r'performance', PerformanceViewSet, basename='hr-performance')
router.register(r'disciplinary', DisciplinaryViewSet, basename='hr-disciplinary')
router.register(r'reports', ReportViewSet, basename='hr-report')
router.register(r'dashboard', DashboardViewSet, basename='hr-dashboard')

# Web (template-based) URL patterns
web_urlpatterns = [
    path('', web_views.hr_dashboard, name='hr_dashboard'),
    path('employees/', web_views.employee_list, name='hr_employee_list'),
    path('employees/create/', web_views.employee_create, name='hr_employee_create'),
    path('employees/<int:pk>/edit/', web_views.employee_edit, name='hr_employee_edit'),
    path('attendance/', web_views.attendance_list, name='hr_attendance_list'),
    path('attendance/clock-in/', web_views.attendance_clock_in, name='hr_clock_in'),
    path('attendance/clock-out/', web_views.attendance_clock_out, name='hr_clock_out'),
    path('leave/', web_views.leave_list, name='hr_leave_list'),
    path('leave/create/', web_views.leave_create, name='hr_leave_create'),
    path('leave/<int:pk>/approve/', web_views.leave_approve, name='hr_leave_approve'),
    path('leave/<int:pk>/reject/', web_views.leave_reject, name='hr_leave_reject'),
    path('payroll/', web_views.payroll_list, name='hr_payroll_list'),
    path('payroll/calculate/', web_views.payroll_calculate, name='hr_payroll_calculate'),
    path('payroll/<int:pk>/mark-paid/', web_views.payroll_mark_paid, name='hr_payroll_mark_paid'),
    path('advances/', web_views.advance_list, name='hr_advance_list'),
    path('advances/create/', web_views.advance_create, name='hr_advance_create'),
    path('performance/', web_views.performance_list, name='hr_performance_list'),
    path('disciplinary/', web_views.disciplinary_list, name='hr_disciplinary_list'),
    path('disciplinary/create/', web_views.disciplinary_create, name='hr_disciplinary_create'),
    path('p9/', web_views.p9_list, name='hr_p9_list'),
    path('p9/<int:employee_pk>/download/', web_views.p9_download, name='hr_p9_download'),
    path('payslip/<int:payroll_pk>/download/', web_views.payslip_download, name='hr_payslip_download'),
    path('departments/', web_views.department_list, name='hr_department_list'),
    path('departments/create/', web_views.department_create, name='hr_department_create'),
    path('departments/<int:pk>/edit/', web_views.department_edit, name='hr_department_edit'),
    path('api/departments/quick-create/', web_views.department_quick_create, name='hr_department_quick_create'),
    path('api/users/create/', web_views.user_quick_create, name='hr_user_quick_create'),
]

urlpatterns = web_urlpatterns + [
    path('api/', include(router.urls)),
]
