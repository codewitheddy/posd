from django.contrib.auth.models import Permission, User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from pos.models import Business, BusinessMembership, POSSession, ZReport


class ZReportRegressionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='z-owner', password='pass123!')
        self.cashier = User.objects.create_user(username='z-cashier', password='pass123!')
        self.viewer = User.objects.create_user(username='z-viewer', password='pass123!')

        self.business = Business.objects.create(
            name='ZReport Business',
            slug='zreport-business',
            owner=self.owner,
        )
        BusinessMembership.objects.create(user=self.owner, business=self.business, role='owner')
        BusinessMembership.objects.create(user=self.cashier, business=self.business, role='cashier')
        BusinessMembership.objects.create(user=self.viewer, business=self.business, role='viewer')

        self.session = POSSession.objects.create(
            business=self.business,
            opened_by=self.owner,
            opening_cash='1000.00',
            status='closed',
            closed_by=self.owner,
            closed_at=timezone.now(),
        )
        self.zreport = ZReport.objects.create(
            business=self.business,
            session=self.session,
            created_by=self.owner,
            report_data={
                'sales_summary': {'gross_sales': 1000.0, 'net_sales': 900.0, 'total_transactions': 2},
                'cash_management': {'difference': 0.0},
                'payment_breakdown': [],
                'top_products': [],
            },
        )

    def test_cashier_cannot_view_zreport_detail(self):
        self.client.force_login(self.cashier)

        response = self.client.get(
            reverse('zreport_detail', kwargs={'slug': self.business.slug, 'z_number': self.zreport.z_number}),
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("don't have permission to view Z-Reports" in m for m in messages))

    def test_cashier_cannot_export_zreport_json(self):
        self.client.force_login(self.cashier)

        response = self.client.get(
            reverse('zreport_export_json', kwargs={'slug': self.business.slug, 'z_number': self.zreport.z_number}),
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("don't have permission to export Z-Reports" in m for m in messages))

    def test_cashier_cannot_access_zreport_api_data(self):
        self.client.force_login(self.cashier)

        response = self.client.get(
            reverse('api_zreport_data', kwargs={'slug': self.business.slug, 'z_number': self.zreport.z_number})
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn('error', response.json())

    def test_viewer_can_view_zreport_detail(self):
        self.client.force_login(self.viewer)
        with patch('pos.zreport_views.render', return_value=HttpResponse('ok')) as mock_render:
            response = self.client.get(
                reverse('zreport_detail', kwargs={'slug': self.business.slug, 'z_number': self.zreport.z_number})
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        context = mock_render.call_args[0][2]
        self.assertTrue(context['can_export_zreport'])
        self.assertTrue(context['can_verify_zreport'])

    def test_zreport_is_immutable_after_creation(self):
        self.zreport.report_data = {'sales_summary': {'gross_sales': 777.0}}

        with self.assertRaises(ValidationError):
            self.zreport.save()

    def test_void_metadata_update_remains_allowed(self):
        permission = Permission.objects.get(codename='can_void_zreport')
        self.owner.user_permissions.add(permission)

        self.zreport.is_voided = True
        self.zreport.voided_by = self.owner
        self.zreport.voided_at = timezone.now()
        self.zreport.void_reason = 'Voiding for audit correction reason'
        self.zreport.save(update_fields=['is_voided', 'voided_by', 'voided_at', 'void_reason'])

        self.zreport.refresh_from_db()
        self.assertTrue(self.zreport.is_voided)

    def test_zreport_cannot_be_deleted(self):
        with self.assertRaises(ValueError):
            self.zreport.delete()
