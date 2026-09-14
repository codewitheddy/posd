from decimal import Decimal
import io
import json
from PIL import Image

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache

from pos.models import (
    Business, BusinessSettings, BusinessMembership, Branch, Product, Category, Sale, PaymentMethod
)
from pos.sync_views import emit_sync_event, CACHE_SYNC_PREFIX


class StoreSettingsSyncTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='admin_settings', email='admin@example.com', password='password123'
        )
        self.client.login(username='admin_settings', password='password123')

        self.business = Business.objects.create(
            name='Test Mega Store',
            slug='test-mega-store',
            owner=self.user,
            phone='+254711000111',
            email='store@example.com',
            address='123 Retail Lane, Nairobi',
            tax_id='P051234567Z'
        )

        self.membership = BusinessMembership.objects.create(
            user=self.user,
            business=self.business,
            role='owner',
            is_active=True
        )

        self.branch = Branch.objects.create(
            business=self.business,
            name='Main Retail Outlet',
            code='OUT-01',
            address='123 Retail Lane',
            is_hq=True
        )

        self.settings = BusinessSettings.get_settings(self.business)
        self.settings.business_name = 'Test Mega Store'
        self.settings.currency_symbol = 'KES'
        self.settings.vat_rate = Decimal('16.00')
        self.settings.vat_enabled = True
        self.settings.save()

    def _create_test_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(200, 200), color=(25, 135, 84, 255))
        image.save(file, 'png')
        file.name = 'test_store_logo.png'
        file.seek(0)
        return SimpleUploadedFile(
            file.name,
            file.read(),
            content_type='image/png'
        )

    def test_context_processor_injects_business_settings(self):
        """Verify business_context context processor delivers business_settings & store_settings"""
        response = self.client.get(reverse('dashboard', kwargs={'slug': self.business.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertIn('business_settings', response.context)
        self.assertIn('store_settings', response.context)
        self.assertEqual(response.context['business_settings'].id, self.settings.id)
        self.assertEqual(response.context['business_settings'].get_business_name(), 'Test Mega Store')

    def test_settings_form_updates_and_syncs_with_business_model(self):
        """POST to business_settings updates both BusinessSettings and parent Business model"""
        test_logo = self._create_test_image()
        url = reverse('business_settings', kwargs={'slug': self.business.slug})
        post_data = {
            'business_name': 'Marid Supermarket HQ',
            'business_address': '456 Commercial Ave, Nairobi',
            'business_phone': '+254722999888',
            'business_email': 'contact@maridsupermarket.com',
            'business_website': 'https://maridsupermarket.com',
            'tax_id': 'P059998887X',
            'vat_rate': '16.00',
            'vat_enabled': 'on',
            'currency_symbol': 'KES',
            'currency_position': 'before',
            'receipt_header': 'Welcome to Marid Supermarket',
            'receipt_footer': 'Thank you for shopping with us!',
            'thermal_receipt_width': '80',
            'thermal_font_size': 'medium',
            'thermal_print_logo': 'on',
            'mpesa_enabled': 'on',
            'mpesa_type': 'till',
            'mpesa_shortcode': '123456',
            'logo': test_logo,
        }

        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Reload from database
        self.settings.refresh_from_db()
        self.business.refresh_from_db()

        # Verify BusinessSettings updated
        self.assertEqual(self.settings.business_name, 'Marid Supermarket HQ')
        self.assertEqual(self.settings.business_address, '456 Commercial Ave, Nairobi')
        self.assertEqual(self.settings.business_phone, '+254722999888')
        self.assertEqual(self.settings.business_email, 'contact@maridsupermarket.com')
        self.assertEqual(self.settings.tax_id, 'P059998887X')
        self.assertEqual(self.settings.receipt_header, 'Welcome to Marid Supermarket')
        self.assertEqual(self.settings.receipt_footer, 'Thank you for shopping with us!')
        self.assertTrue(self.settings.mpesa_enabled)
        self.assertEqual(self.settings.mpesa_shortcode, '123456')
        self.assertTrue(bool(self.settings.logo))

        # Verify parent Business model synchronized
        self.assertEqual(self.business.name, 'Marid Supermarket HQ')
        self.assertEqual(self.business.address, '456 Commercial Ave, Nairobi')
        self.assertEqual(self.business.phone, '+254722999888')
        self.assertEqual(self.business.email, 'contact@maridsupermarket.com')
        self.assertEqual(self.business.tax_id, 'P059998887X')

    def test_logo_removal(self):
        """Checking remove_logo removes the logo from settings"""
        test_logo = self._create_test_image()
        self.settings.logo = test_logo
        self.settings.save()
        self.assertTrue(bool(self.settings.logo))

        url = reverse('business_settings', kwargs={'slug': self.business.slug})
        post_data = {
            'business_name': 'Marid Supermarket HQ',
            'remove_logo': 'true',
            'vat_rate': '16.00',
            'currency_symbol': 'KES',
        }
        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        self.settings.refresh_from_db()
        self.assertFalse(bool(self.settings.logo))

    def test_catalog_sync_endpoint_returns_store_settings(self):
        """GET /pos/api/sync/catalog/ packages store_settings in JSON payload"""
        self.settings.business_name = 'Sync Test Store'
        self.settings.mpesa_enabled = True
        self.settings.mpesa_shortcode = '789012'
        self.settings.save()

        response = self.client.get(reverse('pos_sync_catalog'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('store_settings', data)
        self.assertEqual(data['store_settings']['business_name'], 'Sync Test Store')
        self.assertEqual(data['store_settings']['currency_symbol'], 'KES')
        self.assertEqual(data['store_settings']['mpesa_shortcode'], '789012')
        self.assertTrue(data['store_settings']['mpesa_enabled'])

    def test_sync_event_emission_for_settings_updated(self):
        """emit_sync_event records settings_updated in rolling cache bus"""
        event = emit_sync_event('settings_updated', {
            'business_name': 'Live Sync Brand',
            'currency_symbol': 'USD',
        }, business_id=self.business.id)

        self.assertEqual(event['type'], 'settings_updated')
        self.assertEqual(event['payload']['business_name'], 'Live Sync Brand')

        # Check rolling cache buffer
        cache_key = f"{CACHE_SYNC_PREFIX}{self.business.id}"
        events = cache.get(cache_key)
        self.assertIsNotNone(events)
        self.assertTrue(any(e['type'] == 'settings_updated' for e in events))

    def test_thermal_receipt_renders_custom_settings(self):
        """Thermal receipt template renders store name, header, and footer from settings"""
        self.settings.business_name = 'Marid Prime Grocers'
        self.settings.receipt_header = '*** VIP CUSTOMER RECEIPT ***'
        self.settings.receipt_footer = '*** NO REFUND WITHOUT RECEIPT ***'
        self.settings.save()

        # Create sample sale
        sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.user,
            invoice_number='INV-TEST-001',
            subtotal=Decimal('100.00'),
            vat_rate=Decimal('16.00'),
            vat_amount=Decimal('16.00'),
            total=Decimal('116.00'),
            amount_paid=Decimal('116.00')
        )

        response = self.client.get(reverse('thermal_receipt', kwargs={'slug': self.business.slug, 'pk': sale.pk}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('MARID PRIME GROCERS', content)
        self.assertIn('*** VIP CUSTOMER RECEIPT ***', content)
        self.assertIn('*** NO REFUND WITHOUT RECEIPT ***', content)
