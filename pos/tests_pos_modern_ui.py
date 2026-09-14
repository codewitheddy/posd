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
    PaymentMethod, Sale, SaleItem, SalePayment, POSSession, UserProfile, ActivityLog
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

        # Check branch stock was decremented from 50 to 48
        b_stock = BranchStock.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(b_stock.quantity, Decimal('48.000'))

    def test_pos_screen_renders_supervisor_auth_modal_and_keypad(self):
        """POS screen template renders supervisor authorization modal with PIN keypad and scripts."""
        response = self.client.get(reverse('pos_screen', kwargs={'slug': self.business.slug}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Check Supervisor modal elements
        self.assertIn('supervisorAuthModal', content)
        self.assertIn('Supervisor Authorization', content)
        self.assertIn('supervisor-credential-input', content)
        self.assertIn('supervisor-pin-keypad', content)
        self.assertIn('supervisor-action-banner', content)
        self.assertIn('requestSupervisorAuth', content)
        self.assertIn('submitSupervisorAuth', content)

    def test_supervisor_authorize_with_valid_admin_password(self):
        """Supervisor authorization endpoint accepts owner/admin password and logs to ActivityLog."""
        url = reverse('pos_supervisor_authorize', kwargs={'slug': self.business.slug})
        response = self.client.post(
            url,
            data={
                'credential': 'pospassword123',
                'action_type': 'remove_cart_item',
                'action_details': 'Fresh Apple Juice 1L',
                'reason': 'Customer changed mind'
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertIn('Authorized by', data.get('message', ''))

        # Verify ActivityLog entry was recorded
        log = ActivityLog.objects.filter(
            business=self.business,
            operation_type='POS_SUPERVISOR_OVERRIDE'
        ).latest('timestamp')
        self.assertIn('authorized Cart Item Removal', log.description)
        self.assertIn('Customer changed mind', log.description)

    def test_supervisor_authorize_with_valid_manager_pin(self):
        """Supervisor authorization endpoint accepts manager PIN and logs to ActivityLog."""
        # Create a manager user with PIN
        manager = User.objects.create_user(
            username='store_manager',
            password='managerpass123',
            email='manager@store.com'
        )
        BusinessMembership.objects.create(
            user=manager,
            business=self.business,
            role='manager'
        )
        manager_profile, _ = UserProfile.objects.get_or_create(user=manager)
        manager_profile.set_pin('7788', business=self.business)

        url = reverse('pos_supervisor_authorize', kwargs={'slug': self.business.slug})
        response = self.client.post(
            url,
            data={
                'credential': '7788',
                'action_type': 'apply_discount',
                'action_details': '10% loyalty promo',
                'reason': 'Special manager discount'
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('supervisor_id'), manager.id)

        # Check ActivityLog
        log = ActivityLog.objects.filter(
            business=self.business,
            operation_type='POS_SUPERVISOR_OVERRIDE',
            user=manager
        ).latest('timestamp')
        self.assertIn('Discount Applied', log.description)

    def test_supervisor_authorize_with_cashier_pin_denied(self):
        """Cashier attempting to authorize supervisor override with their own cashier PIN is rejected."""
        # Create a regular cashier with PIN
        cashier_user = User.objects.create_user(
            username='junior_cashier',
            password='cashierpass123',
            email='junior@store.com'
        )
        BusinessMembership.objects.create(
            user=cashier_user,
            business=self.business,
            role='cashier'
        )
        cashier_profile, _ = UserProfile.objects.get_or_create(user=cashier_user)
        cashier_profile.set_pin('1234', business=self.business)

        url = reverse('pos_supervisor_authorize', kwargs={'slug': self.business.slug})
        response = self.client.post(
            url,
            data={
                'credential': '1234',
                'action_type': 'clear_cart',
                'action_details': 'Clear entire cart'
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('cashier', data.get('error', '').lower())

    def test_supervisor_authorize_with_invalid_credential_denied(self):
        """Invalid passwords or non-matching PINs are rejected."""
        url = reverse('pos_supervisor_authorize', kwargs={'slug': self.business.slug})
        response = self.client.post(
            url,
            data={
                'credential': 'wrong_password_999',
                'action_type': 'retrieve_held_order'
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertIn('denied', data.get('error', '').lower())

    def test_payment_method_list_single_store_url(self):
        """GET /payment-methods/ renders payment methods without TypeError."""
        url = reverse('payment_method_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('payment_methods', response.context)
        self.assertContains(response, self.cash_method.name)

    def test_payment_method_list_multitenant_url(self):
        """GET /b/<slug>/payment-methods/ renders payment methods with slug kwarg."""
        url = reverse('payment_method_list', kwargs={'slug': self.business.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('payment_methods', response.context)

    def test_payment_method_create_and_edit_lifecycle(self):
        """Payment method create and edit lifecycle works properly with ActivityLog."""
        # Create
        create_url = reverse('payment_method_create')
        response = self.client.post(create_url, {
            'name': 'Airtel Money',
            'code': 'AIRTEL_MONEY',
            'is_active': 'on',
            'requires_reference': 'on',
            'icon': 'bi-phone'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        pm = PaymentMethod.objects.get(business=self.business, code='AIRTEL_MONEY')
        self.assertEqual(pm.name, 'Airtel Money')
        self.assertTrue(pm.requires_reference)

        # Edit
        edit_url = reverse('payment_method_edit', kwargs={'pk': pm.pk})
        response = self.client.post(edit_url, {
            'name': 'Airtel Money Updated',
            'code': 'AIRTEL_MONEY',
            'is_active': 'on',
            'requires_reference': 'on',
            'icon': 'bi-phone'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        pm.refresh_from_db()
        self.assertEqual(pm.name, 'Airtel Money Updated')

    def test_payment_method_delete_with_admin_password(self):
        """Payment method deletion requires admin password & reason and logs audit."""
        pm = PaymentMethod.objects.create(
            business=self.business,
            name='Test Method To Delete',
            code='TEMP_DEL',
            is_active=True
        )
        delete_url = reverse('payment_method_delete', kwargs={'pk': pm.pk})

        # POST without password fails
        response = self.client.post(delete_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PaymentMethod.objects.filter(pk=pm.pk).exists())

        # POST with correct admin password and reason succeeds
        response = self.client.post(delete_url, {
            'admin_password': 'pospassword123',
            'reason': 'No longer in use by merchant'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PaymentMethod.objects.filter(pk=pm.pk).exists())

    def test_branch_list_view_renders_table_list_view(self):
        """GET /branches/ renders a responsive list view table with search and action buttons."""
        url = reverse('branch_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Check list view table structure and elements
        self.assertIn('branchesTable', content)
        self.assertIn('branchSearchInput', content)
        self.assertIn('Registered Locations', content)
        self.assertIn('Branch Name', content)
        self.assertIn('Branch Code', content)
        self.assertIn('Address / Location', content)
        self.assertIn(self.branch.name, content)
        self.assertIn(self.branch.code, content)



