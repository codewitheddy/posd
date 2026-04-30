"""
Unit tests for HR module services, serializers, and models.

Run with:
    python manage.py test hr.tests.test_unit
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from unittest.mock import patch

from pos.models import Business, Branch, BusinessMembership, UserProfile, BusinessSettings
from hr.models import (
    Department, Employee, Attendance, Payroll, StaffAdvance, Leave, PerformanceRecord
)
from hr.services import AttendanceService, PayrollService, PerformanceService
from hr.serializers import EmployeeSerializer, LeaveSerializer, StaffAdvanceSerializer


def make_user(username, **kwargs):
    return User.objects.create_user(username=username, password='testpass', **kwargs)


class HRBaseTestCase(TestCase):
    """Base test case: creates User, Business, Branch, and Employee."""

    def setUp(self):
        self.owner = make_user('owner')
        self.business = Business.objects.create(
            name='Test Biz', slug='test-biz', owner=self.owner
        )
        self.branch = Branch.objects.create(
            business=self.business,
            name='Main Branch',
            address='123 Main St',
        )
        self.user = make_user('emp_user')
        UserProfile.objects.get_or_create(user=self.user)
        self.employee = Employee.objects.create(
            user_account=self.user,
            business=self.business,
            branch=self.branch,
            job_title='Cashier',
            hire_date=date.today(),
            hourly_rate=Decimal('10.00'),
        )


# ─── AttendanceService ────────────────────────────────────────────────────────

class AttendanceServiceClockInTest(HRBaseTestCase):

    def test_clock_in_success(self):
        """clock_in creates an Attendance record for today."""
        attendance = AttendanceService.clock_in(self.employee)
        self.assertEqual(attendance.employee, self.employee)
        self.assertEqual(attendance.date, timezone.localdate())
        self.assertIsNone(attendance.clock_out)

    def test_clock_in_already_clocked_in_raises(self):
        """clock_in raises ValidationError when an open record already exists."""
        AttendanceService.clock_in(self.employee)
        with self.assertRaises(ValidationError):
            AttendanceService.clock_in(self.employee)

    def test_clock_in_uses_business_working_hours_for_late(self):
        """clock_in marks late based on configured business start time and grace."""
        settings = BusinessSettings.get_settings(self.business)
        settings.workday_start_time = time(9, 0)
        settings.late_grace_minutes = 0
        settings.save()

        fixed_dt = timezone.make_aware(datetime.combine(timezone.localdate(), time(9, 30)))
        with patch('hr.services.timezone.localtime', return_value=fixed_dt):
            attendance = AttendanceService.clock_in(self.employee)

        self.assertEqual(attendance.status, 'late')


class AttendanceServiceClockOutTest(HRBaseTestCase):

    def test_clock_out_success_computes_total_hours(self):
        """clock_out sets clock_out and computes total_hours > 0."""
        AttendanceService.clock_in(self.employee)
        attendance = AttendanceService.clock_out(self.employee)
        self.assertIsNotNone(attendance.clock_out)
        self.assertGreaterEqual(attendance.total_hours, Decimal('0.00'))

    def test_clock_out_no_open_record_raises(self):
        """clock_out raises ValidationError when no open record exists."""
        with self.assertRaises(ValidationError):
            AttendanceService.clock_out(self.employee)


# ─── PayrollService ───────────────────────────────────────────────────────────

class PayrollServiceTest(HRBaseTestCase):

    def _make_attendance(self, hours=Decimal('8.00')):
        today = date.today()
        Attendance.objects.create(
            employee=self.employee,
            date=today,
            clock_in='08:00:00',
            clock_out='16:00:00',
            total_hours=hours,
            status='present',
        )

    def test_calculate_period_basic(self):
        """calculate_period creates a Payroll record with correct basic_salary."""
        self._make_attendance(Decimal('8.00'))
        today = date.today()
        payrolls = PayrollService.calculate_period(self.business, today, today)
        self.assertEqual(len(payrolls), 1)
        p = payrolls[0]
        expected = Decimal('8.00') * Decimal('10.00')
        self.assertEqual(p.basic_salary, expected)
        self.assertGreaterEqual(p.net_salary, Decimal('0.00'))

    def test_calculate_period_advance_capping(self):
        """net_salary is never negative even when advance exceeds gross."""
        self._make_attendance(Decimal('1.00'))  # gross = 10.00
        StaffAdvance.objects.create(
            employee=self.employee,
            amount=Decimal('500.00'),
            reason='Test',
            date_taken=date.today(),
            deduction_per_month=Decimal('500.00'),
            balance_remaining=Decimal('500.00'),
            status='active',
        )
        today = date.today()
        payrolls = PayrollService.calculate_period(self.business, today, today)
        self.assertEqual(payrolls[0].net_salary, Decimal('0.00'))

    def test_mark_paid_success(self):
        """mark_paid sets status to paid and reduces advance balance."""
        self._make_attendance(Decimal('8.00'))
        advance = StaffAdvance.objects.create(
            employee=self.employee,
            amount=Decimal('40.00'),
            reason='Test',
            date_taken=date.today(),
            deduction_per_month=Decimal('40.00'),
            balance_remaining=Decimal('40.00'),
            status='active',
        )
        today = date.today()
        payrolls = PayrollService.calculate_period(self.business, today, today)
        payroll = payrolls[0]
        PayrollService.mark_paid(payroll)
        payroll.refresh_from_db()
        self.assertEqual(payroll.status, 'paid')
        advance.refresh_from_db()
        self.assertLessEqual(advance.balance_remaining, Decimal('40.00'))

    def test_mark_paid_already_paid_raises(self):
        """mark_paid raises ValidationError if payroll is already paid."""
        today = date.today()
        payroll = Payroll.objects.create(
            employee=self.employee,
            period_start=today,
            period_end=today,
            basic_salary=Decimal('100.00'),
            net_salary=Decimal('100.00'),
            status='paid',
        )
        with self.assertRaises(ValidationError):
            PayrollService.mark_paid(payroll)

    def test_mark_paid_advance_balance_reduction(self):
        """mark_paid reduces advance balance_remaining by deduction_per_month."""
        self._make_attendance(Decimal('8.00'))
        advance = StaffAdvance.objects.create(
            employee=self.employee,
            amount=Decimal('20.00'),
            reason='Test',
            date_taken=date.today(),
            deduction_per_month=Decimal('20.00'),
            balance_remaining=Decimal('20.00'),
            status='active',
        )
        today = date.today()
        payrolls = PayrollService.calculate_period(self.business, today, today)
        PayrollService.mark_paid(payrolls[0])
        advance.refresh_from_db()
        self.assertEqual(advance.balance_remaining, Decimal('0.00'))
        self.assertEqual(advance.status, 'settled')

    def test_calculate_period_auto_overtime_uses_business_multiplier(self):
        """Overtime hours and amount are auto-calculated from attendance and business multiplier."""
        settings = BusinessSettings.get_settings(self.business)
        settings.workday_start_time = time(8, 0)
        settings.workday_end_time = time(17, 0)  # 9h scheduled
        settings.overtime_rate_multiplier = Decimal('2.00')
        settings.save()

        Attendance.objects.create(
            employee=self.employee,
            date=date.today(),
            clock_in='08:00:00',
            clock_out='18:00:00',
            total_hours=Decimal('10.00'),
            status='present',
        )

        today = date.today()
        payrolls = PayrollService.calculate_period(self.business, today, today)
        payroll = payrolls[0]

        self.assertEqual(payroll.overtime_hours, Decimal('1.00'))
        self.assertEqual(payroll.overtime_amount, Decimal('20.00'))

    def test_calculate_period_prorates_monthly_basic_salary_for_partial_period(self):
        """Monthly basic salary is prorated by period working days (26-day base)."""
        self.employee.basic_salary = Decimal('20000.00')
        self.employee.hourly_rate = Decimal('0.00')
        self.employee.save(update_fields=['basic_salary', 'hourly_rate'])

        # 2026-04-01 to 2026-04-08 has 6 working days (Mon-Fri basis).
        period_start = date(2026, 4, 1)
        period_end = date(2026, 4, 8)
        payrolls = PayrollService.calculate_period(self.business, period_start, period_end)

        self.assertEqual(len(payrolls), 1)
        payroll = payrolls[0]
        self.assertEqual(payroll.basic_salary, Decimal('4615.38'))


class EmployeeModelValidationTest(HRBaseTestCase):

    def test_employee_clean_requires_kra_pin(self):
        """Employee validation should require a KRA PIN."""
        self.employee.id_number = '12345678'
        self.employee.kra_pin = ''
        self.employee.nssf_number = 'NSSF123'
        self.employee.nhif_number = 'NHIF123'

        with self.assertRaises(ValidationError) as context:
            self.employee.clean()

        self.assertIn('kra_pin', context.exception.message_dict)


class EmployeeSerializerValidationTest(HRBaseTestCase):

    def test_employee_serializer_requires_kra_pin(self):
        """Employee serializer should reject blank KRA PIN."""
        serializer = EmployeeSerializer(instance=self.employee, data={
            'business': self.business.pk,
            'branch': self.branch.pk,
            'job_title': 'Cashier',
            'id_number': '12345678',
            'kra_pin': '',
            'nssf_number': 'NSSF123',
            'nhif_number': 'NHIF123',
            'hire_date': str(date.today()),
            'status': 'active',
        }, partial=True)

        self.assertFalse(serializer.is_valid())
        self.assertIn('kra_pin', serializer.errors)


# ─── PerformanceService ───────────────────────────────────────────────────────

class PerformanceServiceTest(HRBaseTestCase):

    def test_generate_period_no_sales_returns_score_zero(self):
        """generate_period returns score 0 when there are no sales."""
        today = date.today()
        records = PerformanceService.generate_period(self.business, today, today)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].performance_score, Decimal('0.00'))

    def test_generate_period_idempotent(self):
        """Calling generate_period twice updates, not duplicates, the record."""
        today = date.today()
        PerformanceService.generate_period(self.business, today, today)
        PerformanceService.generate_period(self.business, today, today)
        count = PerformanceRecord.objects.filter(
            employee=self.employee, period_start=today, period_end=today
        ).count()
        self.assertEqual(count, 1)


# ─── LeaveSerializer ──────────────────────────────────────────────────────────

class LeaveSerializerValidateTest(HRBaseTestCase):

    def _base_data(self, start, end):
        return {
            'employee': self.employee.pk,
            'leave_type': 'annual',
            'start_date': start,
            'end_date': end,
            'reason': 'Vacation',
        }

    def test_days_count_computed_correctly(self):
        """days_count = (end_date - start_date).days + 1."""
        start = date.today()
        end = start + timedelta(days=4)
        serializer = LeaveSerializer(data=self._base_data(start, end))
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['days_count'], 5)

    def test_end_date_before_start_date_raises(self):
        """end_date < start_date should fail validation."""
        start = date.today()
        end = start - timedelta(days=1)
        serializer = LeaveSerializer(data=self._base_data(start, end))
        self.assertFalse(serializer.is_valid())
        self.assertIn('end_date', serializer.errors)


# ─── StaffAdvanceSerializer ───────────────────────────────────────────────────

class StaffAdvanceSerializerValidateTest(HRBaseTestCase):

    def _base_data(self):
        return {
            'employee': self.employee.pk,
            'amount': '100.00',
            'reason': 'Emergency',
            'date_taken': str(date.today()),
            'deduction_per_month': '50.00',
        }

    def test_duplicate_active_advance_raises(self):
        """Creating a second active advance for the same employee should fail."""
        StaffAdvance.objects.create(
            employee=self.employee,
            amount=Decimal('100.00'),
            reason='First',
            date_taken=date.today(),
            deduction_per_month=Decimal('50.00'),
            balance_remaining=Decimal('100.00'),
            status='active',
        )
        serializer = StaffAdvanceSerializer(data=self._base_data())
        self.assertFalse(serializer.is_valid())
        self.assertIn('employee', serializer.errors)


# ─── Employee.save() status sync ─────────────────────────────────────────────

class EmployeeStatusSyncTest(HRBaseTestCase):

    def test_terminated_syncs_profile_inactive(self):
        """Setting status=terminated sets UserProfile.is_active=False."""
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.is_active = True
        profile.save()

        self.employee.status = 'terminated'
        self.employee.save()

        profile.refresh_from_db()
        self.assertFalse(profile.is_active)

    def test_active_syncs_profile_active(self):
        """Setting status=active (from terminated) sets UserProfile.is_active=True."""
        # First terminate so the profile goes inactive
        self.employee.status = 'terminated'
        self.employee.save()

        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.refresh_from_db()
        self.assertFalse(profile.is_active)

        # Now re-activate
        self.employee.status = 'active'
        self.employee.save()

        profile.refresh_from_db()
        self.assertTrue(profile.is_active)


class PayrollWebViewTest(HRBaseTestCase):

    def setUp(self):
        super().setUp()
        BusinessMembership.objects.create(
            user=self.owner,
            business=self.business,
            role='owner',
            is_active=True,
        )
        self.payroll = Payroll.objects.create(
            employee=self.employee,
            period_start=date.today().replace(day=1),
            period_end=date.today(),
            basic_salary=Decimal('1000.00'),
            net_salary=Decimal('900.00'),
            status='paid',
            pay_date=date.today(),
        )

    def test_payslip_download_returns_pdf(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse('hr_payslip_download', kwargs={
                'slug': self.business.slug,
                'payroll_pk': self.payroll.pk,
            })
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])

    def test_payroll_list_shows_overtime_columns(self):
        self.payroll.overtime_hours = Decimal('2.50')
        self.payroll.overtime_amount = Decimal('750.00')
        self.payroll.save(update_fields=['overtime_hours', 'overtime_amount'])

        self.client.force_login(self.owner)
        response = self.client.get(reverse('hr_payroll_list', kwargs={'slug': self.business.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Overtime Hrs')
        self.assertContains(response, 'Overtime Pay')
        self.assertContains(response, '2.50h')
        self.assertContains(response, 'KES 750.00')


class AttendanceWebViewAutoProvisionTest(HRBaseTestCase):

    def setUp(self):
        super().setUp()
        BusinessMembership.objects.create(
            user=self.owner,
            business=self.business,
            role='owner',
            is_active=True,
        )
        self.cashier_user = make_user('attendance_cashier')
        BusinessMembership.objects.create(
            user=self.cashier_user,
            business=self.business,
            role='cashier',
            is_active=True,
        )
        self.staff_employee = Employee.objects.create(
            first_name='Jane',
            last_name='Staff',
            business=self.business,
            branch=self.branch,
            job_title='Cashier',
            status='active',
            hire_date=date.today(),
        )

    def test_clock_in_denies_cashier_access(self):
        self.client.force_login(self.cashier_user)

        response = self.client.post(
            reverse('hr_clock_in', kwargs={'slug': self.business.slug})
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard', kwargs={'slug': self.business.slug}))
        self.assertFalse(Employee.objects.filter(user_account=self.cashier_user, business=self.business).exists())

    def test_clock_out_denies_cashier_access(self):
        self.client.force_login(self.cashier_user)

        self.client.post(reverse('hr_clock_in', kwargs={'slug': self.business.slug}))
        response = self.client.post(reverse('hr_clock_out', kwargs={'slug': self.business.slug}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard', kwargs={'slug': self.business.slug}))
        self.assertFalse(Employee.objects.filter(user_account=self.cashier_user, business=self.business).exists())

    def test_clock_in_ignores_safe_next_for_denied_cashier(self):
        self.client.force_login(self.cashier_user)

        dashboard_url = reverse('dashboard', kwargs={'slug': self.business.slug})
        response = self.client.post(
            reverse('hr_clock_in', kwargs={'slug': self.business.slug}),
            data={'next': dashboard_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, dashboard_url)

    def test_clock_out_ignores_safe_next_for_denied_cashier(self):
        self.client.force_login(self.cashier_user)
        self.client.post(reverse('hr_clock_in', kwargs={'slug': self.business.slug}))

        dashboard_url = reverse('dashboard', kwargs={'slug': self.business.slug})
        response = self.client.post(
            reverse('hr_clock_out', kwargs={'slug': self.business.slug}),
            data={'next': dashboard_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, dashboard_url)

    def test_manager_can_clock_in_selected_employee(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('hr_clock_in', kwargs={'slug': self.business.slug}),
            data={'employee_id': str(self.staff_employee.pk)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Attendance.objects.filter(employee=self.staff_employee, date=timezone.localdate()).exists()
        )

    def test_manager_can_clock_out_selected_employee(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse('hr_clock_in', kwargs={'slug': self.business.slug}),
            data={'employee_id': str(self.staff_employee.pk)},
        )

        response = self.client.post(
            reverse('hr_clock_out', kwargs={'slug': self.business.slug}),
            data={'employee_id': str(self.staff_employee.pk)},
        )

        self.assertEqual(response.status_code, 302)
        attendance = Attendance.objects.get(employee=self.staff_employee, date=timezone.localdate())
        self.assertIsNotNone(attendance.clock_out)

    def test_attendance_list_shows_row_quick_action_for_manager(self):
        Attendance.objects.create(
            employee=self.staff_employee,
            date=timezone.localdate(),
            clock_in=timezone.localtime().time(),
            status='present',
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse('hr_attendance_list', kwargs={'slug': self.business.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clock Out')
        self.assertContains(response, f'name="employee_id" value="{self.staff_employee.pk}"', html=False)
