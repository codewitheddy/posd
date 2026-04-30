from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient

from pos.models import (
    Business,
    BusinessMembership,
    PaymentMethod,
    Purchase,
    Supplier,
    SupplierPayment,
)


class SupplierRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='supplier-owner', password='pass123!')
        self.api_user = User.objects.create_user(username='supplier-api-user', password='pass123!')

        self.business_one = Business.objects.create(
            name='Business One',
            slug='business-one',
            owner=self.user,
        )
        self.business_two = Business.objects.create(
            name='Business Two',
            slug='business-two',
            owner=self.user,
        )

        BusinessMembership.objects.create(user=self.user, business=self.business_one, role='owner')
        BusinessMembership.objects.create(user=self.user, business=self.business_two, role='owner')
        BusinessMembership.objects.create(user=self.api_user, business=self.business_one, role='owner')

        self.client.force_login(self.user)
        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.api_user)

    def _ensure_active_payment_method(self, business):
        payment_method = PaymentMethod.objects.filter(business=business, is_active=True).first()
        if payment_method is None:
            payment_method = PaymentMethod.objects.create(
                business=business,
                name='CASH',
                code='CASH',
                is_active=True,
            )
        return payment_method

    def test_supplier_balances_is_scoped_to_request_business(self):
        supplier_one = Supplier.objects.create(business=self.business_one, name='Alpha Traders')
        supplier_two = Supplier.objects.create(business=self.business_two, name='Bravo Wholesalers')

        url = reverse('supplier_balances', kwargs={'slug': self.business_one.slug})
        with patch('pos.views.render', return_value=HttpResponse('ok')) as mock_render:
            response = self.client.get(url, {'show_all': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        context = mock_render.call_args[0][2]
        supplier_ids = {row['supplier'].id for row in context['supplier_data']}
        self.assertIn(supplier_one.id, supplier_ids)
        self.assertNotIn(supplier_two.id, supplier_ids)

    def test_supplier_api_queryset_is_scoped_by_active_memberships(self):
        supplier_one = Supplier.objects.create(business=self.business_one, name='One Supplies')
        supplier_two = Supplier.objects.create(business=self.business_two, name='Two Supplies')

        url = reverse('supplier-list')
        response = self.api_client.get(url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        results = payload.get('results', payload)
        returned_ids = {entry['id'] for entry in results}

        self.assertIn(supplier_one.id, returned_ids)
        self.assertNotIn(supplier_two.id, returned_ids)

    def test_supplier_create_rejects_case_insensitive_duplicate_name(self):
        Supplier.objects.create(business=self.business_one, name='Acme Suppliers')
        url = reverse('supplier_create', kwargs={'slug': self.business_one.slug})

        with patch('pos.views.render', return_value=HttpResponse('invalid')) as mock_render:
            response = self.client.post(
                url,
                {
                    'name': 'acme suppliers',
                    'contact_person': 'Jane',
                    'email': 'jane@example.com',
                    'phone': '0700000000',
                    'address': 'Nairobi',
                    'notes': 'duplicate attempt',
                    'is_active': 'on',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('already exists for this business.', ' '.join(messages))
        self.assertEqual(
            Supplier.objects.filter(business=self.business_one, name__iexact='acme suppliers').count(),
            1,
        )

    def test_supplier_edit_rejects_case_insensitive_duplicate_name(self):
        existing = Supplier.objects.create(business=self.business_one, name='Acme Suppliers')
        target = Supplier.objects.create(business=self.business_one, name='Bravo Suppliers')
        url = reverse('supplier_edit', kwargs={'slug': self.business_one.slug, 'pk': target.pk})

        with patch('pos.views.render', return_value=HttpResponse('invalid')) as mock_render:
            response = self.client.post(
                url,
                {
                    'name': 'ACME SUPPLIERS',
                    'contact_person': target.contact_person,
                    'email': target.email,
                    'phone': target.phone,
                    'address': target.address,
                    'notes': target.notes,
                    'is_active': 'on',
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('already exists for this business.', ' '.join(messages))
        target.refresh_from_db()
        self.assertEqual(target.name, 'Bravo Suppliers')
        self.assertTrue(
            Supplier.objects.filter(pk=existing.pk, business=self.business_one, name='Acme Suppliers').exists()
        )

    def test_supplier_statement_invalid_dates_redirect_safely(self):
        supplier = Supplier.objects.create(business=self.business_one, name='Statement Vendor')
        url = reverse(
            'supplier_statement',
            kwargs={'slug': self.business_one.slug, 'supplier_id': supplier.id},
        )

        response_invalid_format = self.client.get(url, {'start_date': 'not-a-date'})
        self.assertEqual(response_invalid_format.status_code, 302)
        self.assertTrue(response_invalid_format['Location'].endswith(url))

        response_bad_range = self.client.get(
            url,
            {'start_date': '2026-04-10', 'end_date': '2026-04-01'},
        )
        self.assertEqual(response_bad_range.status_code, 302)
        self.assertTrue(response_bad_range['Location'].endswith(url))

    def test_create_payment_allows_partially_received_purchase(self):
        supplier = Supplier.objects.create(business=self.business_one, name='Partial Receipt Supplier')
        payment_method = self._ensure_active_payment_method(self.business_one)
        Purchase.objects.create(
            business=self.business_one,
            supplier=supplier,
            status='partially_received',
            total_amount=Decimal('150.00'),
        )

        url = reverse(
            'create_payment',
            kwargs={'slug': self.business_one.slug, 'supplier_id': supplier.id},
        )

        with patch('pos.email_service.EmailService.send_payment_confirmation', return_value=True):
            response = self.client.post(
                url,
                {
                    'amount': '50.00',
                    'payment_date': '2026-04-05',
                    'payment_method': str(payment_method.id),
                    'reference_number': 'TXN-12345',
                    'notes': 'partial receipt payment',
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response['Location'].endswith(
                reverse(
                    'supplier_payments',
                    kwargs={'slug': self.business_one.slug, 'supplier_id': supplier.id},
                )
            )
        )
        payment = SupplierPayment.objects.get(supplier=supplier)
        self.assertEqual(payment.amount, Decimal('50.00'))
        self.assertEqual(payment.payment_method_id, payment_method.id)