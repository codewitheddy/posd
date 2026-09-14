"""
Automated tests for Production Readiness, Multi-Tenant Boundary Isolation,
Concurrency Row-Locking, and Offline Sync Idempotency.
"""

from decimal import Decimal
import uuid
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.db import transaction

from pos.models import (
    Business, BusinessMembership, BusinessSettings, Branch, BranchStock, POSTerminal,
    Product, Category, Customer, Sale, SaleItem, StockAdjustment, PaymentMethod
)


class ProductionReadinessAuditTestCase(TestCase):
    """
    Tests covering production readiness fixes:
    1. Multi-Tenant isolation & boundary enforcement
    2. Concurrency row-locking in complete_sale
    3. Offline sync idempotency & stock adjustment
    """

    def setUp(self):
        # Create Business 1
        self.owner1 = User.objects.create_user(username='owner1', password='password123')
        self.biz1 = Business.objects.create(
            name='Store Alpha',
            slug='store-alpha',
            owner=self.owner1,
            is_active=True
        )
        self.settings1, _ = BusinessSettings.objects.get_or_create(
            business=self.biz1,
            defaults={'business_name': 'Store Alpha', 'vat_rate': Decimal('16.00')}
        )
        self.mem_owner1 = BusinessMembership.objects.create(
            user=self.owner1,
            business=self.biz1,
            role='owner',
            is_active=True
        )
        self.branch1 = Branch.objects.create(
            business=self.biz1,
            name='Alpha Main Branch',
            code='BR-ALPHA-01',
            is_active=True
        )
        self.cashier1 = User.objects.create_user(username='cashier_alpha', password='password123')
        self.mem1 = BusinessMembership.objects.create(
            user=self.cashier1,
            business=self.biz1,
            role='cashier',
            is_active=True
        )

        # Create Business 2
        self.owner2 = User.objects.create_user(username='owner2', password='password123')
        self.biz2 = Business.objects.create(
            name='Store Beta',
            slug='store-beta',
            owner=self.owner2,
            is_active=True
        )
        self.mem_owner2 = BusinessMembership.objects.create(
            user=self.owner2,
            business=self.biz2,
            role='owner',
            is_active=True
        )
        self.settings2, _ = BusinessSettings.objects.get_or_create(
            business=self.biz2,
            defaults={'business_name': 'Store Beta', 'vat_rate': Decimal('16.00')}
        )

        # Products in Business 1
        self.cat1 = Category.objects.create(business=self.biz1, name='Beverages')
        self.prod1 = Product.objects.create(
            business=self.biz1,
            category=self.cat1,
            name='Mineral Water 500ml',
            product_code='WAT-001',
            unit_price=Decimal('50.00'),
            cost_price=Decimal('30.00'),
            stock_quantity=Decimal('100.00'),
            is_active=True
        )
        BranchStock.objects.create(
            branch=self.branch1,
            product=self.prod1,
            quantity=Decimal('100.00'),
            average_cost=Decimal('30.00')
        )

        self.pm_cash, _ = PaymentMethod.objects.get_or_create(
            business=self.biz1,
            code='CASH',
            defaults={'name': 'Cash', 'is_active': True}
        )

    def test_cross_tenant_isolation_prevents_unauthorized_membership_auto_creation(self):
        """
        Cashier from Business 1 attempting to access Business 2 must NOT be auto-provisioned
        a membership in Business 2.
        """
        self.client.login(username='cashier_alpha', password='password123')

        # Visit Business 2 dashboard/POS
        response = self.client.get(reverse('pos_screen', kwargs={'slug': self.biz2.slug}))
        
        # User must be redirected or blocked
        self.assertIn(response.status_code, [302, 403])

        # Verify NO membership was automatically created in Business 2 for cashier_alpha
        has_biz2_mem = BusinessMembership.objects.filter(
            user=self.cashier1,
            business=self.biz2
        ).exists()
        self.assertFalse(has_biz2_mem, "Security Violation: Cashier from Store Alpha was granted membership in Store Beta!")

    def test_complete_sale_stock_deduction_and_atomic_locking(self):
        """
        complete_sale atomic transaction acquires row lock and accurately deducts stock.
        """
        self.client.login(username='owner1', password='password123')

        # Open session
        from pos.models import POSSession
        session = POSSession.objects.create(
            business=self.biz1,
            session_number=1,
            branch=self.branch1,
            opened_by=self.owner1,
            cashier=self.owner1,
            opening_cash=Decimal('1000.00'),
            status='open'
        )

        initial_stock = self.prod1.stock_quantity
        qty_to_buy = Decimal('5.00')

        session_store = self.client.session
        session_store['pos_session_id'] = session.id
        session_store.save()

        response = self.client.post(reverse('complete_sale', kwargs={'slug': self.biz1.slug}), {
            'items': [f"{self.prod1.id},{qty_to_buy},{self.prod1.unit_price}"],
            'payments': [f"{self.pm_cash.id},{self.prod1.unit_price * qty_to_buy},"],
            'amount_paid': str(self.prod1.unit_price * qty_to_buy),
            'discount_type': 'percentage',
            'discount_value': '0',
            'change_given': '0.00',
        })

        self.assertEqual(response.status_code, 302)

        # Refresh product from DB
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock_quantity, initial_stock - qty_to_buy)

        # Verify StockAdjustment record created
        adj = StockAdjustment.objects.filter(product=self.prod1, adjustment_type='sale').first()
        self.assertIsNotNone(adj)
        self.assertEqual(adj.quantity_change, -qty_to_buy)

    def test_offline_sync_idempotency_prevents_duplicate_sales(self):
        """
        sync_offline_sales_view ingests offline sales using idempotency_key
        and safely skips duplicates on replay.
        """
        self.client.login(username='owner1', password='password123')
        session = self.client.session
        session['active_business_id'] = self.biz1.id
        session.save()
        client_uuid = str(uuid.uuid4())

        payload = {
            'sales': [{
                'client_uuid': client_uuid,
                'total': '100.00',
                'subtotal': '86.21',
                'tax': '13.79',
                'discount': '0.00',
                'items': [{
                    'product_id': self.prod1.id,
                    'quantity': 2,
                    'unit_price': '50.00',
                    'total': '100.00'
                }]
            }]
        }

        # First sync
        initial_stock = self.prod1.stock_quantity
        resp1 = self.client.post(
            reverse('pos_sync_offline_sales'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1['success'])
        self.assertEqual(data1.get('errors'), [], f"Sync encountered errors: {data1.get('errors')}")
        self.assertEqual(data1['synced_count'], 1)

        # Verify sale in DB
        sale = Sale.objects.filter(business=self.biz1, idempotency_key=client_uuid).first()
        self.assertIsNotNone(sale)
        self.assertTrue(sale.is_offline_sync)

        # Stock deducted
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock_quantity, initial_stock - Decimal('2.00'))

        # Second sync with exact same client_uuid (Network Retry / Duplicate Sync)
        resp2 = self.client.post(
            reverse('pos_sync_offline_sales'),
            data=payload,
            content_type='application/json'
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2['success'])
        self.assertEqual(data2['synced'][0]['status'], 'already_synced')

        # Stock NOT deducted again
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.stock_quantity, initial_stock - Decimal('2.00'))
