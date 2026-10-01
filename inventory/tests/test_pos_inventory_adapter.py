"""
POS to ERP Stock Ledger Strangler Adapter Tests
Tests automatic ledger synchronization for POS Sales, Returns, and Purchase Receipts.
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from core.models import Company, Branch
from inventory.models import Warehouse, StockLedgerEntry
from pos.models import (
    Business, Category, Product, UnitOfMeasurement,
    Sale, SaleItem, SaleReturn, SaleReturnItem,
    Purchase, PurchaseItem, Supplier, PaymentMethod,
)
from pos.services.pos_inventory_adapter import POSInventoryAdapter

User = get_user_model()


class POSInventoryAdapterTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='poscashier', password='password123')

        # Company & Business
        self.company = Company.objects.create(name="QuickMart Supermarket", slug="quickmart", currency="KES")
        self.branch = Branch.objects.create(company=self.company, name="Westlands", code="WST", is_headquarters=True)
        self.business = Business.objects.create(name="QuickMart Supermarket", slug="quickmart", owner=self.user)

        # Primary Warehouse
        self.wh = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="WH-WST",
            name="Westlands Primary Store",
            warehouse_type=Warehouse.TYPE_MAIN,
            is_primary=True,
        )

        # Products
        self.category, _ = Category.objects.get_or_create(business=self.business, name="Groceries")
        self.unit, _ = UnitOfMeasurement.objects.get_or_create(business=self.business, abbreviation="pcs", defaults={"name": "Pieces"})
        self.product = Product.objects.create(
            business=self.business,
            name="Sugar 1kg",
            product_code="SUGAR-1KG",
            category=self.category,
            unit=self.unit,
            cost_price=Decimal('150.00'),
            unit_price=Decimal('190.00'),
            stock_quantity=Decimal('200.000'),
        )

    def test_pos_purchase_receipt_syncs_to_ledger(self):
        """Test that receiving a purchase order automatically creates an inbound StockLedgerEntry."""
        supplier = Supplier.objects.create(business=self.business, name="Mumias Sugar Ltd")
        purchase = Purchase.objects.create(
            business=self.business,
            supplier=supplier,
            purchase_number="PO-2026-001",
            total_amount=Decimal('15000.00'),
            status='received',
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=self.product,
            quantity=50,
            quantity_received=50,
            unit_cost=Decimal('140.00'),
            total_cost=Decimal('7000.00'),
        )

        entries = POSInventoryAdapter.sync_purchase_receipt(purchase, user=self.user)
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        self.assertEqual(entry.voucher_type, StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT)
        self.assertEqual(entry.voucher_no, "PO-2026-001")
        self.assertEqual(entry.quantity, Decimal('50.0000'))
        self.assertEqual(entry.unit_cost, Decimal('140.0000'))
        self.assertEqual(entry.balance_quantity, Decimal('50.0000'))

    def test_pos_sale_syncs_to_ledger(self):
        """Test that a completed POS sale posts outbound stock movements to the ledger."""
        # Seed opening stock
        from inventory.services.stock_ledger_service import post_stock_movement
        post_stock_movement(
            company=self.company,
            warehouse=self.wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_OPENING_BALANCE,
            voucher_no="OP-001",
            quantity=Decimal('100.0000'),
            unit_cost=Decimal('150.0000'),
        )

        sale = Sale.objects.create(
            business=self.business,
            invoice_number="INV-2026-8801",
            total=Decimal('380.00'),
            subtotal=Decimal('380.00'),
            vat_amount=Decimal('0.00'),
            cashier=self.user,
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            quantity=2,
            unit_price=Decimal('190.00'),
            total_price=Decimal('380.00'),
        )

        entries = POSInventoryAdapter.sync_sale(sale, user=self.user)
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        self.assertEqual(entry.voucher_type, StockLedgerEntry.VOUCHER_POS_SALE)
        self.assertEqual(entry.voucher_no, "INV-2026-8801")
        self.assertEqual(entry.quantity, Decimal('-2.0000'))
        self.assertEqual(entry.balance_quantity, Decimal('98.0000'))

    def test_pos_sale_return_restores_ledger_stock(self):
        """Test that processing a return increments stock in the ledger."""
        # Seed stock
        from inventory.services.stock_ledger_service import post_stock_movement
        post_stock_movement(
            company=self.company,
            warehouse=self.wh,
            product=self.product,
            voucher_type=StockLedgerEntry.VOUCHER_OPENING_BALANCE,
            voucher_no="OP-001",
            quantity=Decimal('50.0000'),
            unit_cost=Decimal('150.0000'),
        )

        sale = Sale.objects.create(
            business=self.business,
            invoice_number="INV-2026-8802",
            total=Decimal('190.00'),
            subtotal=Decimal('190.00'),
            vat_amount=Decimal('0.00'),
            cashier=self.user,
        )
        self.payment_method, _ = PaymentMethod.objects.get_or_create(
            business=self.business,
            code="CASH",
            defaults={"name": "Cash", "method_type": "cash"}
        )
        sale_return = SaleReturn.objects.create(
            original_sale=sale,
            return_number="RET-2026-001",
            subtotal=Decimal('190.00'),
            vat_amount=Decimal('0.00'),
            total_refund=Decimal('190.00'),
            refund_method=self.payment_method,
            reason="Customer exchange",
            processed_by=self.user,
        )
        SaleReturnItem.objects.create(
            sale_return=sale_return,
            product=self.product,
            quantity=1,
            unit_price=Decimal('190.00'),
            total_price=Decimal('190.00'),
        )

        entries = POSInventoryAdapter.sync_sale_return(sale_return, user=self.user)
        self.assertEqual(len(entries), 1)

        entry = entries[0]
        self.assertEqual(entry.voucher_type, StockLedgerEntry.VOUCHER_SALES_RETURN)
        self.assertEqual(entry.quantity, Decimal('1.0000'))
        self.assertEqual(entry.balance_quantity, Decimal('51.0000'))
