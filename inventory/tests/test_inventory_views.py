"""
Inventory Views & UI Integration Tests
Tests Dashboard, Warehouses CRUD, Stock Ledger, Valuation Report, Adjustments, and Transfers views.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from core.models import Company, Branch
from inventory.models import Warehouse, StockLedgerEntry, StockAdjustmentDocument
from inventory.services import post_stock_movement
from pos.models import Business, Category, Product, UnitOfMeasurement

User = get_user_model()


class InventoryViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='invsuperadmin',
            email='admin@apex.co.ke',
            password='adminpassword123',
        )
        self.client.login(username='invsuperadmin', password='adminpassword123')

        # Company & Business
        self.company = Company.objects.create(name="Apex Hypermarket Ltd", slug="apex-hyper", currency="KES")
        self.branch = Branch.objects.create(company=self.company, name="Nairobi CBD", code="NBI-CBD", is_headquarters=True)
        self.business = Business.objects.create(name="Apex Hypermarket Ltd", slug="apex-hyper", owner=self.user)

        # Warehouses
        self.wh_main = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="WH-MAIN",
            name="Main Bulk Store",
            warehouse_type=Warehouse.TYPE_MAIN,
            is_primary=True,
        )
        self.wh_store = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="WH-STORE",
            name="Retail Shelf Store",
            warehouse_type=Warehouse.TYPE_STORE,
        )

        # Products
        self.category, _ = Category.objects.get_or_create(business=self.business, name="Beverages")
        self.unit, _ = UnitOfMeasurement.objects.get_or_create(business=self.business, abbreviation="pcs", defaults={"name": "Pieces"})
        self.product = Product.objects.create(
            business=self.business,
            name="Kenya Highland Tea 500g",
            product_code="TEA-500",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('250.00'),
            unit_price=Decimal('350.00'),
            stock_quantity=Decimal('100.000'),
        )

        # Post initial stock
        post_stock_movement(
            company=self.company,
            warehouse=self.wh_main,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_OPENING_BALANCE,
            voucher_no="OP-001",
            quantity=Decimal('100.0000'),
            unit_cost=Decimal('250.0000'),
            created_by=self.user,
        )

    def test_inventory_dashboard_view(self):
        """Test accessing inventory dashboard."""
        url = reverse('inventory_dashboard')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Inventory Command Center")
        self.assertContains(resp, "25000.00")  # 100 * 250.00 valuation

    def test_warehouse_list_and_detail_views(self):
        """Test warehouse listing and detailed stock view."""
        list_url = reverse('inventory_warehouse_list')
        resp = self.client.get(list_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "WH-MAIN")
        self.assertContains(resp, "WH-STORE")

        detail_url = reverse('inventory_warehouse_detail', kwargs={'pk': self.wh_main.pk})
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Kenya Highland Tea 500g")
        self.assertContains(detail_resp, "25000.00")

    def test_warehouse_create_view(self):
        """Test creating a new warehouse via form."""
        url = reverse('inventory_warehouse_create')
        data = {
            'name': 'Cold Storage Facility',
            'code': 'WH-COLD',
            'warehouse_type': Warehouse.TYPE_MAIN,
            'branch': self.branch.pk,
            'address': 'Industrial Area, Block B',
            'is_active': True,
        }
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Warehouse.objects.filter(code='WH-COLD').exists())

    def test_stock_ledger_list_and_csv_export(self):
        """Test stock ledger view and CSV export format."""
        url = reverse('inventory_ledger_list')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "OP-001")
        self.assertContains(resp, "Kenya Highland Tea 500g")

        # Test CSV export
        csv_resp = self.client.get(url + '?export=csv')
        self.assertEqual(csv_resp.status_code, 200)
        self.assertEqual(csv_resp['Content-Type'], 'text/csv')
        self.assertIn('Posting Date', csv_resp.content.decode('utf-8'))
        self.assertIn('TEA-500', csv_resp.content.decode('utf-8'))

    def test_stock_valuation_report_view(self):
        """Test valuation report view."""
        url = reverse('inventory_valuation_report')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Inventory Asset Valuation Report")
        self.assertContains(resp, "25000.00")

    def test_stock_adjustment_create_and_post_flow(self):
        """Test creating and posting a physical stock adjustment."""
        create_url = reverse('inventory_adjustment_create')
        data = {
            'warehouse': self.wh_main.pk,
            'adjustment_date': '2026-09-30',
            'reason': StockAdjustmentDocument.REASON_PHYSICAL_COUNT,
            'notes': 'End of month audit',
            'product_id[]': [str(self.product.pk)],
            'counted_qty[]': ['95.0000'],  # Shrinkage: -5 units
        }
        resp = self.client.post(create_url, data)
        self.assertEqual(resp.status_code, 302)

        doc = StockAdjustmentDocument.objects.first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.status, StockAdjustmentDocument.STATUS_DRAFT)
        self.assertEqual(doc.total_variance_value, Decimal('-1250.00'))

        # Post the adjustment
        post_url = reverse('inventory_adjustment_post', kwargs={'pk': doc.pk})
        post_resp = self.client.post(post_url)
        self.assertEqual(post_resp.status_code, 302)

        doc.refresh_from_db()
        self.assertEqual(doc.status, StockAdjustmentDocument.STATUS_POSTED)

        # Check ledger balance updated
        latest_entry = StockLedgerEntry.objects.filter(product=self.product).order_by('-posting_time', '-id').first()
        self.assertEqual(latest_entry.balance_quantity, Decimal('95.0000'))

    def test_inter_warehouse_transfer_view_flow(self):
        """Test moving stock between two warehouses via transfer view."""
        transfer_url = reverse('inventory_transfer_create')
        data = {
            'source_warehouse': self.wh_main.pk,
            'target_warehouse': self.wh_store.pk,
            'narration': 'Daily shelf restock',
            'product_id[]': [str(self.product.pk)],
            'quantity[]': ['20.0000'],
        }
        resp = self.client.post(transfer_url, data)
        self.assertEqual(resp.status_code, 302)

        # Main warehouse balance: 100 - 20 = 80
        main_entry = StockLedgerEntry.objects.filter(warehouse=self.wh_main, product=self.product).order_by('-posting_time', '-id').first()
        self.assertEqual(main_entry.balance_quantity, Decimal('80.0000'))

        # Store warehouse balance: 0 + 20 = 20
        store_entry = StockLedgerEntry.objects.filter(warehouse=self.wh_store, product=self.product).order_by('-posting_time', '-id').first()
        self.assertEqual(store_entry.balance_quantity, Decimal('20.0000'))
