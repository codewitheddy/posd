from rest_framework import serializers
from decimal import Decimal
from .models import (
    Department, Employee, Attendance, Payroll,
    StaffAdvance, Leave, PerformanceRecord, DisciplinaryRecord
)


class DepartmentSerializer(serializers.ModelSerializer):
    manager_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Department
        fields = ['id', 'business', 'name', 'description', 'manager', 'manager_name', 'created_at']
        read_only_fields = ['created_at']

    def get_manager_name(self, obj):
        if obj.manager:
            return obj.manager.get_full_name()
        return None

    def validate(self, data):
        business = data.get('business') or (self.instance.business if self.instance else None)
        name = data.get('name') or (self.instance.name if self.instance else None)
        qs = Department.objects.filter(business=business, name=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({'name': 'Department with this name already exists.'})
        return data


class EmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField(read_only=True)
    username = serializers.SerializerMethodField(read_only=True)
    effective_hourly_rate = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Employee
        fields = [
            'id', 'user_account', 'username', 'full_name', 'business', 'branch',
            'department', 'job_title', 'staff_code', 'id_number', 'kra_pin', 'nssf_number', 'nhif_number',
            'address', 'basic_salary', 'hourly_rate', 'effective_hourly_rate',
            'house_allowance', 'transport_allowance', 'medical_allowance', 'other_allowance', 'other_allowances',
            'status', 'emergency_contact_name', 'emergency_contact_phone',
            'notes', 'hire_date', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at', 'effective_hourly_rate', 'staff_code']

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_username(self, obj):
        return obj.user_account.username if obj.user_account else None

    def get_effective_hourly_rate(self, obj):
        return obj.effective_hourly_rate

    def validate(self, data):
        user_account = data.get('user_account') or (self.instance.user_account if self.instance else None)
        business = data.get('business') or (self.instance.business if self.instance else None)
        kra_pin = data.get('kra_pin') if 'kra_pin' in data else (self.instance.kra_pin if self.instance else None)
        if user_account and business:
            qs = Employee.objects.filter(user_account=user_account, business=business)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {'user_account': 'Employee already exists for this user in this business.'}
                )
        if not kra_pin:
            raise serializers.ValidationError({'kra_pin': 'KRA PIN is required.'})
        return data


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'employee', 'employee_name', 'date', 'clock_in', 'clock_out',
                  'total_hours', 'status', 'notes']
        read_only_fields = ['total_hours']

    def get_employee_name(self, obj):
        return str(obj.employee)


class PayrollSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)
    total_allowances = serializers.SerializerMethodField(read_only=True)
    gross_salary = serializers.SerializerMethodField(read_only=True)
    total_deductions = serializers.SerializerMethodField(read_only=True)
    proration_note = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Payroll
        fields = [
            'id', 'employee', 'employee_name', 'period_start', 'period_end',
            'basic_salary', 'house_allowance', 'transport_allowance', 'medical_allowance', 'other_allowance',
            'total_allowances', 'overtime_hours', 'overtime_amount', 'bonus', 'commission',
            'gross_salary', 'paye', 'shif', 'nssf', 'housing_levy', 'absence_deduction', 'other_deductions', 'advances_deducted',
            'total_deductions', 'net_salary', 'pay_date', 'status', 'notes', 'proration_note',
        ]
        read_only_fields = [
            'basic_salary', 'house_allowance', 'transport_allowance', 'medical_allowance', 'other_allowance',
            'total_allowances', 'overtime_amount', 'gross_salary', 'paye', 'shif', 'nssf', 'housing_levy', 'absence_deduction',
            'advances_deducted', 'total_deductions', 'net_salary', 'pay_date', 'proration_note'
        ]

    def get_employee_name(self, obj):
        return str(obj.employee)

    def get_total_allowances(self, obj):
        return obj.total_allowances

    def get_gross_salary(self, obj):
        return obj.gross_salary

    def get_total_deductions(self, obj):
        return obj.total_deductions

    def get_proration_note(self, obj):
        return (
            'Monthly basic salary and fixed allowances are prorated by working days '
            'in the selected pay period (26-working-day monthly base).'
        )

    def validate(self, data):
        if self.instance and self.instance.status == 'paid':
            raise serializers.ValidationError("Cannot modify a paid payroll record.")
        return data


class StaffAdvanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = StaffAdvance
        fields = ['id', 'employee', 'employee_name', 'amount', 'reason', 'date_taken',
                  'deduction_per_month', 'balance_remaining', 'status']
        read_only_fields = ['balance_remaining', 'status']

    def get_employee_name(self, obj):
        return str(obj.employee)

    def validate(self, data):
        deduction = data.get('deduction_per_month')
        if deduction is not None and deduction <= Decimal('0.00'):
            raise serializers.ValidationError(
                {'deduction_per_month': 'Deduction per month must be greater than zero.'}
            )
        # On create, check for existing active advance
        if not self.instance:
            employee = data.get('employee')
            if employee and StaffAdvance.objects.filter(employee=employee, status='active').exists():
                raise serializers.ValidationError(
                    {'employee': 'Employee already has an active advance.'}
                )
        return data

    def create(self, validated_data):
        validated_data['balance_remaining'] = validated_data['amount']
        validated_data['status'] = 'active'
        return super().create(validated_data)


class LeaveSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)
    approved_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Leave
        fields = ['id', 'employee', 'employee_name', 'leave_type', 'start_date', 'end_date',
                  'days_count', 'reason', 'status', 'approved_by', 'approved_by_name', 'created_at']
        read_only_fields = ['days_count', 'status', 'approved_by', 'created_at']

    def get_employee_name(self, obj):
        return str(obj.employee)

    def get_approved_by_name(self, obj):
        if obj.approved_by:
            return str(obj.approved_by)
        return None

    def validate(self, data):
        start = data.get('start_date') or (self.instance.start_date if self.instance else None)
        end = data.get('end_date') or (self.instance.end_date if self.instance else None)
        if start and end:
            if end < start:
                raise serializers.ValidationError(
                    {'end_date': 'End date must be on or after start date.'}
                )
            data['days_count'] = (end - start).days + 1
        return data


class PerformanceRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PerformanceRecord
        fields = [
            'id', 'employee', 'employee_name', 'period_start', 'period_end',
            'total_sales', 'total_transactions', 'total_discounts_given',
            'total_voids', 'total_refunds', 'shift_shortages', 'performance_score', 'created_at',
        ]
        read_only_fields = [
            'total_sales', 'total_transactions', 'total_discounts_given',
            'total_voids', 'total_refunds', 'shift_shortages', 'performance_score', 'created_at',
        ]

    def get_employee_name(self, obj):
        return str(obj.employee)


class DisciplinaryRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField(read_only=True)
    issued_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DisciplinaryRecord
        fields = [
            'id', 'employee', 'employee_name', 'incident_date', 'incident_type',
            'description', 'action_taken', 'issued_by', 'issued_by_name', 'created_at',
        ]
        read_only_fields = ['created_at']

    def get_employee_name(self, obj):
        return str(obj.employee)

    def get_issued_by_name(self, obj):
        return str(obj.issued_by)
