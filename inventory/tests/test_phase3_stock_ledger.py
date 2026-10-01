"""
Unit & Integration Tests for Phase 3: Inventory & Append-Only Stock Ledger
Tests immutable ledger posting, moving weighted average, FIFO valuation, atomic transfers, and negative stock invariants.
"""
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from core.models import Company, Branch
from pos.models import Business, Category, Product, UnitOfMeasurement
from inventory.models import (
    Warehouse,
    StockItemSettings,
    StockLedgerEntry,
    ValuationLayer,
    StockAdjustmentDocument,
)
from inventory.services import (
    post_stock_movement,
    reverse_stock_movement,
    get_stock_balance,
    calculate_fifo_cost,
    get_inventory_valuation_summary,
    create_stock_adjustment,
    post_stock_adjustment,
    transfer_stock_between_warehouses,
)

User = get_user_model()


class StockLedgerIntegrationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='stockadmin', password='testpassword123')

        # Company & Business
        self.company = Company.objects.create(name="Apex Supermarket Ltd", slug="apex-supermarket", currency="KES")
        self.branch = Branch.objects.create(company=self.company, name="Nairobi West", code="NBI-W", is_headquarters=True)
        self.business = Business.objects.create(name="Apex Supermarket Ltd", slug="apex-supermarket", owner=self.user)

        # Warehouses
        self.main_wh = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="WH-MAIN",
            name="Main Bulk Store",
            warehouse_type=Warehouse.TYPE_MAIN,
            is_primary=True,
        )
        self.shelf_wh = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="WH-SHELF",
            name="Front Retail Shelf",
            warehouse_type=Warehouse.TYPE_STORE,
        )

        # Product
        self.category, _ = Category.objects.get_or_create(business=self.business, name="Beverages")
        self.unit, _ = UnitOfMeasurement.objects.get_or_create(business=self.business, abbreviation="pcs", defaults={"name": "Pieces"})
        self.product = Product.objects.create(
            business=self.business,
            name="Premium Coffee 500g",
            product_code="PRD-COFFEE",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('500.00'),
            unit_price=Decimal('750.00'),
            stock_quantity=Decimal('0.000'),
        )

    def test_inbound_receipt_and_weighted_average_cost(self):
        """
        Test that consecutive receipts calculate the moving weighted average cost accurately:
        Batch 1: 10 units @ KES 400.00 => Bal: 10 @ KES 400.00 (Val: 4,000.00)
        Batch 2: 10 units @ KES 600.00 => Bal: 20 @ KES 500.00 (Val: 10,000.00)
        """
        # Batch 1
        e1 = post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT,
            voucher_no="GRN-0001",
            quantity=Decimal('10.0000'),
            unit_cost=Decimal('400.0000'),
            created_by=self.user,
        )
        self.assertEqual(e1.balance_quantity, Decimal('10.0000'))
        self.assertEqual(e1.valuation_rate, Decimal('400.0000'))
        self.assertEqual(e1.balance_value, Decimal('4000.00'))

        # Batch 2
        e2 = post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT,
            voucher_no="GRN-0002",
            quantity=Decimal('10.0000'),
            unit_cost=Decimal('600.0000'),
            created_by=self.user,
        )
        self.assertEqual(e2.balance_quantity, Decimal('20.0000'))
        self.assertEqual(e2.valuation_rate, Decimal('500.0000'))
        self.assertEqual(e2.balance_value, Decimal('10000.00'))

    def test_outbound_sale_depletes_at_valuation_rate(self):
        """
        Test that outbound sale/dispatch consumes stock at the current valuation rate.
        Starting: 20 units @ KES 500.00
        Sale: 5 units => Bal: 15 @ KES 500.00 (Val: 7,500.00)
        """
        # Initial stock 20 @ 500
        post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_OPENING_BALANCE,
            voucher_no="OP-001",
            quantity=Decimal('20.0000'),
            unit_cost=Decimal('500.0000'),
        )

        sale_entry = post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_POS_SALE,
            voucher_no="INV-2026-0001",
            quantity=Decimal('-5.0000'),
            created_by=self.user,
        )
        self.assertEqual(sale_entry.quantity, Decimal('-5.0000'))
        self.assertEqual(sale_entry.unit_cost, Decimal('500.0000'))
        self.assertEqual(sale_entry.balance_quantity, Decimal('15.0000'))
        self.assertEqual(sale_entry.balance_value, Decimal('7500.00'))

    def test_negative_stock_rejection_invariant(self):
        """Verify that dispatching more than available stock raises ValidationError."""
        StockItemSettings.objects.create(
            company=self.company,
            product=self.product,
            allow_negative_stock=False,
        )
        # On hand: 0, Request: 5 units
        with self.assertRaises(ValidationError):
            post_stock_movement(
                company=self.company,
                warehouse=self.main_wh,
                product=self.product,
                voucher_type=StockLedgerEntry.VOUCHER_POS_SALE,
                voucher_no="INV-FAIL",
                quantity=Decimal('-5.0000'),
            )

    def test_reversal_entry_reverses_balance(self):
        """Test that reversing an entry creates an opposite entry restoring balance."""
        entry = post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT,
            voucher_no="GRN-REV-TEST",
            quantity=Decimal('50.0000'),
            unit_cost=Decimal('500.0000'),
        )
        self.assertEqual(entry.balance_quantity, Decimal('50.0000'))

        rev = reverse_stock_movement(entry, reason="Vendor recall error", user=self.user)
        self.assertEqual(rev.quantity, Decimal('-50.0000'))
        self.assertEqual(rev.balance_quantity, Decimal('0.0000'))
        self.assertTrue(rev.is_reversal)
        self.assertEqual(rev.reversed_entry, entry)

    def test_fifo_layer_cost_calculation(self):
        """
        Test FIFO depletion across multiple receipt batches:
        Layer 1: 5 units @ KES 100.00
        Layer 2: 10 units @ KES 200.00
        Consume: 8 units => 5 @ 100 + 3 @ 200 = KES 1,100.00
        """
        post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT,
            voucher_no="GRN-FIFO-1",
            quantity=Decimal('5.0000'),
            unit_cost=Decimal('100.0000'),
        )
        post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT,
            voucher_no="GRN-FIFO-2",
            quantity=Decimal('10.0000'),
            unit_cost=Decimal('200.0000'),
        )

        cost, layers = calculate_fifo_cost(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            quantity_to_consume=Decimal('8.0000'),
        )
        self.assertEqual(cost, Decimal('1100.00'))
        self.assertEqual(len(layers), 2)
        self.assertEqual(layers[0]['quantity_taken'], Decimal('5.0000'))
        self.assertEqual(layers[1]['quantity_taken'], Decimal('3.0000'))

    def test_atomic_inter_warehouse_transfer(self):
        """Test stock transfer between two warehouses."""
        # Initial stock at main warehouse: 50 units
        post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_OPENING_BALANCE,
            voucher_no="OP-001",
            quantity=Decimal('50.0000'),
            unit_cost=Decimal('500.0000'),
        )

        trf_no, entries = transfer_stock_between_warehouses(
            company=self.company,
            source_warehouse=self.main_wh,
            target_warehouse=self.shelf_wh,
            items_data=[{'product': self.product, 'quantity': Decimal('15.0000')}],
            narration="Daily shelf restock",
            user=self.user,
        )

        self.assertEqual(len(entries), 2)
        main_bal = get_stock_balance(self.company, self.main_wh, self.product)
        shelf_bal = get_stock_balance(self.company, self.shelf_wh, self.product)

        self.assertEqual(main_bal['balance_quantity'], Decimal('35.0000'))
        self.assertEqual(shelf_bal['balance_quantity'], Decimal('15.0000'))
        self.assertEqual(shelf_bal['valuation_rate'], Decimal('500.0000'))

    def test_physical_stock_adjustment(self):
        """Test physical count reconciliation adjustment."""
        # System has 10 units
        post_stock_movement(
            company=self.company,
            warehouse=self.main_wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_OPENING_BALANCE,
            voucher_no="OP-001",
            quantity=Decimal('10.0000'),
            unit_cost=Decimal('500.0000'),
        )

        # Count found 8 units (2 units shrinkage/loss)
        doc = create_stock_adjustment(
            company=self.company,
            warehouse=self.main_wh,
            reason=StockAdjustmentDocument.REASON_PHYSICAL_COUNT,
            lines_data=[{'product': self.product, 'counted_quantity': Decimal('8.0000')}],
            created_by=self.user,
        )
        self.assertEqual(doc.lines.first().variance_quantity, Decimal('-2.0000'))
        self.assertEqual(doc.total_variance_value, Decimal('-1000.00'))

        post_stock_adjustment(doc, user=self.user)
        self.assertEqual(doc.status, StockAdjustmentDocument.STATUS_POSTED)

        bal = get_stock_balance(self.company, self.main_wh, self.product)
        self.assertEqual(bal['balance_quantity'], Decimal('8.0000'))
