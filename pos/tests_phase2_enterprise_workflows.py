"""
Unit & Integration Test Suite for Phase 2: Enterprise Core Workflows
Covers B2B Sales Orders, Goods Dispatch & Delivery Notes, Stock Ledger synchronization,
General Ledger COGS auto-posting, Multi-level Purchase Approval Workflows, and
Inventory/GL Reconciliation Service.
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.contenttypes.models import ContentType

from core.models import Company, Branch
from core.models.workflows import WorkflowDefinition, WorkflowStep, ApprovalRequest
from pos.models import (
    Business, BusinessMembership, Category, Product, Supplier,
    Purchase, PurchaseItem, Customer, Branch as POSBranch, BranchStock,
    SalesOrder, SalesOrderItem, SalesOrderStatus,
    DeliveryNote, DeliveryNoteItem, DeliveryNoteStatus,
    POSGLMapping
)
from pos.sales_order_services import (
    create_sales_order, confirm_sales_order,
    create_delivery_note_from_order, dispatch_delivery_note,
    complete_delivery_note
)
from inventory.models import Warehouse, StockLedgerEntry
from inventory.services.stock_ledger_service import post_stock_movement
from inventory.services.reconciliation_service import perform_stock_reconciliation
from accounting.models import Account, AccountType, AccountCategory, NormalBalance, JournalEntry, JournalEntryStatus

User = get_user_model()


class Phase2EnterpriseWorkflowsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='admin_boss', password='password123', email='boss@enterprise.com'
        )
        self.client = Client()
        self.client.force_login(self.user)

        self.company = Company.objects.create(
            name="MegaCorp Trading",
            slug="megacorp",
            currency="KES",
            is_active=True
        )

        self.core_branch = Branch.objects.create(
            company=self.company,
            name="Nairobi Central Hub",
            code="NBI-HUB",
            is_active=True
        )

        self.business = Business.objects.create(
            name="MegaCorp Trading",
            slug="megacorp",
            owner=self.user,
            is_active=True
        )

        BusinessMembership.objects.create(
            business=self.business,
            user=self.user,
            role='owner',
            is_active=True
        )

        self.pos_branch = POSBranch.objects.create(
            business=self.business,
            name="Nairobi Central Hub",
            code="NBI-HUB",
            is_active=True
        )

        self.warehouse = Warehouse.objects.create(
            company=self.company,
            branch=self.core_branch,
            code="WH-NBI",
            name="Nairobi Main Warehouse",
            is_primary=True,
            is_active=True
        )

        # General Ledger Chart of Accounts
        self.acc_inventory = Account.objects.create(
            company=self.company,
            code="1200",
            name="Merchandise Inventory",
            account_type=AccountType.ASSET,
            category=AccountCategory.INVENTORY,
            normal_balance=NormalBalance.DEBIT,
            system_tag='inventory',
            is_active=True,
            is_system=True,
        )
        self.acc_cogs = Account.objects.create(
            company=self.company,
            code="5000",
            name="Cost of Goods Sold",
            account_type=AccountType.EXPENSE,
            category=AccountCategory.COST_OF_SALES,
            normal_balance=NormalBalance.DEBIT,
            system_tag='cogs',
            is_active=True,
            is_system=True,
        )

        self.gl_mapping = POSGLMapping.objects.create(
            business=self.business,
            inventory_account_code="1200",
            cogs_account_code="5000",
        )

        # Products & Customer
        self.category = Category.objects.create(business=self.business, name="Wholesale FMCG")

        self.product_flour = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Premium Maize Flour 24x2kg Bale",
            product_code="WH-FLOUR-24",
            cost_price=Decimal('1800.00'),
            unit_price=Decimal('2200.00'),
            stock_quantity=Decimal('100.000'),
            is_active=True,
        )

        self.product_sugar = Product.objects.create(
            business=self.business,
            category=self.category,
            name="Refined White Sugar 50kg Sack",
            product_code="WH-SUGAR-50",
            cost_price=Decimal('5500.00'),
            unit_price=Decimal('6500.00'),
            stock_quantity=Decimal('50.000'),
            is_active=True,
        )

        BranchStock.objects.create(
            branch=self.pos_branch, product=self.product_flour, quantity=Decimal('100.000')
        )
        BranchStock.objects.create(
            branch=self.pos_branch, product=self.product_sugar, quantity=Decimal('50.000')
        )

        self.customer = Customer.objects.create(
            business=self.business,
            name="Safari Supermarkets chain Ltd",
            customer_code="CUST-B2B-001",
            phone="+254700112233",
            email="procurement@safari.co.ke",
            address="Plot 45, Industrial Area, Nairobi",
            is_active=True
        )

    def test_b2b_sales_order_creation_and_confirmation(self):
        """Test B2B sales order calculation of line totals, taxes, and status transitions."""
        items_data = [
            {'product': self.product_flour, 'quantity': Decimal('20.000'), 'unit_price': Decimal('2200.00'), 'tax_rate': Decimal('16.00')},
            {'product': self.product_sugar, 'quantity': Decimal('10.000'), 'unit_price': Decimal('6500.00'), 'tax_rate': Decimal('16.00')},
        ]

        so = create_sales_order(
            business=self.business,
            customer=self.customer,
            items_data=items_data,
            user=self.user,
            branch=self.pos_branch,
            payment_terms='net_30',
            discount_amount=Decimal('1000.00'),
        )

        self.assertTrue(so.order_number.startswith('SO-'))
        self.assertEqual(so.status, SalesOrderStatus.DRAFT)
        self.assertEqual(so.items.count(), 2)

        # 20 * 2200 = 44,000 subtotal, 16% tax = 7,040 -> total = 51,040
        # 10 * 6500 = 65,000 subtotal, 16% tax = 10,400 -> total = 75,400
        # Total subtotal: 109,000. Total tax: 17,440. Total before disc: 126,440 - 1000 = 125,440
        self.assertEqual(so.subtotal, Decimal('109000.00'))
        self.assertEqual(so.tax_amount, Decimal('17440.00'))
        self.assertEqual(so.total_amount, Decimal('125440.00'))

        # Confirm Order
        so_confirmed = confirm_sales_order(so, user=self.user)
        self.assertEqual(so_confirmed.status, SalesOrderStatus.CONFIRMED)
        self.assertEqual(so_confirmed.confirmed_by, self.user)
        self.assertIsNotNone(so_confirmed.confirmed_at)

    def test_delivery_note_dispatch_deducts_stock_and_posts_cogs_gl(self):
        """
        Verify that dispatching a DeliveryNote:
        1. Deducts physical BranchStock & Product master stock.
        2. Appends an immutable StockLedgerEntry (voucher_type='sales_delivery').
        3. Updates SalesOrder status and delivered quantities.
        4. Automatically posts balanced COGS GL Journal (DR 5000 COGS / CR 1200 Inventory).
        """
        # Post initial stock movement to stock ledger
        post_stock_movement(
            company=self.company,
            warehouse=self.warehouse,
            product=self.product_flour,
            voucher_type=StockLedgerEntry.VOUCHER_OPENING_BALANCE,
            voucher_no='INIT-FLOUR-01',
            quantity=Decimal('100.0000'),
            unit_cost=Decimal('1800.00'),
            created_by=self.user,
        )

        items_data = [
            {'product': self.product_flour, 'quantity': Decimal('10.000'), 'unit_price': Decimal('2200.00')},
        ]
        so = create_sales_order(
            business=self.business,
            customer=self.customer,
            items_data=items_data,
            user=self.user,
            branch=self.pos_branch,
        )
        confirm_sales_order(so, user=self.user)

        # Create Delivery Note for full quantity
        dn = create_delivery_note_from_order(
            sales_order=so,
            user=self.user,
            carrier_info={'carrier_name': 'Express Logistics', 'vehicle_reg': 'KDG 456Z', 'driver_name': 'Kamau'}
        )
        self.assertEqual(dn.status, DeliveryNoteStatus.DRAFT)
        self.assertEqual(dn.items.count(), 1)
        self.assertEqual(dn.items.first().quantity_dispatched, Decimal('10.000'))

        # Initial stock: 100.000
        dispatched_dn = dispatch_delivery_note(dn, user=self.user)
        self.assertEqual(dispatched_dn.status, DeliveryNoteStatus.DISPATCHED)
        self.assertEqual(dispatched_dn.dispatched_by, self.user)

        # 1. Verify physical stock deduction
        self.product_flour.refresh_from_db()
        self.assertEqual(self.product_flour.stock_quantity, Decimal('90.000'))

        bstock = BranchStock.objects.get(branch=self.pos_branch, product=self.product_flour)
        self.assertEqual(bstock.quantity, Decimal('90.000'))

        # 2. Verify SalesOrder updated to DELIVERED
        so.refresh_from_db()
        self.assertEqual(so.status, SalesOrderStatus.DELIVERED)
        so_item = so.items.first()
        self.assertEqual(so_item.quantity_delivered, Decimal('10.000'))
        self.assertEqual(so_item.quantity_pending_delivery, Decimal('0.000'))

        # 3. Verify Stock Ledger Entry
        sle = StockLedgerEntry.objects.filter(
            company=self.company,
            voucher_type=StockLedgerEntry.VOUCHER_SALES_DELIVERY,
            voucher_no=dispatched_dn.delivery_number,
        ).first()
        self.assertIsNotNone(sle)
        self.assertEqual(sle.quantity, Decimal('-10.0000'))

        # 4. Verify Accounting GL Journal Entry (10 * 1800.00 = KES 18,000.00)
        gl_entry = JournalEntry.objects.filter(
            company=self.company,
            source_module='inventory',
            source_ref=dispatched_dn.delivery_number,
        ).first()
        self.assertIsNotNone(gl_entry)
        self.assertEqual(gl_entry.status, JournalEntryStatus.POSTED)
        self.assertTrue(gl_entry.is_balanced())
        dr, cr = gl_entry.calculate_totals()
        self.assertEqual(dr, Decimal('18000.00'))
        self.assertEqual(cr, Decimal('18000.00'))

        lines = list(gl_entry.lines.all())
        debit_line = next(l for l in lines if l.debit > 0)
        credit_line = next(l for l in lines if l.credit > 0)
        self.assertEqual(debit_line.account.code, '5000')  # COGS
        self.assertEqual(debit_line.debit, Decimal('18000.00'))
        self.assertEqual(credit_line.account.code, '1200')  # Inventory Asset
        self.assertEqual(credit_line.credit, Decimal('18000.00'))

        # Complete Delivery
        completed_dn = complete_delivery_note(dispatched_dn, recipient_name="Alice (Store Manager)")
        self.assertEqual(completed_dn.status, DeliveryNoteStatus.DELIVERED)
        self.assertEqual(completed_dn.recipient_name, "Alice (Store Manager)")
        self.assertIsNotNone(completed_dn.delivered_date)

    def test_purchase_multi_level_approval_workflow_integration(self):
        """Test multi-level workflow approval engine integration on Purchase Orders."""
        supplier = Supplier.objects.create(business=self.business, name="Grain Millers Ltd")
        po = Purchase.objects.create(
            business=self.business,
            supplier=supplier,
            status='draft',
            total_amount=Decimal('500000.00')
        )

        # Define 2-step Workflow
        po_ct = ContentType.objects.get_for_model(Purchase)
        wf = WorkflowDefinition.objects.create(
            company=self.company,
            name="Large PO Approval",
            code="purchase_order",
            content_type=po_ct,
            is_active=True
        )
        step1 = WorkflowStep.objects.create(workflow=wf, step_number=1, name="Department Manager Review")
        step2 = WorkflowStep.objects.create(workflow=wf, step_number=2, name="Finance Director Signoff")

        # Submit via HTTP POST
        url_submit = reverse('purchase_submit', kwargs={'slug': self.business.slug, 'pk': po.pk})
        resp = self.client.post(url_submit)
        self.assertEqual(resp.status_code, 302)

        po.refresh_from_db()
        self.assertEqual(po.status, 'pending_approval')

        # Check ApprovalRequest created by workflow engine
        appr_req = ApprovalRequest.objects.filter(
            company=self.company, content_type=po_ct, object_id=str(po.pk)
        ).first()
        self.assertIsNotNone(appr_req)
        self.assertEqual(appr_req.current_step, step1)
        self.assertEqual(appr_req.status, ApprovalRequest.STATUS_PENDING)

        # Step 1 Approval via HTTP POST
        url_approve = reverse('purchase_approve', kwargs={'slug': self.business.slug, 'pk': po.pk})
        resp1 = self.client.post(url_approve)
        self.assertEqual(resp1.status_code, 302)

        appr_req.refresh_from_db()
        self.assertEqual(appr_req.current_step, step2)
        po.refresh_from_db()
        self.assertEqual(po.status, 'pending_approval')  # Still pending final step 2

        # Step 2 Final Approval
        resp2 = self.client.post(url_approve)
        self.assertEqual(resp2.status_code, 302)

        appr_req.refresh_from_db()
        self.assertEqual(appr_req.status, ApprovalRequest.STATUS_APPROVED)
        po.refresh_from_db()
        self.assertEqual(po.status, 'approved')
        self.assertEqual(po.approved_by, self.user)

    def test_inventory_and_gl_reconciliation_service(self):
        """Test reconciliation audit service detects health vs discrepancies across inventory & GL."""
        # Initial state: product_flour (100 * 1800 = 180,000), product_sugar (50 * 5500 = 275,000)
        # Total operational valuation = 455,000.00
        report = perform_stock_reconciliation(self.business, company=self.company)
        self.assertEqual(report['total_products_checked'], 2)
        self.assertEqual(report['total_operational_valuation'], Decimal('455000.00'))
        self.assertEqual(report['discrepancies_count'], 0)
        self.assertEqual(report['status'], 'WARNING')  # GL balance is 0 vs 455,000 valuation

        # Post opening GL Journal for Merchandise Inventory 455,000.00
        from accounting.api import post_journal
        post_journal(
            company=self.company,
            branch=self.core_branch,
            source_module='inventory',
            source_ref='OPENING-VAL-01',
            narration='Opening Inventory Valuation',
            lines=[
                {'account_code': '1200', 'debit': Decimal('455000.00'), 'credit': Decimal('0.00'), 'description': 'Opening stock'},
                {'account_code': '5000', 'debit': Decimal('0.00'), 'credit': Decimal('455000.00'), 'description': 'Opening equity/offset'},
            ],
            posted_by=self.user,
        )

        balanced_report = perform_stock_reconciliation(self.business, company=self.company)
        self.assertEqual(balanced_report['gl_account_balance'], Decimal('455000.00'))
        self.assertEqual(balanced_report['valuation_variance'], Decimal('0.00'))
        self.assertTrue(balanced_report['is_valuation_balanced'])
        self.assertEqual(balanced_report['status'], 'HEALTHY')
