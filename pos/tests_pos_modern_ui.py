"""
Unit and Integration Tests for Modern POS Selling Point UI & Features:
- Dual View (Touch Tile Grid & List)
- Multi-Cart Concurrent Tabs
- 1-Tap Fast-Tender Checkout
- Customer-Facing Display (CFD)
- Keyboard Maestro Shortcuts and Audio Synthesizer
"""

from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from pos.models import (
    Business, BusinessSettings, BusinessMembership, Branch, Product, Category, BranchStock,
    PaymentMethod, Sale, SaleItem, SalePayment, POSSession
)


class POSModernUITests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='cashier_one',
            password='pospassword123',
            email='cashier@store.com'
        )
        self.business = Business.objects.create(
            name='Modern Retail Superstore',
            owner=self.user,
            is_active=True
        )
        BusinessMembership.objects.create(
            user=self.user,
            business=self.business,
            role='owner'
        )
        self.settings, _ = BusinessSettings.objects.get_or_create(business=self.business)
        self.settings.mpesa_enabled = True
        self.settings.mpesa_shortcode = '247247'
        self.settings.mpesa_type = 'paybill'
        self.settings.mpesa_account_reference = 'RETAIL-01'
        self.settings.vat_rate = Decimal('16.00')
        self.settings.save()
        self.branch = Branch.objects.create(
            business=self.business,
            name='Nairobi CBD Store',
            is_default=True,
            is_active=True
        )
        self.category = Category.objects.create(
            business=self.business,
            name='Beverages'
        )
        self.product = Product.objects.create(
            business=self.business,
            category=self.category,
            name='Fresh Apple Juice 1L',
            product_code='JUICE-APL-1L',
            barcode='616110998877',
            cost_price=Decimal('120.00'),
            unit_price=Decimal('180.00'),
            stock_quantity=Decimal('50.000'),
            is_active=True
        )
        BranchStock.objects.create(
            branch=self.branch,
            product=self.product,
            quantity=Decimal('50.000'),
            average_cost=Decimal('120.00')
        )

        # Payment Methods
        self.cash_method, _ = PaymentMethod.objects.get_or_create(
            business=self.business,
            code='CASH',
            defaults={'name': 'Cash', 'is_active': True}
        )
        self.mpesa_method, _ = PaymentMethod.objects.get_or_create(
            business=self.business,
            code='MPESA',
            defaults={'name': 'M-Pesa', 'is_active': True}
        )

        # Open POS session for cashier
        self.session = POSSession.objects.create(
            business=self.business,
            cashier=self.user,
            opened_by=self.user,
            opening_cash=Decimal('1000.00'),
            status='open'
        )

        # Log in
        self.client.login(username='cashier_one', password='pospassword123')

        # Store session in client
        session = self.client.session
        session['active_business_id'] = self.business.id
        session['pos_session_id'] = self.session.id
        session.save()

    def test_customer_display_view_loads_successfully(self):
        """Customer-Facing Display (CFD) page renders with 200 OK, customized store name and logo."""
        response = self.client.get(reverse('customer_display', kwargs={'slug': self.business.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/customer_display.html')

        content = response.content.decode('utf-8')
        # Check Business name & Lipa na M-Pesa
        self.assertIn('Modern Retail Superstore', content)
        self.assertIn('Welcome to Modern Retail Superstore', content)
        self.assertIn('welcomeLogoContainer', content)
        self.assertIn('welcomeStoreName', content)
        self.assertIn('thankYouStoreName', content)
        self.assertIn('cfdBusinessName', content)
        self.assertIn('Lipa na M-Pesa', content)
        self.assertIn('247247', content)
        self.assertIn('RETAIL-01', content)

        # Check Live BroadcastChannel synchronization script
        self.assertIn('pos_customer_display_sync', content)
        self.assertIn('BroadcastChannel', content)
        self.assertIn('totalDueDisplay', content)
        self.assertIn('thankYouState', content)

    def test_customer_display_default_route(self):
        """Customer-Facing Display (CFD) default /pos/customer-display/ works when session has active business."""
        response = self.client.get(reverse('customer_display'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/customer_display.html')

    def test_pos_screen_renders_modern_ui_components(self):
        """POS screen template contains Dual View switcher, Multi-Cart tabs, and 1-Tap Fast-Tender."""
        response = self.client.get(reverse('pos_screen', kwargs={'slug': self.business.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/pos_screen.html')

        content = response.content.decode('utf-8')

        # 1. Dual View Switcher & Touch Tiles
        self.assertIn('view-mode-grid-btn', content)
        self.assertIn('view-mode-list-btn', content)
        self.assertIn('products-grid', content)
        self.assertIn('products-list', content)
        self.assertIn('setProductView', content)

        # 2. Multi-Cart Concurrent Tabs
        self.assertIn('cart-tabs-nav', content)
        self.assertIn('initMultiCarts', content)
        self.assertIn('addNewMultiCart', content)
        self.assertIn('switchMultiCart', content)
        self.assertIn('closeMultiCart', content)

        # 3. 1-Tap Fast-Tender Bar
        self.assertIn('fast-tender-panel', content)
        self.assertIn('fast-quick-cash-chips', content)
        self.assertIn('btn-fast-cash', content)
        self.assertIn('btn-fast-mpesa', content)
        self.assertIn('fastTenderCash', content)
        self.assertIn('fastTenderMpesa', content)

        # 4. Web Audio Synthesizer & CFD Broadcaster
        self.assertIn('playScanBeep', content)
        self.assertIn('playErrorBeep', content)
        self.assertIn('playSuccessChime', content)
        self.assertIn('broadcastToCfd', content)
        self.assertIn('customer_display', content)

    def test_pos_screen_load_products_json(self):
        """POS lazy loader returns JSON product items including tax, bulk, category info."""
        response = self.client.get(
            reverse('pos_screen', kwargs={'slug': self.business.slug}),
            {'load_products': '1', 'offset': '0', 'limit': '20'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(len(data.get('products', [])), 1)

        prod_data = data['products'][0]
        self.assertEqual(prod_data['name'], 'Fresh Apple Juice 1L')
        self.assertEqual(prod_data['product_code'], 'JUICE-APL-1L')
        self.assertEqual(float(prod_data['unit_price']), 180.00)
        self.assertEqual(float(prod_data['stock_quantity']), 50.00)
        self.assertEqual(prod_data['category_name'], 'Beverages')

    def test_fast_tender_cash_checkout_execution(self):
        """1-Tap Fast-Tender Cash checkout creates completed sale and updates stock."""
        # 2 units of juice = 360 KES, customer paid 500 KES note, 140 KES change
        sale_data = {
            'items': [f"{self.product.id},2,180.00,"],
            'payments': [f"{self.cash_method.id},360.00,Cash Fast-Tender"],
            'amount_paid': '500.00',
            'change_given': '140.00',
            'discount_type': 'percentage',
            'discount_value': '0',
            'notes': 'Fast tender sale'
        }

        response = self.client.post(
            reverse('complete_sale', kwargs={'slug': self.business.slug}),
            sale_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # Check sale record
        sale = Sale.objects.filter(business=self.business).latest('created_at')
        self.assertEqual(sale.total, Decimal('360.00'))
        self.assertEqual(sale.amount_paid, Decimal('500.00'))
        self.assertEqual(sale.change_given, Decimal('140.00'))

        # Check sale item
        sale_item = SaleItem.objects.get(sale=sale)
        self.assertEqual(sale_item.product, self.product)
        self.assertEqual(sale_item.quantity, Decimal('2.000'))
        self.assertEqual(sale_item.unit_price, Decimal('180.00'))

        # Check payment record
        sale_payment = SalePayment.objects.get(sale=sale)
        self.assertEqual(sale_payment.payment_method, self.cash_method)
        self.assertEqual(sale_payment.amount, Decimal('360.00'))

        # Check branch stock was decremented from 50 to 48
        b_stock = BranchStock.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(b_stock.quantity, Decimal('48.000'))
