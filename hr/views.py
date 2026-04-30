from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.utils import timezone

from pos.models import Business, BusinessMembership, ActivityLog
from .models import (
    Department, Employee, Attendance, Payroll,
    StaffAdvance, Leave, PerformanceRecord, DisciplinaryRecord
)
from .serializers import (
    DepartmentSerializer, EmployeeSerializer, AttendanceSerializer,
    PayrollSerializer, StaffAdvanceSerializer, LeaveSerializer,
    PerformanceRecordSerializer, DisciplinaryRecordSerializer
)
from .permissions import IsHRAdmin, IsHRManagerOrAdmin, IsOwnEmployeeOrAdmin
from .services import AttendanceService, PayrollService, PerformanceService


class HRPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


def _get_business(request):
    slug = request.resolver_match.kwargs.get('slug')
    if not slug:
        return None
    return get_object_or_404(Business, slug=slug)


def _log(user, action_type, description, model_name, object_id, business):
    try:
        ActivityLog.log_activity(
            user=user,
            action_type=action_type,
            description=description,
            model_name=model_name,
            object_id=object_id,
            business=business,
            operation_type=action_type,
            entity_type=model_name,
            entity_id=str(object_id) if object_id else '',
        )
    except Exception:
        pass


class DepartmentViewSet(viewsets.ModelViewSet):
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, IsHRAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return Department.objects.none()
        return Department.objects.filter(business=business).select_related('manager__user_account')

    def perform_create(self, serializer):
        instance = serializer.save()
        _log(self.request.user, 'create', f'Created department {instance.name}', 'Department', instance.pk, instance.business)

    def perform_update(self, serializer):
        instance = serializer.save()
        _log(self.request.user, 'update', f'Updated department {instance.name}', 'Department', instance.pk, instance.business)

    def perform_destroy(self, instance):
        _log(self.request.user, 'delete', f'Deleted department {instance.name}', 'Department', instance.pk, instance.business)
        instance.delete()


class EmployeeViewSet(viewsets.ModelViewSet):
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, IsOwnEmployeeOrAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return Employee.objects.none()
        qs = Employee.objects.filter(business=business).select_related('user_account', 'branch', 'department')
        membership = BusinessMembership.objects.filter(
            user=self.request.user, business=business, is_active=True
        ).first()
        if membership and membership.role in ('cashier', 'sales'):
            qs = qs.filter(user_account=self.request.user)
        status_filter = self.request.query_params.get('status')
        dept_filter = self.request.query_params.get('department')
        branch_filter = self.request.query_params.get('branch')
        if status_filter:
            qs = qs.filter(status=status_filter)
        if dept_filter:
            qs = qs.filter(department_id=dept_filter)
        if branch_filter:
            qs = qs.filter(branch_id=branch_filter)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        _log(self.request.user, 'create', f'Created employee {instance}', 'Employee', instance.pk, instance.business)

    def perform_update(self, serializer):
        instance = serializer.save()
        _log(self.request.user, 'update', f'Updated employee {instance}', 'Employee', instance.pk, instance.business)

    def perform_destroy(self, instance):
        _log(self.request.user, 'delete', f'Deleted employee {instance}', 'Employee', instance.pk, instance.business)
        instance.delete()


class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, IsOwnEmployeeOrAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return Attendance.objects.none()
        qs = Attendance.objects.filter(employee__business=business).select_related('employee__user_account')
        membership = BusinessMembership.objects.filter(
            user=self.request.user, business=business, is_active=True
        ).first()
        if membership and membership.role in ('cashier', 'sales'):
            qs = qs.filter(employee__user_account=self.request.user)
        emp = self.request.query_params.get('employee')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        att_status = self.request.query_params.get('status')
        if emp:
            qs = qs.filter(employee_id=emp)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if att_status:
            qs = qs.filter(status=att_status)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'create', f'Created attendance for {instance.employee}', 'Attendance', instance.pk, business)

    def perform_update(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'update', f'Updated attendance for {instance.employee}', 'Attendance', instance.pk, business)

    @action(detail=False, methods=['post'], url_path='clock-in')
    def clock_in(self, request, slug=None):
        business = _get_business(request)
        try:
            employee = Employee.objects.get(user_account=request.user, business=business)
        except Employee.DoesNotExist:
            return Response({'detail': 'No employee profile found.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            attendance = AttendanceService.clock_in(employee)
        except ValidationError as e:
            return Response({'detail': str(e.message)}, status=status.HTTP_400_BAD_REQUEST)
        _log(request.user, 'create', f'Clock in: {employee}', 'Attendance', attendance.pk, business)
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='clock-out')
    def clock_out(self, request, slug=None):
        business = _get_business(request)
        try:
            employee = Employee.objects.get(user_account=request.user, business=business)
        except Employee.DoesNotExist:
            return Response({'detail': 'No employee profile found.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            attendance = AttendanceService.clock_out(employee)
        except ValidationError as e:
            return Response({'detail': str(e.message)}, status=status.HTTP_400_BAD_REQUEST)
        _log(request.user, 'update', f'Clock out: {employee}', 'Attendance', attendance.pk, business)
        return Response(AttendanceSerializer(attendance).data)


class PayrollViewSet(viewsets.ModelViewSet):
    serializer_class = PayrollSerializer
    permission_classes = [IsAuthenticated, IsHRManagerOrAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return Payroll.objects.none()
        qs = Payroll.objects.filter(employee__business=business).select_related('employee__user_account')
        emp = self.request.query_params.get('employee')
        pay_status = self.request.query_params.get('status')
        period = self.request.query_params.get('period_start')
        if emp:
            qs = qs.filter(employee_id=emp)
        if pay_status:
            qs = qs.filter(status=pay_status)
        if period:
            qs = qs.filter(period_start=period)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'create', f'Created payroll for {instance.employee}', 'Payroll', instance.pk, business)

    def perform_update(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'update', f'Updated payroll for {instance.employee}', 'Payroll', instance.pk, business)

    @action(detail=False, methods=['post'], url_path='calculate')
    def calculate(self, request, slug=None):
        business = _get_business(request)
        period_start = request.data.get('period_start')
        period_end = request.data.get('period_end')
        if not period_start or not period_end:
            return Response({'detail': 'period_start and period_end are required.'}, status=status.HTTP_400_BAD_REQUEST)
        from datetime import date
        try:
            ps = date.fromisoformat(period_start)
            pe = date.fromisoformat(period_end)
        except ValueError:
            return Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        payrolls = PayrollService.calculate_period(business, ps, pe)
        _log(request.user, 'create', f'Calculated payroll for {ps} to {pe}', 'Payroll', None, business)
        return Response(PayrollSerializer(payrolls, many=True).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, slug=None, pk=None):
        business = _get_business(request)
        payroll = get_object_or_404(Payroll, pk=pk, employee__business=business)
        try:
            payroll = PayrollService.mark_paid(payroll)
        except ValidationError as e:
            return Response({'detail': str(e.message)}, status=status.HTTP_400_BAD_REQUEST)
        _log(request.user, 'update', f'Marked payroll paid for {payroll.employee}', 'Payroll', payroll.pk, business)
        return Response(PayrollSerializer(payroll).data)


class StaffAdvanceViewSet(viewsets.ModelViewSet):
    serializer_class = StaffAdvanceSerializer
    permission_classes = [IsAuthenticated, IsHRAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return StaffAdvance.objects.none()
        return StaffAdvance.objects.filter(employee__business=business).select_related('employee__user_account')

    def perform_create(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'create', f'Created advance for {instance.employee}', 'StaffAdvance', instance.pk, business)

    def perform_update(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'update', f'Updated advance for {instance.employee}', 'StaffAdvance', instance.pk, business)


class LeaveViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveSerializer
    permission_classes = [IsAuthenticated, IsOwnEmployeeOrAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return Leave.objects.none()
        qs = Leave.objects.filter(employee__business=business).select_related(
            'employee__user_account', 'approved_by__user_account'
        )
        membership = BusinessMembership.objects.filter(
            user=self.request.user, business=business, is_active=True
        ).first()
        if membership and membership.role in ('cashier', 'sales'):
            qs = qs.filter(employee__user_account=self.request.user)
        emp = self.request.query_params.get('employee')
        leave_type = self.request.query_params.get('leave_type')
        leave_status = self.request.query_params.get('status')
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if emp:
            qs = qs.filter(employee_id=emp)
        if leave_type:
            qs = qs.filter(leave_type=leave_type)
        if leave_status:
            qs = qs.filter(status=leave_status)
        if date_from:
            qs = qs.filter(start_date__gte=date_from)
        if date_to:
            qs = qs.filter(end_date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'create', f'Leave request by {instance.employee}', 'Leave', instance.pk, business)

    @action(detail=True, methods=['post'], url_path='approve',
            permission_classes=[IsAuthenticated, IsHRManagerOrAdmin])
    def approve(self, request, slug=None, pk=None):
        business = _get_business(request)
        leave = get_object_or_404(Leave, pk=pk, employee__business=business)
        if leave.status != 'pending':
            return Response({'detail': 'Leave request is already finalized.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            approver = Employee.objects.get(user_account=request.user, business=business)
        except Employee.DoesNotExist:
            approver = None
        leave.status = 'approved'
        leave.approved_by = approver
        leave.save(update_fields=['status', 'approved_by'])
        # Set overlapping attendance records to 'off'
        Attendance.objects.filter(
            employee=leave.employee,
            date__gte=leave.start_date,
            date__lte=leave.end_date,
        ).update(status='off')
        _log(request.user, 'update', f'Approved leave for {leave.employee}', 'Leave', leave.pk, business)
        return Response(LeaveSerializer(leave).data)

    @action(detail=True, methods=['post'], url_path='reject',
            permission_classes=[IsAuthenticated, IsHRManagerOrAdmin])
    def reject(self, request, slug=None, pk=None):
        business = _get_business(request)
        leave = get_object_or_404(Leave, pk=pk, employee__business=business)
        if leave.status != 'pending':
            return Response({'detail': 'Leave request is already finalized.'}, status=status.HTTP_400_BAD_REQUEST)
        leave.status = 'rejected'
        leave.save(update_fields=['status'])
        _log(request.user, 'update', f'Rejected leave for {leave.employee}', 'Leave', leave.pk, business)
        return Response(LeaveSerializer(leave).data)


class PerformanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PerformanceRecordSerializer
    permission_classes = [IsAuthenticated, IsOwnEmployeeOrAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return PerformanceRecord.objects.none()
        qs = PerformanceRecord.objects.filter(employee__business=business).select_related('employee__user_account')
        membership = BusinessMembership.objects.filter(
            user=self.request.user, business=business, is_active=True
        ).first()
        if membership and membership.role in ('cashier', 'sales'):
            qs = qs.filter(employee__user_account=self.request.user)
        return qs

    @action(detail=False, methods=['post'], url_path='generate',
            permission_classes=[IsAuthenticated, IsHRAdmin])
    def generate(self, request, slug=None):
        business = _get_business(request)
        period_start = request.data.get('period_start')
        period_end = request.data.get('period_end')
        if not period_start or not period_end:
            return Response({'detail': 'period_start and period_end are required.'}, status=status.HTTP_400_BAD_REQUEST)
        from datetime import date
        try:
            ps = date.fromisoformat(period_start)
            pe = date.fromisoformat(period_end)
        except ValueError:
            return Response({'detail': 'Invalid date format. Use YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        records = PerformanceService.generate_period(business, ps, pe)
        _log(request.user, 'create', f'Generated performance records for {ps} to {pe}', 'PerformanceRecord', None, business)
        return Response(PerformanceRecordSerializer(records, many=True).data)

    @action(detail=False, methods=['get'], url_path='leaderboard',
            permission_classes=[IsAuthenticated, IsHRManagerOrAdmin])
    def leaderboard(self, request, slug=None):
        business = _get_business(request)
        period_start = request.query_params.get('period_start')
        period_end = request.query_params.get('period_end')
        qs = PerformanceRecord.objects.filter(employee__business=business).order_by('-performance_score')
        if period_start:
            qs = qs.filter(period_start__gte=period_start)
        if period_end:
            qs = qs.filter(period_end__lte=period_end)
        return Response(PerformanceRecordSerializer(qs[:20], many=True).data)


class DisciplinaryViewSet(viewsets.ModelViewSet):
    serializer_class = DisciplinaryRecordSerializer
    permission_classes = [IsAuthenticated, IsHRAdmin]
    pagination_class = HRPagination

    def get_queryset(self):
        business = _get_business(self.request)
        if not business:
            return DisciplinaryRecord.objects.none()
        return DisciplinaryRecord.objects.filter(employee__business=business).select_related(
            'employee__user_account', 'issued_by__user_account'
        )

    def perform_create(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'create', f'Disciplinary record for {instance.employee}', 'DisciplinaryRecord', instance.pk, business)

    def perform_update(self, serializer):
        instance = serializer.save()
        business = _get_business(self.request)
        _log(self.request.user, 'update', f'Updated disciplinary record for {instance.employee}', 'DisciplinaryRecord', instance.pk, business)

    def perform_destroy(self, instance):
        business = _get_business(self.request)
        _log(self.request.user, 'delete', f'Deleted disciplinary record for {instance.employee}', 'DisciplinaryRecord', instance.pk, business)
        instance.delete()


class ReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsHRManagerOrAdmin]

    @action(detail=False, methods=['get'], url_path='attendance')
    def attendance(self, request, slug=None):
        """Attendance report filtered by employee, date range, status."""
        business = _get_business(request)
        qs = Attendance.objects.filter(employee__business=business).select_related('employee__user_account')
        emp = request.query_params.get('employee')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        att_status = request.query_params.get('status')
        if emp:
            qs = qs.filter(employee_id=emp)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if att_status:
            qs = qs.filter(status=att_status)
        return Response(AttendanceSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='payroll')
    def payroll(self, request, slug=None):
        """Payroll report filtered by employee, period, status."""
        business = _get_business(request)
        qs = Payroll.objects.filter(employee__business=business).select_related('employee__user_account')
        emp = request.query_params.get('employee')
        pay_status = request.query_params.get('status')
        period_start = request.query_params.get('period_start')
        period_end = request.query_params.get('period_end')
        if emp:
            qs = qs.filter(employee_id=emp)
        if pay_status:
            qs = qs.filter(status=pay_status)
        if period_start:
            qs = qs.filter(period_start__gte=period_start)
        if period_end:
            qs = qs.filter(period_end__lte=period_end)
        return Response(PayrollSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='performance')
    def performance(self, request, slug=None):
        """Performance report filtered by employee and period."""
        business = _get_business(request)
        qs = PerformanceRecord.objects.filter(employee__business=business).select_related('employee__user_account').order_by('-performance_score')
        emp = request.query_params.get('employee')
        period_start = request.query_params.get('period_start')
        period_end = request.query_params.get('period_end')
        if emp:
            qs = qs.filter(employee_id=emp)
        if period_start:
            qs = qs.filter(period_start__gte=period_start)
        if period_end:
            qs = qs.filter(period_end__lte=period_end)
        return Response(PerformanceRecordSerializer(qs, many=True).data)

    @action(detail=False, methods=['get'], url_path='shift-cash')
    def shift_cash(self, request, slug=None):
        """Shift cash difference report from pos.Shift, aggregated per cashier."""
        from pos.models import Shift
        from django.db.models import Sum, Count
        business = _get_business(request)
        qs = Shift.objects.filter(cashier__business_memberships__business=business).select_related('cashier')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        emp_id = request.query_params.get('employee')
        if date_from:
            qs = qs.filter(start_time__date__gte=date_from)
        if date_to:
            qs = qs.filter(start_time__date__lte=date_to)
        if emp_id:
            try:
                employee = Employee.objects.get(pk=emp_id, business=business)
                qs = qs.filter(cashier=employee.user_account)
            except Employee.DoesNotExist:
                pass
        # Aggregate per cashier
        aggregated = qs.values(
            'cashier__id', 'cashier__username', 'cashier__first_name', 'cashier__last_name'
        ).annotate(
            total_cash_difference=Sum('cash_difference'),
            shift_count=Count('id'),
        ).order_by('total_cash_difference')
        # Also return raw shift records
        shifts_data = []
        for shift in qs.order_by('-start_time')[:100]:
            shifts_data.append({
                'id': shift.id,
                'cashier': shift.cashier.get_full_name() or shift.cashier.username,
                'shift_number': shift.shift_number,
                'start_time': shift.start_time,
                'end_time': shift.end_time,
                'opening_cash': str(shift.opening_cash),
                'closing_cash': str(shift.closing_cash),
                'cash_difference': str(shift.cash_difference),
                'status': shift.status,
            })
        return Response({
            'summary': list(aggregated),
            'shifts': shifts_data,
        })


class DashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsHRManagerOrAdmin]

    @action(detail=False, methods=['get'], url_path='metrics')
    def metrics(self, request, slug=None):
        """HR dashboard metrics."""
        from django.db.models import Sum
        from django.utils import timezone
        from decimal import Decimal
        from datetime import date, timedelta
        business = _get_business(request)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        selected_overtime_range = request.query_params.get('overtime_range', 'month').strip().lower()
        overtime_range_error = ''
        overtime_start_date = month_start
        overtime_end_date = today
        if selected_overtime_range == '7d':
            overtime_start_date = today - timedelta(days=6)
        elif selected_overtime_range == '30d':
            overtime_start_date = today - timedelta(days=29)
        elif selected_overtime_range == 'custom':
            start_raw = request.query_params.get('overtime_start', '').strip()
            end_raw = request.query_params.get('overtime_end', '').strip()
            try:
                overtime_start_date = date.fromisoformat(start_raw)
                overtime_end_date = date.fromisoformat(end_raw)
                if overtime_start_date > overtime_end_date:
                    raise ValueError('Overtime start date cannot be after end date.')
            except ValueError:
                selected_overtime_range = 'month'
                overtime_start_date = month_start
                overtime_end_date = today
                overtime_range_error = 'Invalid overtime date range. Showing this month instead.'
        else:
            selected_overtime_range = 'month'

        total_employees = Employee.objects.filter(business=business, status='active').count()
        present_today = Attendance.objects.filter(
            employee__business=business,
            date=today,
            status__in=('present', 'late'),
        ).count()
        on_leave_today = Leave.objects.filter(
            employee__business=business,
            status='approved',
            start_date__lte=today,
            end_date__gte=today,
        ).count()

        # Top performer this month
        top_record = PerformanceRecord.objects.filter(
            employee__business=business,
            period_start__gte=month_start,
        ).order_by('-performance_score').select_related('employee__user_account').first()
        top_performer = None
        if top_record:
            top_performer = {
                'employee_id': top_record.employee.pk,
                'name': str(top_record.employee),
                'performance_score': str(top_record.performance_score),
            }

        # Payroll this month
        payroll_this_month = Payroll.objects.filter(
            employee__business=business,
            pay_date__gte=month_start,
            status='paid',
        ).aggregate(total=Sum('net_salary'))['total'] or 0

        policy = AttendanceService.get_working_hours_policy(business)
        scheduled_hours = policy['scheduled_hours']
        overtime_by_employee = {}
        total_overtime_hours = Decimal('0.00')
        if scheduled_hours > 0:
            month_attendance = Attendance.objects.filter(
                employee__business=business,
                date__gte=overtime_start_date,
                date__lte=overtime_end_date,
                status__in=('present', 'late'),
            ).select_related('employee__user_account')

            for record in month_attendance:
                worked = record.total_hours or Decimal('0.00')
                overtime = max(Decimal('0.00'), worked - scheduled_hours)
                if overtime <= 0:
                    continue

                total_overtime_hours += overtime
                emp = record.employee
                if emp.pk not in overtime_by_employee:
                    overtime_by_employee[emp.pk] = {
                        'employee_id': emp.pk,
                        'name': emp.get_full_name(),
                        'overtime_hours': Decimal('0.00'),
                        'overtime_days': 0,
                    }
                overtime_by_employee[emp.pk]['overtime_hours'] += overtime
                overtime_by_employee[emp.pk]['overtime_days'] += 1

        top_overtime_staff = sorted(
            overtime_by_employee.values(),
            key=lambda row: (-row['overtime_hours'], row['name'].lower()),
        )[:5]
        top_overtime_staff_payload = [
            {
                'employee_id': row['employee_id'],
                'name': row['name'],
                'overtime_hours': str(row['overtime_hours']),
                'overtime_days': row['overtime_days'],
            }
            for row in top_overtime_staff
        ]

        return Response({
            'total_employees': total_employees,
            'present_today': present_today,
            'on_leave_today': on_leave_today,
            'top_performer': top_performer,
            'payroll_this_month': str(payroll_this_month),
            'scheduled_hours': str(scheduled_hours),
            'total_overtime_hours': str(total_overtime_hours),
            'overtime_staff_count': len(overtime_by_employee),
            'top_overtime_staff': top_overtime_staff_payload,
            'selected_overtime_range': selected_overtime_range,
            'overtime_start_date': str(overtime_start_date),
            'overtime_end_date': str(overtime_end_date),
            'overtime_range_error': overtime_range_error,
        })
