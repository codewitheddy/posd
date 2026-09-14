"""
Automated Test Suite for Offline-Resilient POS Terminal Sync Engine

Tests coverage:
1. Terminal device token authentication (header validation, inactive terminal/branch rejection).
2. Batched outbox sync (creating Sale, SaleItem, SalePayment, and StockMovement ledger).
3. Duplicate sync idempotency safety (replaying identical idempotency_key prevents double-deduction & duplication).
4. Negative stock / overselling tolerance (offline sales succeed without rollback, ledger flags negative balance, warning returned).
5. Downstream updates delivery (incremental catalog updates, stock display levels, requisitions/transfers status sync).
"""

import uuid
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status

from pos.models import (
    Business, Branch, POSTerminal, Product, Category, VATCode,
    PaymentMethod, BranchStock, StockMovement, Sale, SaleItem,
    StockRequisition, StockRequisitionItem, StockTransferRequest,
    StockTransferItem, Dispatch
)
from pos.terminal_sync_service import TerminalSyncService


class POSTerminalSyncTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Setup Business & Owner
        self.owner = User.objects.create_user(username='hq_owner', password='password123', email='owner@example.com')
        self.cashier = User.objects.create_user(username='branch_cashier', password='password123', email='cashier@example.com')
        self.business = Business.objects.create(name='Test Retail Enterprise', owner=self.owner, is_active=True)

        # 2. Setup HQ and Branch
        self.hq_branch = Branch.objects.create(business=self.business, name='Main HQ Warehouse', is_hq=True, is_active=True)
        self.branch_a = Branch.objects.create(business=self.business, name='Branch Downtown', is_hq=False, is_active=True)

        # 3. Setup POS Terminal with device token
        self.device_token = 'term_token_' + uuid.uuid4().hex
        self.terminal = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch_a,
            name='Counter 1',
            terminal_code='TERM-DT-01',
            device_token=self.device_token,
            is_active=True
        )

        # 4. Setup Products, Categories, VAT Codes
        self.category = Category.objects.create(business=self.business, name='Groceries')
        self.vat_16 = VATCode.objects.create(business=self.business, code='A-16', name='Standard Rate 16%', vat_rate=Decimal('16.00'), is_active=True)
        
        self.prod1 = Product.objects.create(
            business=self.business,
            category=self.category,
            name='Fresh Milk 1L',
            product_code='MILK-001',
            unit_price=Decimal('120.00'),
            cost_price=Decimal('90.00'),
            vat_code=self.vat_16,
            is_active=True
        )
        self.prod2 = Product.objects.create(
            business=self.business,
            category=self.category,
            name='White Bread 400g',
            product_code='BREAD-001',
            unit_price=Decimal('65.00'),
            cost_price=Decimal('45.00'),
            vat_code=self.vat_16,
            is_active=True
        )

        # 5. Payment Methods
        self.pm_cash, _ = PaymentMethod.objects.get_or_create(
            business=self.business, code='CASH', defaults={'name': 'Cash', 'is_active': True}
        )
        self.pm_mpesa, _ = PaymentMethod.objects.get_or_create(
            business=self.business, code='MPESA', defaults={'name': 'M-Pesa', 'is_active': True}
        )

        # 6. Initial Branch Stock
        self.stock1, _ = BranchStock.objects.get_or_create(
            branch=self.branch_a,
            product=self.prod1,
            defaults={'quantity': Decimal('50.000'), 'average_cost': Decimal('90.00')}
        )
        self.stock2, _ = BranchStock.objects.get_or_create(
            branch=self.branch_a,
            product=self.prod2,
            defaults={'quantity': Decimal('20.000'), 'average_cost': Decimal('45.00')}
        )

    def test_terminal_token_authentication(self):
        """Test terminal token authentication via header."""
        sync_url = f'/api/terminals/{self.terminal.id}/sync/'

        # Case 1: No token
        res_no_auth = self.client.post(sync_url, {}, format='json')
        self.assertIn(res_no_auth.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # Case 2: Invalid token
        self.client.credentials(HTTP_X_TERMINAL_TOKEN='invalid_token_12345')
        res_invalid = self.client.post(sync_url, {}, format='json')
        self.assertIn(res_invalid.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

        # Case 3: Valid X-Terminal-Token
        self.client.credentials(HTTP_X_TERMINAL_TOKEN=self.device_token)
        res_valid = self.client.post(sync_url, {'outbox': []}, format='json')
        self.assertEqual(res_valid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_valid.data['terminal']['terminal_code'], 'TERM-DT-01')

        # Case 4: Inactive terminal
        self.terminal.is_active = False
        self.terminal.save()
        res_inactive = self.client.post(sync_url, {'outbox': []}, format='json')
        self.assertIn(res_inactive.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_batched_offline_sales_sync_creates_sales_and_ledger(self):
        """Test syncing a batch of offline sales updates BranchStock and writes StockMovement ledger entries."""
        self.client.credentials(HTTP_X_TERMINAL_TOKEN=self.device_token)
        sync_url = f'/api/terminals/{self.terminal.id}/sync/'

        idempotency_key_1 = str(uuid.uuid4())
        idempotency_key_2 = str(uuid.uuid4())

        payload = {
            'outbox': [
                {
                    'idempotency_key': idempotency_key_1,
                    'client_created_at': '2026-09-13T00:10:00Z',
                    'cashier_id': self.cashier.id,
                    'subtotal': '240.00',
                    'vat_rate': '16.00',
                    'vat_amount': '38.40',
                    'total': '240.00',
                    'amount_paid': '240.00',
                    'items': [
                        {
                            'product_id': self.prod1.id,
                            'quantity': '2.000',
                            'unit_price': '120.00',
                            'note': 'Chilled milk'
                        }
                    ],
                    'payments': [
                        {
                            'payment_method': 'CASH',
                            'amount': '240.00'
                        }
                    ]
                },
                {
                    'idempotency_key': idempotency_key_2,
                    'client_created_at': '2026-09-13T00:12:00Z',
                    'cashier_id': self.cashier.id,
                    'subtotal': '130.00',
                    'vat_rate': '16.00',
                    'vat_amount': '20.80',
                    'total': '130.00',
                    'amount_paid': '130.00',
                    'items': [
                        {
                            'product_id': self.prod2.id,
                            'quantity': '2.000',
                            'unit_price': '65.00'
                        }
                    ],
                    'payments': [
                        {
                            'payment_method': 'MPESA',
                            'amount': '130.00',
                            'reference_number': 'QWE789123'
                        }
                    ]
                }
            ]
        }

        response = self.client.post(sync_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['processed_sales']), 2)
        self.assertEqual(response.data['processed_sales'][0]['status'], 'processed')
        self.assertEqual(response.data['processed_sales'][1]['status'], 'processed')

        # Verify Sales in database
        sale1 = Sale.objects.get(idempotency_key=idempotency_key_1)
        self.assertEqual(sale1.terminal, self.terminal)
        self.assertEqual(sale1.branch, self.branch_a)
        self.assertTrue(sale1.is_offline_sync)
        self.assertEqual(sale1.total, Decimal('240.00'))
        self.assertEqual(sale1.items.count(), 1)
        self.assertEqual(sale1.payments.count(), 1)

        # Verify Stock Deductions
        self.stock1.refresh_from_db()
        self.stock2.refresh_from_db()
        self.assertEqual(self.stock1.quantity, Decimal('48.000'))  # 50 - 2
        self.assertEqual(self.stock2.quantity, Decimal('18.000'))  # 20 - 2

        # Verify StockMovement ledger
        mv1 = StockMovement.objects.get(idempotency_key=idempotency_key_1)
        self.assertEqual(mv1.quantity_delta, Decimal('-2.000'))
        self.assertEqual(mv1.balance_after, Decimal('48.000'))
        self.assertEqual(mv1.terminal, self.terminal)
        self.assertFalse(mv1.resulted_in_negative_stock)

    def test_duplicate_sync_idempotency_safety(self):
        """Test replaying the same idempotency key twice does NOT double-deduct stock or duplicate sales."""
        self.client.credentials(HTTP_X_TERMINAL_TOKEN=self.device_token)
        sync_url = f'/api/terminals/{self.terminal.id}/sync/'

        idempotency_key = str(uuid.uuid4())
        payload = {
            'outbox': [
                {
                    'idempotency_key': idempotency_key,
                    'client_created_at': '2026-09-13T00:15:00Z',
                    'subtotal': '120.00',
                    'total': '120.00',
                    'amount_paid': '120.00',
                    'items': [
                        {
                            'product_id': self.prod1.id,
                            'quantity': '5.000',
                            'unit_price': '120.00'
                        }
                    ]
                }
            ]
        }

        # First sync attempt
        res1 = self.client.post(sync_url, payload, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.data['processed_sales'][0]['status'], 'processed')
        sale_id_1 = res1.data['processed_sales'][0]['sale_id']

        self.stock1.refresh_from_db()
        self.assertEqual(self.stock1.quantity, Decimal('45.000'))  # 50 - 5
        self.assertEqual(StockMovement.objects.filter(idempotency_key=idempotency_key).count(), 1)

        # Second sync attempt (Replay identical payload / retried after timeout)
        res2 = self.client.post(sync_url, payload, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data['processed_sales'][0]['status'], 'already_processed')
        self.assertEqual(res2.data['processed_sales'][0]['sale_id'], sale_id_1)

        # Assert no duplicate Sale created
        self.assertEqual(Sale.objects.filter(idempotency_key=idempotency_key).count(), 1)

        # Assert NO double-deduction on stock
        self.stock1.refresh_from_db()
        self.assertEqual(self.stock1.quantity, Decimal('45.000'))

        # Assert NO duplicate StockMovement created
        self.assertEqual(StockMovement.objects.filter(idempotency_key=idempotency_key).count(), 1)

    def test_offline_overselling_negative_stock_warning(self):
        """Test overselling offline produces a warning, deducts to negative, but NEVER aborts or rolls back sync."""
        self.client.credentials(HTTP_X_TERMINAL_TOKEN=self.device_token)
        sync_url = f'/api/terminals/{self.terminal.id}/sync/'

        # Current stock is 20
        idempotency_key = str(uuid.uuid4())
        payload = {
            'outbox': [
                {
                    'idempotency_key': idempotency_key,
                    'subtotal': '1625.00',
                    'total': '1625.00',
                    'amount_paid': '1625.00',
                    'items': [
                        {
                            'product_id': self.prod2.id,
                            'quantity': '25.000',  # 25 > 20 (overselling by 5)
                            'unit_price': '65.00'
                        }
                    ]
                }
            ]
        }

        response = self.client.post(sync_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        processed = response.data['processed_sales'][0]
        self.assertEqual(processed['status'], 'processed')
        self.assertTrue(len(processed['warnings']) > 0)
        self.assertIn('oversold', processed['warnings'][0].lower())

        # Stock balance should be -5.000
        self.stock2.refresh_from_db()
        self.assertEqual(self.stock2.quantity, Decimal('-5.000'))

        # Ledger record flags negative stock
        mv = StockMovement.objects.get(idempotency_key=idempotency_key)
        self.assertTrue(mv.resulted_in_negative_stock)
        self.assertEqual(mv.balance_after, Decimal('-5.000'))

    def test_downstream_catalog_and_distribution_sync(self):
        """Test downstream packaging returns catalog updates, stock display levels, and requisition/transfer status updates."""
        # Create a stock requisition for branch_a
        req = StockRequisition.objects.create(
            business=self.business,
            requesting_branch=self.branch_a,
            requested_by=self.cashier,
            status='approved',
            notes='Urgent stock for weekend'
        )
        StockRequisitionItem.objects.create(
            requisition=req,
            product=self.prod1,
            requested_quantity=Decimal('100.000'),
            approved_quantity=Decimal('80.000')
        )

        self.client.credentials(HTTP_X_TERMINAL_TOKEN=self.device_token)
        sync_url = f'/api/terminals/{self.terminal.id}/sync/'

        response = self.client.post(sync_url, {'outbox': []}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check Catalog Updates
        products = response.data['catalog_updates']['products']
        self.assertTrue(len(products) >= 2)
        prod_names = [p['name'] for p in products]
        self.assertIn('Fresh Milk 1L', prod_names)
        self.assertIn('White Bread 400g', prod_names)

        # Check Branch Stock Levels
        stock_levels = response.data['branch_stock_levels']
        self.assertTrue(len(stock_levels) >= 2)

        # Check Distribution Updates
        requisitions = response.data['distribution_updates']['requisitions']
        self.assertEqual(len(requisitions), 1)
        self.assertEqual(requisitions[0]['reference_number'], req.reference_number)
        self.assertEqual(requisitions[0]['status'], 'approved')
        self.assertEqual(len(requisitions[0]['items']), 1)
        self.assertEqual(requisitions[0]['items'][0]['approved_quantity'], '80.000')

        # Verify terminal state updated
        self.terminal.refresh_from_db()
        self.assertIsNotNone(self.terminal.last_sync_at)
        self.assertEqual(self.terminal.sync_status, 'synced')
