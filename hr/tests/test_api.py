"""
API smoke tests for HR module endpoints.

Run with:
    python manage.py test hr.tests.test_api
"""
from datetime import date
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from pos.models import Business, Branch, BusinessMembership, UserProfile
from hr.models import Employee, Attendance


def make_user(username, **kwargs):
    return User.objects.create_user(username=username, password='testpass', **kwargs)


class HRAPIBaseTestCase(TestCase):
    """Base: creates User, Business, Branch, Employee, and an APIClient."""

    def setUp(self):
        self.client = APIClient()

        # Owner / admin user
        self.admin_user = make_user('admin_user')
        self.business = Business.objects.create(
            name='API Test Biz', slug='api-test-biz', owner=self.admin_user
        )
        BusinessMembership.objects.create(
            user=self.admin_user, business=self.business, role='admin', is_active=True
        )
        self.branch = Branch.objects.create(
            business=self.business,
            name='HQ',
            address='1 HQ Road',
        )
        UserProfile.objects.get_or_create(user=self.admin_user)
        self.admin_employee = Employee.objects.create(
            user_account=self.admin_user,
            business=self.business,
            branch=self.branch,
            job_title='Admin',
            hire_date=date.today(),
        )

        # Cashier user
        self.cashier_user = make_user('cashier_user')
        BusinessMembership.objects.create(
            user=self.cashier_user, business=self.business, role='cashier', is_active=True
        )
        UserProfile.objects.get_or_create(user=self.cashier_user)
        self.cashier_employee = Employee.objects.create(
            user_account=self.cashier_user,
            business=self.business,
            branch=self.branch,
            job_title='Cashier',
            hire_date=date.today(),
        )

        # Manager user
        self.manager_user = make_user('manager_user')
        BusinessMembership.objects.create(
            user=self.manager_user, business=self.business, role='manager', is_active=True
        )
        UserProfile.objects.get_or_create(user=self.manager_user)
        Employee.objects.create(
            user_account=self.manager_user,
            business=self.business,
            branch=self.branch,
            job_title='Manager',
            hire_date=date.today(),
        )

        self.slug = self.business.slug
        self.base_url = f'/b/{self.slug}/hr/api'

    def _login(self, user):
        self.client.force_authenticate(user=user)

    def _logout(self):
        self.client.force_authenticate(user=None)


# ─── GET /employees/ ──────────────────────────────────────────────────────────

class EmployeeListAPITest(HRAPIBaseTestCase):

    def test_admin_gets_200(self):
        self._login(self.admin_user)
        response = self.client.get(f'{self.base_url}/employees/')
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_gets_403_or_401(self):
        self._logout()
        response = self.client.get(f'{self.base_url}/employees/')
        self.assertIn(response.status_code, [401, 403])


# ─── POST /attendance/clock-in/ ───────────────────────────────────────────────

class AttendanceClockInAPITest(HRAPIBaseTestCase):

    def test_admin_with_employee_profile_gets_201(self):
        self._login(self.admin_user)
        response = self.client.post(f'{self.base_url}/attendance/clock-in/')
        self.assertEqual(response.status_code, 201)

    def test_cashier_with_employee_profile_gets_403(self):
        self._login(self.cashier_user)
        response = self.client.post(f'{self.base_url}/attendance/clock-in/')
        self.assertEqual(response.status_code, 403)

    def test_admin_already_clocked_in_gets_400(self):
        self._login(self.admin_user)
        self.client.post(f'{self.base_url}/attendance/clock-in/')
        response = self.client.post(f'{self.base_url}/attendance/clock-in/')
        self.assertEqual(response.status_code, 400)


# ─── GET /dashboard/metrics/ ─────────────────────────────────────────────────

class DashboardMetricsAPITest(HRAPIBaseTestCase):

    def test_admin_gets_200(self):
        self._login(self.admin_user)
        response = self.client.get(f'{self.base_url}/dashboard/metrics/')
        self.assertEqual(response.status_code, 200)

    def test_manager_gets_403(self):
        self._login(self.manager_user)
        response = self.client.get(f'{self.base_url}/dashboard/metrics/')
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_gets_403_or_401(self):
        self._logout()
        response = self.client.get(f'{self.base_url}/dashboard/metrics/')
        self.assertIn(response.status_code, [401, 403])

    def test_metrics_includes_overtime_summary(self):
        self._login(self.admin_user)

        today = date.today()
        # Default policy is 9 scheduled hours (08:00 to 17:00), so 11h means 2h overtime.
        Attendance.objects.create(
            employee=self.cashier_employee,
            date=today,
            clock_in='08:00:00',
            clock_out='19:00:00',
            total_hours=Decimal('11.00'),
            status='present',
        )
        Attendance.objects.create(
            employee=self.cashier_employee,
            date=today - timedelta(days=1),
            clock_in='08:00:00',
            clock_out='18:00:00',
            total_hours=Decimal('10.00'),
            status='present',
        )

        response = self.client.get(f'{self.base_url}/dashboard/metrics/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['overtime_staff_count'], 1)
        self.assertEqual(response.data['total_overtime_hours'], '3.00')
        self.assertEqual(len(response.data['top_overtime_staff']), 1)
        self.assertEqual(response.data['top_overtime_staff'][0]['overtime_days'], 2)

    def test_metrics_overtime_range_7d_excludes_older_records(self):
        self._login(self.admin_user)

        today = date.today()
        Attendance.objects.create(
            employee=self.cashier_employee,
            date=today,
            clock_in='08:00:00',
            clock_out='19:00:00',
            total_hours=Decimal('11.00'),
            status='present',
        )
        Attendance.objects.create(
            employee=self.cashier_employee,
            date=today - timedelta(days=10),
            clock_in='08:00:00',
            clock_out='19:00:00',
            total_hours=Decimal('11.00'),
            status='present',
        )

        response = self.client.get(f'{self.base_url}/dashboard/metrics/?overtime_range=7d')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['selected_overtime_range'], '7d')
        self.assertEqual(response.data['total_overtime_hours'], '2.00')
        self.assertEqual(response.data['overtime_staff_count'], 1)


# ─── POST /leave/ ─────────────────────────────────────────────────────────────

class LeaveCreateAPITest(HRAPIBaseTestCase):

    def test_admin_creates_leave_gets_201(self):
        self._login(self.admin_user)
        payload = {
            'employee': self.admin_employee.pk,
            'leave_type': 'annual',
            'start_date': str(date.today()),
            'end_date': str(date.today()),
            'reason': 'Rest day',
        }
        response = self.client.post(f'{self.base_url}/leave/', payload, format='json')
        self.assertEqual(response.status_code, 201)

    def test_cashier_creates_own_leave_gets_403(self):
        self._login(self.cashier_user)
        payload = {
            'employee': self.cashier_employee.pk,
            'leave_type': 'annual',
            'start_date': str(date.today()),
            'end_date': str(date.today()),
            'reason': 'Rest day',
        }
        response = self.client.post(f'{self.base_url}/leave/', payload, format='json')
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_leave_create_gets_403_or_401(self):
        self._logout()
        payload = {
            'employee': self.cashier_employee.pk,
            'leave_type': 'annual',
            'start_date': str(date.today()),
            'end_date': str(date.today()),
            'reason': 'Rest day',
        }
        response = self.client.post(f'{self.base_url}/leave/', payload, format='json')
        self.assertIn(response.status_code, [401, 403])
