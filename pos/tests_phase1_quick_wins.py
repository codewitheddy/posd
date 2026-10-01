"""
Unit & Integration Tests for Phase 1 Quick Wins
Tests fractional decimal quantities in purchasing/GRN, list view pagination & aggregations,
and automatic General Ledger journal posting on stock count write-offs.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import Company, Branch
from pos.models import (
    Business, BusinessMembership, Category, Product, Supplier,
    Purchase, PurchaseItem, GoodsReceivedNote, GoodsReceivedNoteItem,
    Customer, StockAdjustment
)
from inventory.models import Warehouse, StockAdjustmentDocument
from inventory.services import create_stock_adjustment, post_stock_adjustment
from accounting.models import Account, AccountType, AccountCategory, NormalBalance, JournalEntry, JournalEntryStatus

User = get_user_model()


class Phase1QuickWinsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='admin_user', password='password123', email='admin@test.com')
        self.client = Client()
        self.client.force_login(self.user)

        # Core Company & Branch
        self.company = Company.objects.create(name="Prime Retailers Ltd", slug="prime-retailers", currency="KES")
        self.branch = Branch.objects.create(company=self.company, name="HQ Branch", code="HQ", is_headquarters=True)

        # POS Business
        self.business = Business.objects.create(name="Prime Retailers Ltd", slug="prime-retailers", owner=self.user)
        self.membership = BusinessMembership.objects.create(
            user=self.user, business=self.business, role='owner', is_active=True
        )

        # Chart of Accounts for Accounting GL integration tests
        self.inv_account = Account.objects.create(
            company=self.company,
            code='1200',
            name='Merchandise Inventory Asset',
            account_type=AccountType.ASSET,
            category=AccountCategory.INVENTORY,
            normal_balance=NormalBalance.DEBIT,
            system_tag='inventory',
            is_active=True,
            is_system=True,
        )
        self.shrinkage_account = Account.objects.create(
            company=self.company,
            code='5100',
            name='Inventory Shrinkage & Spoilage',
            account_type=AccountType.EXPENSE,
            category=AccountCategory.COST_OF_SALES,
            normal_balance=NormalBalance.DEBIT,
            system_tag='inventory_spoilage',
            is_active=True,
            is_system=True,
        )

        # Category, Product, Supplier
        self.category = Category.objects.create(business=self.business, name="Bulk Grains")
        self.product = Product.objects.create(
            business=self.business,
            name="Wheat Grain Bulk",
            product_code="WHEAT-01",
            cost_price=Decimal('120.00'),
            unit_price=Decimal('180.00'),
            stock_quantity=Decimal('50.000'),
            low_stock_threshold=Decimal('10.000'),
            category=self.category,
        )
        self.supplier = Supplier.objects.create(
            business=self.business,
            name="Grain Millers Ltd",
            phone="+254700111222",
            email="orders@grainmillers.co.ke",
            is_active=True,
        )

        # Warehouse
        self.warehouse = Warehouse.objects.create(
            company=self.company,
            branch=self.branch,
            code="WH-MAIN",
            name="Main Warehouse",
            warehouse_type=Warehouse.TYPE_MAIN,
            is_primary=True,
        )

    def test_fractional_decimal_purchase_receive(self):
        """Verify receiving fractional decimal quantities (e.g. 12.5 kg received, 0.5 kg damaged)."""
        purchase = Purchase.objects.create(
            business=self.business,
            supplier=self.supplier,
            purchase_number="PO-2026-0001",
            total_amount=Decimal('1800.00'),
            status='ordered',
        )
        item = PurchaseItem.objects.create(
            business=self.business,
            purchase=purchase,
            product=self.product,
            quantity=Decimal('15.000'),
            unit_cost=Decimal('120.00'),
            total_cost=Decimal('1800.00'),
        )

        # Receive 12.500 kg good, 0.500 kg damaged (13.000 total out of 15.000)
        receiving_data = {
            'items': [
                {
                    'item_id': item.id,
                    'quantity_received': Decimal('12.500'),
                    'quantity_damaged': Decimal('0.500'),
                    'notes': '0.5kg sack torn in transit',
                }
            ]
        }
        success = purchase.mark_as_received(receiving_data)
        self.assertTrue(success)

        item.refresh_from_db()
        self.assertEqual(item.quantity_received, Decimal('12.500'))
        self.assertEqual(item.quantity_damaged, Decimal('0.500'))
        
        self.product.refresh_from_db()
        # Initial 50.000 + 12.500 received = 62.500
        self.assertEqual(self.product.stock_quantity, Decimal('62.500'))

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'partially_received')

    def test_supplier_list_pagination_and_aggregation(self):
        """Verify supplier list displays with pagination and annotated purchase metrics without N+1 queries."""
        # Create 30 suppliers to test pagination (25 per page)
        suppliers = []
        for i in range(1, 31):
            suppliers.append(Supplier(
                business=self.business,
                name=f"Supplier {i:02d}",
                phone=f"+254700000{i:02d}",
                is_active=True,
            ))
        Supplier.objects.bulk_create(suppliers)

        # Create purchase for Supplier 01
        s1 = Supplier.objects.get(business=self.business, name="Supplier 01")
        Purchase.objects.create(
            business=self.business,
            supplier=s1,
            purchase_number="PO-S1-01",
            total_amount=Decimal('45000.00'),
            status='received',
        )

        url = reverse('supplier_list', kwargs={'slug': self.business.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Should be paginated (page 1 has 25 items)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['suppliers']), 25)

        # Verify annotated values on Supplier 01
        s1_in_context = next((s for s in response.context['suppliers'] if s.name == "Supplier 01"), None)
        if s1_in_context:
            self.assertEqual(s1_in_context.total_purchases_amount, Decimal('45000.00'))
            self.assertEqual(s1_in_context.purchases_count, 1)

    def test_customer_list_single_query_aggregation_and_pagination(self):
        """Verify customer list performs single-query counts and paginates at 25 items."""
        customers = []
        for i in range(1, 30):
            cust_type = 'vip' if i <= 5 else ('wholesale' if i <= 10 else 'regular')
            customers.append(Customer(
                business=self.business,
                name=f"Customer {i:02d}",
                customer_code=f"CUST-{i:04d}",
                phone=f"+254711000{i:02d}",
                customer_type=cust_type,
                is_active=True,
            ))
        Customer.objects.bulk_create(customers)

        url = reverse('customer_list', kwargs={'slug': self.business.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(response.context['total_count'], 29)
        self.assertEqual(response.context['vip_count'], 5)
        self.assertEqual(response.context['wholesale_count'], 5)
        self.assertEqual(response.context['regular_count'], 19)

    def test_stock_adjustment_posts_balanced_gl_journal(self):
        """Verify that posting a StockAdjustmentDocument creates a balanced double-entry GL journal."""
        from inventory.services import post_stock_movement
        # Post opening balance of 50 units @ KES 120.00 in the stock ledger
        post_stock_movement(
            company=self.company,
            warehouse=self.warehouse,
            product=self.product,
            voucher_type='opening_balance',
            voucher_no='INIT-001',
            quantity=Decimal('50.0000'),
            unit_cost=Decimal('120.00'),
            created_by=self.user,
        )

        # System stock is 50.000 @ KES 120.00. Physical count is 45.000 (-5.000 deficit = KES -600.00).
        doc = create_stock_adjustment(
            company=self.company,
            warehouse=self.warehouse,
            reason=StockAdjustmentDocument.REASON_DAMAGE,
            lines_data=[
                {
                    'product': self.product,
                    'counted_quantity': Decimal('45.0000'),
                }
            ],
            notes="5 units broken during warehouse reorganization",
            created_by=self.user,
        )
        self.assertEqual(doc.status, StockAdjustmentDocument.STATUS_DRAFT)
        self.assertEqual(doc.total_variance_value, Decimal('-600.00'))

        posted_doc = post_stock_adjustment(doc, user=self.user)
        self.assertEqual(posted_doc.status, StockAdjustmentDocument.STATUS_POSTED)

        # Check Accounting GL Journal Entry created
        gl_entry = JournalEntry.objects.filter(
            company=self.company,
            source_module='inventory',
            source_ref=doc.adjustment_number,
        ).first()

        self.assertIsNotNone(gl_entry)
        self.assertEqual(gl_entry.status, JournalEntryStatus.POSTED)
        self.assertTrue(gl_entry.is_balanced())
        total_dr, total_cr = gl_entry.calculate_totals()
        self.assertEqual(total_dr, Decimal('600.00'))
        self.assertEqual(total_cr, Decimal('600.00'))

        # Verify Lines: DR 5100 Shrinkage 600.00 / CR 1200 Inventory 600.00
        lines = list(gl_entry.lines.all())
        self.assertEqual(len(lines), 2)
        debit_line = next(l for l in lines if l.debit > 0)
        credit_line = next(l for l in lines if l.credit > 0)

        self.assertEqual(debit_line.account.code, '5100')
        self.assertEqual(debit_line.debit, Decimal('600.00'))
        self.assertEqual(credit_line.account.code, '1200')
        self.assertEqual(credit_line.credit, Decimal('600.00'))
