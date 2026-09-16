"""
Automated Test Suite for Front Office / Back Office Separation and Real-Time Sync Engine.
Verifies role isolation, Server-Sent Events / Polling endpoints, product catalog caching,
and offline checkout synchronization.
"""
from decimal import Decimal
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.cache import cache

from pos.models import (
    Business, Branch, BranchStock, BusinessMembership, UserProfile,
    Product, Category, Sale, SaleItem, PaymentMethod
)
from pos.sync_views import emit_sync_event, CACHE_SYNC_PREFIX


class FrontBackOfficeSeparationAndSyncTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

        # Create Admin
        self.admin_user = User.objects.create_superuser(
            username="syncadmin",
            email="admin@testsync.com",
            password="adminpassword123",
        )

        # Create Business & Branch
        self.business = Business.objects.create(
            name="Test Store Sync",
            slug="test-sync",
            owner=self.admin_user,
            is_active=True,
        )
        self.branch = Branch.objects.create(
            business=self.business,
            name="Main Register Branch",
            code="REG01",
            is_default=True,
            is_active=True,
        )
        BusinessMembership.objects.create(
            user=self.admin_user,
            business=self.business,
            role='owner',
            is_active=True,
        )

        # Create Cashier
        self.cashier_user = User.objects.create_user(
            username="synccashier",
            email="cashier@testsync.com",
            password="cashierpassword123",
        )
        BusinessMembership.objects.create(
            user=self.cashier_user,
            business=self.business,
            role='cashier',
            is_active=True,
        )
        profile, _ = UserProfile.objects.get_or_create(user=self.cashier_user)
        profile.set_pin('7788', business=self.business)

        # Create Sample Category & Products
        self.category = Category.objects.create(
            business=self.business,
            name="Snacks",
        )
        self.product1 = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Potato Crisps",
            barcode="8901234567890",
            product_code="SNK-001",
            unit_price=Decimal("150.00"),
            cost_price=Decimal("100.00"),
            stock_quantity=50,
            is_active=True,
        )
        BranchStock.objects.create(
            branch=self.branch,
            product=self.product1,
            quantity=Decimal("50.000"),
            average_cost=Decimal("100.00")
        )
        self.payment_method = PaymentMethod.objects.create(
            business=self.business,
            name="Cash",
            code="cash",
            is_active=True,
        )

    def test_cashier_strictly_blocked_from_back_office(self):
        """Cashiers attempting to access Back Office routes must be redirected to Front Office /pos/."""
        self.client.force_login(self.cashier_user)

        back_office_urls = [
            reverse('dashboard'),
            reverse('product_list'),
            reverse('user_management_list'),
        ]

        for url in back_office_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"Cashier should be redirected from {url}")
            self.assertTrue(
                response.url.endswith('/pos/') or response.url.endswith('/pos_screen') or '/pos' in response.url,
                f"Cashier should be redirected to Front Office POS, got {response.url}"
            )

    def test_admin_allowed_in_both_back_and_front_office(self):
        """Admins must have full access to both Back Office dashboard and Front Office POS."""
        self.client.force_login(self.admin_user)

        # Back Office
        resp_bo = self.client.get(reverse('dashboard'))
        self.assertEqual(resp_bo.status_code, 200)

        # Create open POS shift session for admin
        from pos.models import POSSession
        POSSession.objects.create(
            business=self.business,
            branch=self.branch,
            opened_by=self.admin_user,
            cashier=self.admin_user,
            opening_cash=Decimal("500.00"),
            status='open',
        )

        # Front Office
        resp_fo = self.client.get(reverse('pos_screen'))
        self.assertEqual(resp_fo.status_code, 200)

    def test_products_catalog_sync_endpoint(self):
        """Front Office product catalog endpoint delivers structured JSON for client-side caching."""
        self.client.force_login(self.cashier_user)

        response = self.client.get(reverse('pos_sync_catalog'))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertGreaterEqual(data.get('count'), 1)
        
        # Verify product structure
        prods = {p['id']: p for p in data['products']}
        self.assertIn(self.product1.id, prods)
        self.assertEqual(prods[self.product1.id]['name'], "Potato Crisps")
        self.assertEqual(prods[self.product1.id]['barcode'], "8901234567890")
        self.assertEqual(prods[self.product1.id]['unit_price'], 150.00)

    def test_realtime_event_emission_on_price_change(self):
        """Changing product price in Back Office automatically emits a real-time sync event."""
        # Update product price
        self.product1.unit_price = Decimal("175.00")
        self.product1.save()

        # Check rolling buffer in cache
        events = cache.get(f"{CACHE_SYNC_PREFIX}{self.business.id}", [])
        self.assertTrue(len(events) > 0, "Sync event should be placed in cache buffer")

        latest_event = events[-1]
        self.assertEqual(latest_event['type'], 'product_updated')
        self.assertEqual(latest_event['payload']['product_id'], self.product1.id)
        self.assertEqual(latest_event['payload']['unit_price'], 175.00)

    def test_sync_polling_endpoint(self):
        """Polling endpoint returns new sync events created since timestamp."""
        self.client.force_login(self.cashier_user)

        # Emit an event
        emit_sync_event('price_updated', {'product_id': self.product1.id, 'new_price': 180.0}, business_id=self.business.id)

        response = self.client.get(reverse('pos_sync_poll'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(len(data.get('events')) >= 1)

    def test_offline_sales_batch_sync_idempotency(self):
        """Offline sales batch endpoint creates sales, items, payment and handles duplicates idempotently."""
        self.client.force_login(self.cashier_user)

        client_uuid = "test_offline_sale_uuid_12345"
        payload = {
            "sales": [
                {
                    "client_uuid": client_uuid,
                    "total": "300.00",
                    "subtotal": "300.00",
                    "tax": "0.00",
                    "items": [
                        {
                            "product_id": self.product1.id,
                            "quantity": 2,
                            "unit_price": "150.00",
                            "total": "300.00"
                        }
                    ]
                }
            ]
        }

        # 1. First sync attempt
        init_stock = self.product1.stock_quantity
        response = self.client.post(
            reverse('pos_sync_offline_sales'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('synced_count'), 1)
        self.assertEqual(data['synced'][0]['status'], 'created')

        # Verify stock deducted
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock_quantity, init_stock - 2)

        # 2. Second sync attempt with SAME client_uuid (idempotency check)
        response_duplicate = self.client.post(
            reverse('pos_sync_offline_sales'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response_duplicate.status_code, 200)
        dup_data = response_duplicate.json()
        self.assertEqual(dup_data['synced'][0]['status'], 'already_synced')

        # Verify stock was NOT deducted a second time
        self.product1.refresh_from_db()
        self.assertEqual(self.product1.stock_quantity, init_stock - 2)

    def test_multi_membership_resolves_primary_store_for_cashier(self):
        """When a cashier has multiple memberships across legacy test businesses, StoreMiddleware prioritizes active primary store."""
        from django.test import RequestFactory
        from pos.middleware import StoreMiddleware
        
        # Create a second business and membership
        other_biz = Business.objects.create(name="Old Test Biz", slug="old-test", owner=self.admin_user, is_active=True)
        BusinessMembership.objects.create(user=self.cashier_user, business=other_biz, role='cashier', is_active=True)

        factory = RequestFactory()
        request = factory.get('/pos/')
        request.user = self.cashier_user
        
        middleware = StoreMiddleware(lambda r: None)
        middleware(request)
        
        self.assertIsNotNone(request.business)
        self.assertEqual(request.business_membership.role, 'cashier')

    def test_backoffice_product_price_update_emits_sync_event_to_pos(self):
        """Updating a product in backoffice emits a real-time sync event readable by cashier polling / stream."""
        self.product1.unit_price = Decimal("180.00")
        self.product1.stock_quantity = 42
        self.product1.save()

        self.client.force_login(self.cashier_user)
        response = self.client.get(reverse('pos_sync_poll'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        matching = [e for e in data.get('events', []) if e['type'] == 'product_updated' and e['payload']['product_id'] == self.product1.id]
        self.assertTrue(len(matching) >= 1)
        self.assertEqual(matching[-1]['payload']['unit_price'], 180.00)
        self.assertEqual(matching[-1]['payload']['stock_quantity'], 42.0)

    def test_multi_branch_kra_tims_config_and_invoice_signing(self):
        """Verify KRA TIMS config resolution hierarchy across Business, Branch, and Terminal."""
        from pos.models import POSTerminal, Sale, SaleItem
        from pos.tims_service import TIMSService

        # Set up Branch 2 with dedicated KRA eTIMS settings
        branch2 = Branch.objects.create(
            business=self.business,
            name="Mombasa Branch",
            code="MSA-01",
            kra_pin="P059999999X",
            kra_branch_id="02",
            cu_number="KRAMW0020002",
            tims_enabled=True,
        )

        # Set up Counter 3 with physical ESD override
        counter3 = POSTerminal.objects.create(
            business=self.business,
            branch=branch2,
            name="Counter 3",
            terminal_code="MSA-C3",
            device_token="token_msa_c3",
            cu_number="ESD-PHYSICAL-003",
        )

        # 1. Branch 2 Config
        cfg_branch = TIMSService.get_tims_config(self.business, branch=branch2)
        self.assertEqual(cfg_branch['kra_pin'], "P059999999X")
        self.assertEqual(cfg_branch['kra_branch_id'], "02")
        self.assertEqual(cfg_branch['cu_number'], "KRAMW0020002")
        self.assertTrue(cfg_branch['enabled'])

        # 2. Counter 3 Override
        cfg_counter = TIMSService.get_tims_config(self.business, branch=branch2, terminal=counter3)
        self.assertEqual(cfg_counter['cu_number'], "ESD-PHYSICAL-003")
        self.assertEqual(cfg_counter['source'], "terminal")

        # 3. Create Sale and Sign Invoice
        sale = Sale.objects.create(
            business=self.business,
            branch=branch2,
            cashier=self.cashier_user,
            invoice_number="INV-MSA-001",
            subtotal=Decimal("258.62"),
            vat_rate=Decimal("16.00"),
            vat_amount=Decimal("41.38"),
            total=Decimal("300.00"),
        )
        SaleItem.objects.create(
            business=self.business,
            sale=sale,
            product=self.product1,
            quantity=Decimal("2"),
            unit_price=Decimal("150.00"),
            total_price=Decimal("300.00"),
        )

        success, cu_inv = TIMSService.sign_sale_invoice(sale, branch=branch2, terminal=counter3)
        self.assertTrue(success)
        sale.refresh_from_db()
        self.assertTrue(sale.tims_synced)
        self.assertIn("ESD-PHYSICAL-003", sale.tims_invoice_number)
        self.assertIn("itax.kra.go.ke", sale.tims_verification_url)
        self.assertIn("P059999999X", sale.tims_qr_code)

    def test_offline_sale_sync_ingestion_and_stock_deduction(self):
        """Offline checkout sync endpoint correctly ingests sales, creates records, and deducts branch stock."""
        import uuid
        self.client.force_login(self.cashier_user)

        initial_stock = BranchStock.objects.get(branch=self.branch, product=self.product1).quantity
        idempotency_key = str(uuid.uuid4())

        payload = {
            "sales": [
                {
                    "idempotency_key": idempotency_key,
                    "receipt_number": "OFFLINE-TEST-001",
                    "subtotal": 300.0,
                    "tax_amount": 0.0,
                    "discount_amount": 0.0,
                    "total": 300.0,
                    "payment_method": "Cash",
                    "amount_tendered": 500.0,
                    "change_due": 200.0,
                    "created_at": "2026-09-15T12:00:00Z",
                    "items": [
                        {
                            "product_id": self.product1.id,
                            "quantity": 2,
                            "unit_price": 150.0,
                            "discount": 0.0,
                            "tax": 0.0,
                            "total": 300.0
                        }
                    ]
                }
            ]
        }

        response = self.client.post(
            reverse('pos_sync_offline_sales'),
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('synced_count'), 1)

        # Verify sale in DB
        created_sale = Sale.objects.get(idempotency_key=idempotency_key)
        self.assertEqual(created_sale.total, Decimal("300.00"))
        self.assertEqual(created_sale.items.count(), 1)
        self.assertEqual(created_sale.items.first().quantity, Decimal("2"))

        # Verify stock deduction
        updated_stock = BranchStock.objects.get(branch=self.branch, product=self.product1).quantity
        self.assertEqual(updated_stock, initial_stock - Decimal("2"))

    def test_offline_sale_sync_idempotency_prevents_duplicate_sales(self):
        """Duplicate submissions with same idempotency_key must not create duplicate sales or double-deduct stock."""
        import uuid
        self.client.force_login(self.cashier_user)

        initial_stock = BranchStock.objects.get(branch=self.branch, product=self.product1).quantity
        idempotency_key = str(uuid.uuid4())

        payload = {
            "sales": [
                {
                    "idempotency_key": idempotency_key,
                    "receipt_number": "OFFLINE-TEST-002",
                    "subtotal": 150.0,
                    "tax_amount": 0.0,
                    "discount_amount": 0.0,
                    "total": 150.0,
                    "payment_method": "Cash",
                    "created_at": "2026-09-15T12:05:00Z",
                    "items": [
                        {
                            "product_id": self.product1.id,
                            "quantity": 1,
                            "unit_price": 150.0,
                            "total": 150.0
                        }
                    ]
                }
            ]
        }

        # First sync
        res1 = self.client.post(reverse('pos_sync_offline_sales'), data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json().get('synced_count'), 1)

        # Second sync (duplicate replay)
        res2 = self.client.post(reverse('pos_sync_offline_sales'), data=json.dumps(payload), content_type="application/json")
        self.assertEqual(res2.status_code, 200)
        results = res2.json().get('results', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].get('status'), 'already_synced')

        # Stock should only be deducted once (by 1)
        updated_stock = BranchStock.objects.get(branch=self.branch, product=self.product1).quantity
        self.assertEqual(updated_stock, initial_stock - Decimal("1"))



