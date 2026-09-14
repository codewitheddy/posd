"""
Unit and integration test suite for Marid POS Multi-Branch,
Unified Stock Movement Ledger, Weighted Moving Average Cost, and Inter-Branch/HQ Distribution.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework import status

from pos.models import (
    Business, BusinessMembership, Branch, BranchMembership,
    Product, Category, BranchStock, StockMovement,
    StockRequisition, StockRequisitionItem,
    StockTransferRequest, StockTransferItem,
    Dispatch, DispatchItem, POSTerminal,
)
from pos.branch_services import DistributionService, BranchStockService
from pos.admin import StockMovementAdmin
from django.contrib.admin.sites import AdminSite


class MultiBranchLedgerTests(TestCase):
    def setUp(self):
        # Users
        self.hq_admin = User.objects.create_user(username="hq_admin", password="password123")
        self.business = Business.objects.create(name="Marid Enterprise", owner=self.hq_admin)
        BusinessMembership.objects.create(user=self.hq_admin, business=self.business, role="admin", is_active=True)

        self.branch_mgr_a = User.objects.create_user(username="mgr_a", password="password123")
        BusinessMembership.objects.create(user=self.branch_mgr_a, business=self.business, role="manager", is_active=True)

        self.branch_mgr_b = User.objects.create_user(username="mgr_b", password="password123")
        BusinessMembership.objects.create(user=self.branch_mgr_b, business=self.business, role="manager", is_active=True)

        self.cashier_a = User.objects.create_user(username="cashier_a", password="password123")
        BusinessMembership.objects.create(user=self.cashier_a, business=self.business, role="cashier", is_active=True)

        # Branches
        self.hq_branch = Branch.objects.create(
            business=self.business,
            name="Central HQ Warehouse",
            code="HQ01",
            is_hq=True,
            is_active=True,
        )
        self.branch_a = Branch.objects.create(
            business=self.business,
            name="Nairobi Branch A",
            code="NRB01",
            is_hq=False,
            is_active=True,
        )
        self.branch_b = Branch.objects.create(
            business=self.business,
            name="Mombasa Branch B",
            code="MSA01",
            is_hq=False,
            is_active=True,
        )

        # Branch Memberships
        BranchMembership.objects.create(
            user=self.hq_admin, branch=self.hq_branch, role="hq_admin", is_home_branch=True, is_active=True
        )
        BranchMembership.objects.create(
            user=self.branch_mgr_a, branch=self.branch_a, role="branch_manager", is_home_branch=True, is_active=True
        )
        BranchMembership.objects.create(
            user=self.branch_mgr_b, branch=self.branch_b, role="branch_manager", is_home_branch=True, is_active=True
        )
        BranchMembership.objects.create(
            user=self.cashier_a, branch=self.branch_a, role="cashier", is_home_branch=True, is_active=True
        )

        # Product
        self.category = Category.objects.create(business=self.business, name="Electronics")
        self.product = Product.objects.create(
            business=self.business,
            name="Wireless Barcode Scanner",
            product_code="SCAN-001",
            unit_price=Decimal("150.00"),
            cost_price=Decimal("50.00"),
            stock_quantity=Decimal("0.00"),
            is_active=True,
        )

    def test_single_hq_branch_enforcement(self):
        """Test that a business cannot have more than one HQ branch simultaneously."""
        self.assertTrue(self.hq_branch.is_hq)
        new_hq = Branch(
            business=self.business,
            name="Second HQ Attempt",
            code="HQ02",
            is_hq=True,
        )
        # clean() or save() should ensure uniqueness
        new_hq.save()
        # Refresh first HQ
        self.hq_branch.refresh_from_db()
        # Ensure only 1 HQ exists for this business
        hq_count = Branch.objects.filter(business=self.business, is_hq=True).count()
        self.assertEqual(hq_count, 1)
        self.assertTrue(new_hq.is_hq)
        self.assertFalse(self.hq_branch.is_hq)

    def test_weighted_moving_average_cost_math(self):
        """
        Verify moving-average cost calculation:
        Receipt 1: 10 units @ $50 -> Avg Cost = $50, Total Qty = 10
        Receipt 2: 10 units @ $100 -> Avg Cost = ((10*50)+(10*100))/20 = $75.00, Total Qty = 20
        """
        stock_a, _ = BranchStock.objects.get_or_create(
            branch=self.branch_a, product=self.product,
            defaults={'quantity': Decimal('0.00'), 'average_cost': Decimal('0.00')}
        )

        # First Receipt
        stock_a.receive(
            quantity=Decimal("10.00"),
            unit_cost=Decimal("50.00"),
            movement_type="purchase",
            performed_by=self.branch_mgr_a,
            notes="Initial batch"
        )
        stock_a.refresh_from_db()
        self.assertEqual(stock_a.quantity, Decimal("10.00"))
        self.assertEqual(stock_a.average_cost, Decimal("50.00"))

        # Check Stock Movement Ledger
        m1 = StockMovement.objects.filter(branch=self.branch_a, product=self.product).latest('created_at')
        self.assertEqual(m1.delta_quantity, Decimal("10.00"))
        self.assertEqual(m1.unit_cost, Decimal("50.00"))
        self.assertEqual(m1.balance_after, Decimal("10.00"))
        self.assertFalse(m1.resulted_in_negative_stock)

        # Second Receipt
        stock_a.receive(
            quantity=Decimal("10.00"),
            unit_cost=Decimal("100.00"),
            movement_type="purchase",
            performed_by=self.branch_mgr_a,
            notes="Second batch at higher cost"
        )
        stock_a.refresh_from_db()
        self.assertEqual(stock_a.quantity, Decimal("20.00"))
        # (10 * 50 + 10 * 100) / 20 = 1500 / 20 = 75.00
        self.assertEqual(stock_a.average_cost, Decimal("75.00"))

        m2 = StockMovement.objects.filter(branch=self.branch_a, product=self.product).latest('created_at')
        self.assertEqual(m2.delta_quantity, Decimal("10.00"))
        self.assertEqual(m2.unit_cost, Decimal("100.00"))
        self.assertEqual(m2.balance_after, Decimal("20.00"))

    def test_negative_stock_deduction_and_warning_flag(self):
        """
        Verify that stock deductions exceeding current balance succeed without crashing,
        setting resulted_in_negative_stock=True on the ledger entry.
        """
        stock_a, _ = BranchStock.objects.get_or_create(
            branch=self.branch_a, product=self.product,
            defaults={'quantity': Decimal('10.00'), 'average_cost': Decimal('60.00')}
        )

        # Deduct 15 units (when only 10 available)
        stock_a.deduct(
            quantity=Decimal("15.00"),
            movement_type="sale",
            performed_by=self.cashier_a,
            notes="Oversell at POS terminal"
        )
        stock_a.refresh_from_db()
        self.assertEqual(stock_a.quantity, Decimal("-5.00"))

        # Ledger check
        movement = StockMovement.objects.filter(branch=self.branch_a, product=self.product).latest('created_at')
        self.assertEqual(movement.delta_quantity, Decimal("-15.00"))
        self.assertEqual(movement.balance_after, Decimal("-5.00"))
        self.assertTrue(movement.resulted_in_negative_stock)

        # Next receipt adopts incoming unit cost directly since existing qty <= 0
        stock_a.receive(
            quantity=Decimal("20.00"),
            unit_cost=Decimal("70.00"),
            movement_type="purchase",
            performed_by=self.branch_mgr_a,
            notes="Restock recovery"
        )
        stock_a.refresh_from_db()
        self.assertEqual(stock_a.quantity, Decimal("15.00"))
        self.assertEqual(stock_a.average_cost, Decimal("70.00"))

    def test_hq_requisition_workflow_with_dispatch_and_receipt(self):
        """
        Full lifecycle test:
        1. Branch raises requisition to HQ.
        2. Attempting to dispatch prior to approval raises ValidationError.
        3. HQ approves with adjusted quantities.
        4. HQ dispatches goods (HQ stock deducted, Dispatch created in transit).
        5. Branch confirms receipt with discrepancy (Branch stock credited, moving average recalculated).
        """
        # Seed HQ stock
        hq_stock, _ = BranchStock.objects.get_or_create(
            branch=self.hq_branch, product=self.product,
            defaults={'quantity': Decimal('100.00'), 'average_cost': Decimal('45.00')}
        )

        # Step 1: Branch A creates Requisition for 20 units
        req = DistributionService.create_requisition(
            business=self.business,
            requesting_branch=self.branch_a,
            items_data=[{'product_id': self.product.id, 'quantity': Decimal('20.00')}],
            user=self.branch_mgr_a,
            notes="Need replenishment"
        )
        self.assertEqual(req.status, 'pending')
        req_item = req.items.first()
        self.assertEqual(req_item.requested_quantity, Decimal('20.00'))

        # Step 2: Attempting to dispatch before approval must fail
        with self.assertRaises(ValidationError):
            DistributionService.dispatch(
                source_doc=req,
                items_data=[{'item_id': req_item.id, 'quantity': Decimal('20.00')}],
                user=self.hq_admin
            )

        # Step 3: HQ Approves requisition for 15 units (adjusted)
        DistributionService.approve_requisition(
            requisition=req,
            approved_items_map={req_item.id: Decimal('15.00')},
            user=self.hq_admin
        )
        req.refresh_from_db()
        req_item.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(req_item.approved_quantity, Decimal('15.00'))

        # Step 4: HQ Dispatches 15 units
        dispatch_rec = DistributionService.dispatch(
            source_doc=req,
            items_data=[{'item_id': req_item.id, 'quantity': Decimal('15.00')}],
            user=self.hq_admin,
            notes="Dispatched via logistics van"
        )
        self.assertEqual(dispatch_rec.status, 'in_transit')
        self.assertEqual(dispatch_rec.source_branch, self.hq_branch)
        self.assertEqual(dispatch_rec.destination_branch, self.branch_a)

        # Verify HQ stock deducted
        hq_stock.refresh_from_db()
        self.assertEqual(hq_stock.quantity, Decimal('85.00'))

        # Step 5: Branch A confirms receipt of 14 units (1 unit damaged in transit)
        dispatch_item = dispatch_rec.items.first()
        DistributionService.confirm_receipt(
            dispatch=dispatch_rec,
            received_items_data={
                dispatch_item.id: {
                    'received_qty': Decimal('14.00'),
                    'discrepancy_reason': '1 damaged unit'
                }
            },
            user=self.branch_mgr_a
        )

        dispatch_rec.refresh_from_db()
        self.assertEqual(dispatch_rec.status, 'partially_received')

        # Verify Branch A stock credited with 14 units @ $45.00
        stock_a = BranchStock.objects.get(branch=self.branch_a, product=self.product)
        self.assertEqual(stock_a.quantity, Decimal('14.00'))
        self.assertEqual(stock_a.average_cost, Decimal('45.00'))

    def test_inter_branch_transfer_workflow(self):
        """
        Full lifecycle test of peer-to-peer branch transfer:
        1. Branch B requests transfer of 5 units from Branch A.
        2. Branch A approves & dispatches.
        3. Branch B receives stock.
        """
        # Seed Branch A stock: 30 units @ $50.00
        stock_a, _ = BranchStock.objects.get_or_create(
            branch=self.branch_a, product=self.product,
            defaults={'quantity': Decimal('30.00'), 'average_cost': Decimal('50.00')}
        )

        # Seed Branch B stock: 5 units @ $80.00
        stock_b, _ = BranchStock.objects.get_or_create(
            branch=self.branch_b, product=self.product,
            defaults={'quantity': Decimal('5.00'), 'average_cost': Decimal('80.00')}
        )

        # Prevent self-transfer
        with self.assertRaises(ValidationError):
            DistributionService.create_transfer_request(
                business=self.business,
                source_branch=self.branch_a,
                dest_branch=self.branch_a,
                items_data=[{'product_id': self.product.id, 'quantity': Decimal('5.00')}],
                user=self.branch_mgr_a
            )

        # Create valid Transfer Request
        trf = DistributionService.create_transfer_request(
            business=self.business,
            source_branch=self.branch_a,
            dest_branch=self.branch_b,
            items_data=[{'product_id': self.product.id, 'quantity': Decimal('5.00')}],
            user=self.branch_mgr_b,
            reason="Product X moving fast in Mombasa"
        )
        self.assertEqual(trf.status, 'pending')

        # Branch A approves
        trf_item = trf.items.first()
        DistributionService.approve_transfer_request(
            transfer_request=trf,
            approved_items_map={trf_item.id: Decimal('5.00')},
            user=self.branch_mgr_a
        )
        trf.refresh_from_db()
        self.assertEqual(trf.status, 'approved')

        # Branch A dispatches
        dispatch_rec = DistributionService.dispatch(
            source_doc=trf,
            items_data=[{'item_id': trf_item.id, 'quantity': Decimal('5.00')}],
            user=self.branch_mgr_a
        )
        stock_a.refresh_from_db()
        self.assertEqual(stock_a.quantity, Decimal('25.00'))

        # Branch B receives full quantity (5 units)
        dispatch_item = dispatch_rec.items.first()
        DistributionService.confirm_receipt(
            dispatch=dispatch_rec,
            received_items_data={
                dispatch_item.id: {
                    'received_qty': Decimal('5.00'),
                    'discrepancy_reason': ''
                }
            },
            user=self.branch_mgr_b
        )

        # Branch B new qty = 5 + 5 = 10.
        # Moving avg cost = ((5 * 80) + (5 * 50)) / 10 = (400 + 250) / 10 = 650 / 10 = 65.00
        stock_b.refresh_from_db()
        self.assertEqual(stock_b.quantity, Decimal('10.00'))
        self.assertEqual(stock_b.average_cost, Decimal('65.00'))

    def test_stock_movement_admin_is_read_only(self):
        """Ensure StockMovement admin site disallows adds, edits, and deletions."""
        admin_site = AdminSite()
        sma = StockMovementAdmin(StockMovement, admin_site)
        self.assertFalse(sma.has_add_permission(None))
        self.assertFalse(sma.has_change_permission(None))
        self.assertFalse(sma.has_delete_permission(None))

    def test_drf_api_endpoints_and_branch_scoping(self):
        """Verify DRF API ViewSets respect branch scoping and custom actions."""
        client = APIClient()

        # Seed HQ stock
        BranchStock.objects.update_or_create(
            branch=self.hq_branch, product=self.product,
            defaults={'quantity': Decimal('50.00'), 'average_cost': Decimal('40.00')}
        )

        # Authenticate as branch manager A
        client.force_authenticate(user=self.branch_mgr_a)

        # 1. Create Requisition via API
        post_data = {
            "requesting_branch": self.branch_a.id,
            "notes": "API Requisition test",
            "items": [
                {"product": self.product.id, "requested_quantity": "8.00"}
            ]
        }
        res = client.post("/api/requisitions/", post_data, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        req_id = res.data["id"]

        # 2. HQ Admin approves via custom action API
        client.force_authenticate(user=self.hq_admin)
        res_appr = client.post(
            f"/api/requisitions/{req_id}/approve/",
            {"approved_items": {str(res.data["items"][0]["id"]): "8.00"}},
            format="json"
        )
        self.assertEqual(res_appr.status_code, status.HTTP_200_OK)

        # 3. HQ Admin dispatches via custom action API
        res_disp = client.post(
            f"/api/requisitions/{req_id}/dispatch/",
            {"items": [{"item_id": res.data["items"][0]["id"], "quantity": "8.00"}], "notes": "API dispatch"},
            format="json"
        )
        self.assertIn(res_disp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        dispatch_id = res_disp.data.get("id") or res_disp.data.get("dispatch_id")

        # 4. Branch Manager A confirms receipt via API
        client.force_authenticate(user=self.branch_mgr_a)
        disp_obj = Dispatch.objects.get(pk=dispatch_id)
        disp_item_id = disp_obj.items.first().id

        res_recv = client.post(
            f"/api/dispatches/{dispatch_id}/confirm_receipt/",
            {"received_items": {str(disp_item_id): {"received_qty": "8.00", "discrepancy_reason": ""}}},
            format="json"
        )
        self.assertEqual(res_recv.status_code, status.HTTP_200_OK)

        # Verify ledger has records
        res_ledger = client.get("/api/stock-movements/")
        self.assertEqual(res_ledger.status_code, status.HTTP_200_OK)
        self.assertGreater(len(res_ledger.data["results"] if "results" in res_ledger.data else res_ledger.data), 0)
