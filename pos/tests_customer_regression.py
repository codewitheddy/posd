from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from pos.models import Business, BusinessMembership, Customer, CustomerPayment, LoyaltyTransaction


class CustomerRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='customer-owner', password='pass123!')
        self.business = Business.objects.create(
            name='Customer Business',
            slug='customer-business',
            owner=self.user,
        )
        BusinessMembership.objects.create(user=self.user, business=self.business, role='owner')

        self.other_user = User.objects.create_user(username='other-owner', password='pass123!')
        self.other_business = Business.objects.create(
            name='Other Customer Business',
            slug='other-customer-business',
            owner=self.other_user,
        )
        BusinessMembership.objects.create(user=self.other_user, business=self.other_business, role='owner')

    def test_customer_api_list_scopes_to_membership_business(self):
        Customer.objects.create(
            business=self.business,
            name='Allowed Customer',
            phone='0700000001',
            email='allowed@example.com',
        )
        Customer.objects.create(
            business=self.other_business,
            name='Leaked Customer',
            phone='0700000002',
            email='leaked@example.com',
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.get('/api/v1/customers/')

        self.assertEqual(response.status_code, 200)
        names = [row['name'] for row in response.data.get('results', [])]
        self.assertIn('Allowed Customer', names)
        self.assertNotIn('Leaked Customer', names)

    def test_customer_api_create_assigns_business_from_membership(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        payload = {
            'name': 'API Customer',
            'phone': '0711002200',
            'email': 'api-customer@example.com',
        }

        response = client.post('/api/v1/customers/', payload, format='json')

        self.assertEqual(response.status_code, 201)
        customer = Customer.objects.get(name='API Customer')
        self.assertEqual(customer.business_id, self.business.id)

    def test_customer_create_rejects_negative_credit_limit(self):
        self.client.force_login(self.user)
        url = reverse('customer_create', kwargs={'slug': self.business.slug})

        payload = {
            'name': 'Bad Credit Customer',
            'phone': '0722003300',
            'email': 'bad-credit@example.com',
            'customer_type': 'regular',
            'credit_limit': '-100',
            'is_active': 'on',
        }
        with patch('pos.views.render', return_value=HttpResponse('invalid')):
            response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(name='Bad Credit Customer').exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Credit limit cannot be negative.', messages)

    def test_customer_list_status_filter_excludes_inactive(self):
        self.client.force_login(self.user)
        Customer.objects.create(
            business=self.business,
            name='Active Customer',
            phone='0700100100',
            is_active=True,
        )
        Customer.objects.create(
            business=self.business,
            name='Inactive Customer',
            phone='0700100101',
            is_active=False,
        )

        url = reverse('customer_list', kwargs={'slug': self.business.slug})
        with patch('pos.views.render', return_value=HttpResponse('ok')) as mock_render:
            response = self.client.get(url, {'status': 'active'})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        context = mock_render.call_args[0][2]
        names = [c.name for c in context['customers']]
        self.assertIn('Active Customer', names)
        self.assertNotIn('Inactive Customer', names)

    @override_settings(ENFORCE_UNIQUE_CUSTOMER_PHONE=True)
    def test_customer_create_rejects_duplicate_phone_when_enforced(self):
        self.client.force_login(self.user)
        Customer.objects.create(
            business=self.business,
            name='Existing Customer',
            phone='0799001100',
            email='existing@example.com',
        )

        url = reverse('customer_create', kwargs={'slug': self.business.slug})
        payload = {
            'name': 'Duplicate Phone Customer',
            'phone': '0799001100',
            'email': 'dup@example.com',
            'customer_type': 'regular',
            'credit_limit': '0',
            'is_active': 'on',
        }
        with patch('pos.views.render', return_value=HttpResponse('invalid')):
            response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(name='Duplicate Phone Customer').exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('already uses this phone number' in m for m in messages))

    @override_settings(ENFORCE_UNIQUE_CUSTOMER_PHONE=True)
    def test_customer_create_rejects_duplicate_phone_across_normalized_formats(self):
        self.client.force_login(self.user)
        Customer.objects.create(
            business=self.business,
            name='Existing Customer',
            phone='+254799001100',
            email='existing@example.com',
        )

        url = reverse('customer_create', kwargs={'slug': self.business.slug})
        payload = {
            'name': 'Normalized Duplicate',
            'phone': '0799001100',
            'email': 'normalized-dup@example.com',
            'customer_type': 'regular',
            'credit_limit': '0',
            'is_active': 'on',
        }
        with patch('pos.views.render', return_value=HttpResponse('invalid')):
            response = self.client.post(url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(name='Normalized Duplicate').exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('already uses this phone number' in m for m in messages))

    @override_settings(ENFORCE_UNIQUE_CUSTOMER_PHONE=True)
    def test_customer_api_rejects_duplicate_phone_when_enforced(self):
        Customer.objects.create(
            business=self.business,
            name='API Existing',
            phone='+254788002200',
            email='api-existing@example.com',
        )

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.post('/api/v1/customers/', {
            'name': 'API Duplicate',
            'phone': '0788002200',
            'email': 'api-dup@example.com',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.data)

    def test_customer_detail_lists_merge_candidates_by_normalized_phone(self):
        self.client.force_login(self.user)
        target = Customer.objects.create(
            business=self.business,
            name='Target Customer',
            phone='0700123456',
            email='target@example.com',
        )
        source = Customer.objects.create(
            business=self.business,
            name='Source Customer',
            phone='+254700123456',
            email='source@example.com',
        )

        url = reverse('customer_detail', kwargs={'slug': self.business.slug, 'pk': target.pk})
        with patch('pos.crm_views.render', return_value=HttpResponse('ok')) as mock_render:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        context = mock_render.call_args[0][2]
        merge_candidates = context['merge_candidates']
        self.assertEqual(len(merge_candidates), 1)
        self.assertEqual(merge_candidates[0]['customer'].pk, source.pk)

    def test_customer_merge_moves_balances_and_history(self):
        self.client.force_login(self.user)
        target = Customer.objects.create(
            business=self.business,
            name='Target Customer',
            phone='0700123456',
            email='target@example.com',
            loyalty_points=10,
            lifetime_points=20,
            total_purchases=Decimal('1000.00'),
            visit_count=2,
            credit_limit=Decimal('500.00'),
            credit_balance=Decimal('100.00'),
            tags='vip',
        )
        source = Customer.objects.create(
            business=self.business,
            name='Source Customer',
            phone='0700123456',
            email='source@example.com',
            loyalty_points=5,
            lifetime_points=15,
            total_purchases=Decimal('250.00'),
            visit_count=1,
            credit_limit=Decimal('800.00'),
            credit_balance=Decimal('60.00'),
            tags='duplicate',
        )
        LoyaltyTransaction.objects.create(
            customer=source,
            transaction_type='adjust',
            points=5,
            amount=Decimal('0.00'),
            description='Seed source txn',
            created_by=self.user,
        )
        CustomerPayment.objects.create(
            business=self.business,
            customer=source,
            amount=Decimal('20.00'),
            recorded_by=self.user,
        )

        response = self.client.post(
            reverse('customer_merge', kwargs={'slug': self.business.slug, 'pk': target.pk}),
            {'source_customer_id': str(source.pk)},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        source.refresh_from_db()

        self.assertEqual(target.loyalty_points, 15)
        self.assertEqual(target.lifetime_points, 35)
        self.assertEqual(target.total_purchases, Decimal('1250.00'))
        self.assertEqual(target.visit_count, 3)
        self.assertEqual(target.credit_limit, Decimal('800.00'))
        self.assertEqual(target.credit_balance, Decimal('140.00'))
        self.assertFalse(source.is_active)
        self.assertEqual(source.loyalty_points, 0)
        self.assertEqual(source.credit_balance, Decimal('0.00'))
        self.assertEqual(LoyaltyTransaction.objects.filter(customer=target).count(), 1)
        self.assertEqual(CustomerPayment.objects.filter(customer=target).count(), 1)

    def test_customer_merge_rejects_different_normalized_phone(self):
        self.client.force_login(self.user)
        target = Customer.objects.create(
            business=self.business,
            name='Target Customer',
            phone='0700123456',
        )
        source = Customer.objects.create(
            business=self.business,
            name='Different Customer',
            phone='0711998877',
        )

        response = self.client.post(
            reverse('customer_merge', kwargs={'slug': self.business.slug, 'pk': target.pk}),
            {'source_customer_id': str(source.pk)},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('same normalized phone number' in m for m in messages))
