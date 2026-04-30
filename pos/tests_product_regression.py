from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient

from pos.models import Business, BusinessMembership, Category, Product


class ProductRegressionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='product-owner', password='pass123!')
        self.api_user = User.objects.create_user(username='product-api-user', password='pass123!')

        self.business_one = Business.objects.create(
            name='Products One',
            slug='products-one',
            owner=self.owner,
        )
        self.business_two = Business.objects.create(
            name='Products Two',
            slug='products-two',
            owner=self.owner,
        )

        BusinessMembership.objects.create(user=self.owner, business=self.business_one, role='owner')
        BusinessMembership.objects.create(user=self.owner, business=self.business_two, role='owner')
        BusinessMembership.objects.create(user=self.api_user, business=self.business_one, role='owner')

        self.api_client = APIClient()
        self.api_client.force_authenticate(user=self.api_user)

    def test_product_api_queryset_is_scoped_by_active_memberships(self):
        product_one = Product.objects.create(
            business=self.business_one,
            name='Scoped Product One',
            product_code='SP-001',
            cost_price=Decimal('10.00'),
            unit_price=Decimal('15.00'),
        )
        Product.objects.create(
            business=self.business_two,
            name='Scoped Product Two',
            product_code='SP-002',
            cost_price=Decimal('20.00'),
            unit_price=Decimal('30.00'),
        )

        response = self.api_client.get(reverse('product-list'))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        results = payload.get('results', payload)
        returned_ids = {entry['id'] for entry in results}

        self.assertIn(product_one.id, returned_ids)
        self.assertEqual(len(returned_ids), 1)

    def test_product_api_create_binds_membership_business(self):
        response = self.api_client.post(
            reverse('product-list'),
            {
                'name': 'API Created Product',
                'product_code': 'API-001',
                'cost_price': '40.00',
                'unit_price': '55.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(name='API Created Product')
        self.assertEqual(product.business_id, self.business_one.id)

    def test_product_api_create_rejects_foreign_business_category(self):
        foreign_category = Category.objects.create(business=self.business_two, name='Foreign Category')

        response = self.api_client.post(
            reverse('product-list'),
            {
                'name': 'Cross Business Category Product',
                'product_code': 'API-002',
                'category': foreign_category.id,
                'cost_price': '12.00',
                'unit_price': '18.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.json())
        self.assertFalse(Product.objects.filter(name='Cross Business Category Product').exists())

    def test_product_api_create_rejects_barcode_collision_with_unit_barcode(self):
        Product.objects.create(
            business=self.business_one,
            name='Existing Unit Barcode Product',
            product_code='API-003',
            unit_barcode='BAR-001',
            cost_price=Decimal('11.00'),
            unit_price=Decimal('14.00'),
        )

        response = self.api_client.post(
            reverse('product-list'),
            {
                'name': 'Collision Barcode Product',
                'product_code': 'API-004',
                'barcode': 'BAR-001',
                'cost_price': '13.00',
                'unit_price': '17.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('barcode', response.json())
        self.assertFalse(Product.objects.filter(name='Collision Barcode Product').exists())


class ProductFormValidationRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='product-form-user', password='pass123!')
        self.business = Business.objects.create(
            name='Product Form Business',
            slug='product-form-business',
            owner=self.user,
        )
        BusinessMembership.objects.create(user=self.user, business=self.business, role='owner')

        self.client.force_login(self.user)

    def _create_url(self):
        return reverse('product_create', kwargs={'slug': self.business.slug})

    def _edit_url(self, product):
        return reverse('product_edit', kwargs={'slug': self.business.slug, 'pk': product.pk})

    def _base_payload(self):
        return {
            'name': 'Validation Product',
            'product_code': 'VAL-001',
            'cost_price': '100.00',
            'unit_price': '150.00',
            'is_active': '1',
            'tax_class': 'standard',
        }

    def test_create_ignores_minimum_price_field(self):
        payload = self._base_payload()
        payload['product_code'] = 'VAL-005'
        payload['minimum_price'] = '200.00'

        response = self.client.post(self._create_url(), payload)

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(business=self.business, product_code='VAL-005')
        self.assertIsNone(product.minimum_price)

    def test_create_rejects_partial_bulk_configuration(self):
        payload = self._base_payload()
        payload['unit_barcode'] = 'BULK-UNIT-001'

        with patch('pos.views.render', return_value=HttpResponse('invalid')) as mock_render:
            response = self.client.post(self._create_url(), payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        self.assertFalse(Product.objects.filter(business=self.business, product_code='VAL-001').exists())
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Bulk Unit Name, Units per Bulk, and Bulk Unit Price are all required when using bulk configuration.', messages)

    def test_create_normalizes_excise_rate_when_not_excisable(self):
        payload = self._base_payload()
        payload['product_code'] = 'VAL-002'
        payload['is_excisable'] = '0'
        payload['excise_rate'] = '19.50'

        response = self.client.post(self._create_url(), payload)

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(business=self.business, product_code='VAL-002')
        self.assertFalse(product.is_excisable)
        self.assertEqual(product.excise_rate, Decimal('0'))

    def test_create_accepts_legacy_product_type_post_field(self):
        payload = self._base_payload()
        payload['product_code'] = 'VAL-004'
        payload['product_type'] = 'service'

        response = self.client.post(self._create_url(), payload)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(business=self.business, product_code='VAL-004').exists())

    def test_edit_rejects_bulk_discount_below_minimum_price(self):
        product = Product.objects.create(
            business=self.business,
            name='Existing Validation Product',
            product_code='VAL-003',
            cost_price=Decimal('50.00'),
            unit_price=Decimal('75.00'),
        )

        payload = {
            'name': product.name,
            'product_code': product.product_code,
            'cost_price': '50.00',
            'unit_price': '75.00',
            'minimum_price': '60.00',
            'bulk_unit_name': 'Carton',
            'bulk_unit_quantity': '12',
            'bulk_unit_price': '700.00',
            'bulk_discount_price': '55.00',
            'is_active': '1',
            'tax_class': 'standard',
        }

        with patch('pos.views.render', return_value=HttpResponse('invalid')) as mock_render:
            response = self.client.post(self._edit_url(product), payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        product.refresh_from_db()
        self.assertIsNone(product.bulk_discount_price)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('Bulk discount price cannot be below the minimum price.', messages)
