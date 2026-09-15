from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from pos.models import (
    Business, BusinessMembership, Branch, BranchMembership,
    Product, Category, BranchStock, StockMovement,
    StockTransferRequest, StockTransferItem, Dispatch, DispatchItem,
    TransferEvent, TransferApprovalRule,
)
from pos.branch_services import DistributionService, BranchStockService


class StockTransferLifecycleTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Admin user and business
        self.admin_user = User.objects.create_user(username="admin_user", password="password123")
        self.business = Business.objects.create(name="Apex Retailers", owner=self.admin_user, slug="apex-retailers")
        BusinessMembership.objects.create(user=self.admin_user, business=self.business, role="admin", is_active=True)

        # Manager user
        self.mgr_user = User.objects.create_user(username="source_mgr", password="password123")
        BusinessMembership.objects.create(user=self.mgr_user, business=self.business, role="manager", is_active=True)

        # Dest user
        self.dest_user = User.objects.create_user(username="dest_staff", password="password123")
        BusinessMembership.objects.create(user=self.dest_user, business=self.business, role="cashier", is_active=True)

        # Branches
        self.source_branch = Branch.objects.create(
            business=self.business, name="Central Warehouse", code="CW-01", is_active=True
        )
        self.dest_branch = Branch.objects.create(
            business=self.business, name="Eastside Outlet", code="EO-02", is_active=True
        )

        BranchMembership.objects.create(user=self.mgr_user, branch=self.source_branch, role="manager", is_active=True)
        BranchMembership.objects.create(user=self.dest_user, branch=self.dest_branch, role="cashier", is_active=True)
        BranchMembership.objects.create(user=self.admin_user, branch=self.source_branch, role="manager", is_active=True)

        # Category & Products
        self.category = Category.objects.create(business=self.business, name="Beverages")
        self.product_a = Product.objects.create(
            business=self.business,
            name="Soda 500ml",
            product_code="SKU-SODA-500",
            barcode="111111111111",
            category=self.category,
            cost_price=Decimal("20.00"),
            unit_price=Decimal("35.00"),
            stock_quantity=Decimal("100.000"),
            is_active=True,
        )
        self.product_b = Product.objects.create(
            business=self.business,
            name="Mineral Water 1L",
            product_code="SKU-WATER-1L",
            barcode="222222222222",
            category=self.category,
            cost_price=Decimal("10.00"),
            unit_price=Decimal("20.00"),
            stock_quantity=Decimal("150.000"),
            is_active=True,
        )

        # Initial source branch stock
        BranchStockService.add(self.source_branch, self.product_a, Decimal("100.000"), Decimal("20.00"))
        BranchStockService.add(self.source_branch, self.product_b, Decimal("150.000"), Decimal("10.00"))

    def test_full_successful_transfer_lifecycle(self):
        """Test complete flow: Create -> Approve -> Dispatch -> Receive (Full)."""
        items_data = [
            {'product_id': self.product_a.id, 'quantity': Decimal("30.000")},
            {'product_id': self.product_b.id, 'quantity': Decimal("50.000")},
        ]

        # 1. Create Transfer Request
        trf = DistributionService.create_transfer_request(
            business=self.business,
            source_branch=self.source_branch,
            dest_branch=self.dest_branch,
            items_data=items_data,
            user=self.dest_user,
            reason="Replenish weekend inventory",
        )
        self.assertIsNotNone(trf.reference_number)
        self.assertEqual(trf.status, 'pending')
        self.assertEqual(trf.items.count(), 2)
        # Verify event logged
        self.assertTrue(trf.events.filter(event_type__in=['created', 'submitted']).exists())

        # 2. Approve Transfer Request
        approved_map = {item.id: item.requested_quantity for item in trf.items.all()}
        trf = DistributionService.approve_transfer_request(trf, approved_map, self.mgr_user)
        self.assertEqual(trf.status, 'approved')
        self.assertEqual(trf.approved_by, self.mgr_user)
        self.assertTrue(trf.events.filter(event_type='approved').exists())

        # 3. Dispatch Stock
        dispatch_items = [{'item_id': item.id, 'quantity': item.approved_quantity} for item in trf.items.all()]
        dispatch = DistributionService.dispatch(trf, dispatch_items, self.mgr_user, notes="Truck 4A")

        # Check source branch stock was decremented
        src_stock_a = BranchStock.objects.get(branch=self.source_branch, product=self.product_a)
        src_stock_b = BranchStock.objects.get(branch=self.source_branch, product=self.product_b)
        self.assertEqual(src_stock_a.quantity, Decimal("70.000"))
        self.assertEqual(src_stock_b.quantity, Decimal("100.000"))

        # Verify in_transit_out movements logged
        movements = StockMovement.objects.filter(branch=self.source_branch, movement_type='in_transit_out')
        self.assertEqual(movements.count(), 2)

        # Verify transfer status is dispatched
        trf.refresh_from_db()
        self.assertEqual(trf.status, 'dispatched')
        self.assertEqual(dispatch.status, 'in_transit')
        self.assertTrue(trf.events.filter(event_type='dispatched').exists())

        # Verify unit cost at dispatch was captured
        for it in trf.items.all():
            self.assertGreater(it.unit_cost_at_dispatch, Decimal("0.00"))

        # 4. Confirm Full Receipt
        recv_data = {
            item.id: {'received_qty': item.dispatched_quantity, 'discrepancy_reason': ''}
            for item in dispatch.items.all()
        }
        dispatch = DistributionService.confirm_receipt(dispatch, recv_data, self.dest_user)

        # Verify destination stock increased
        dst_stock_a = BranchStock.objects.get(branch=self.dest_branch, product=self.product_a)
        dst_stock_b = BranchStock.objects.get(branch=self.dest_branch, product=self.product_b)
        self.assertEqual(dst_stock_a.quantity, Decimal("30.000"))
        self.assertEqual(dst_stock_b.quantity, Decimal("50.000"))

        # Verify final statuses
        self.assertEqual(dispatch.status, 'received')
        trf.refresh_from_db()
        self.assertEqual(trf.status, 'completed')
        self.assertTrue(trf.events.filter(event_type='received_full').exists())

    def test_discrepancy_handling_and_supervisor_loss_writeoff(self):
        """Test short receipt triggering discrepancy_flagged and supervisor write-off."""
        items_data = [{'product_id': self.product_a.id, 'quantity': Decimal("20.000")}]
        trf = DistributionService.create_transfer_request(
            business=self.business, source_branch=self.source_branch, dest_branch=self.dest_branch,
            items_data=items_data, user=self.dest_user
        )
        approved_map = {item.id: Decimal("20.000") for item in trf.items.all()}
        DistributionService.approve_transfer_request(trf, approved_map, self.mgr_user)

        dispatch_items = [{'item_id': item.id, 'quantity': Decimal("20.000")} for item in trf.items.all()]
        dispatch = DistributionService.dispatch(trf, dispatch_items, self.mgr_user)

        # Receive only 16 units (4 damaged in transit)
        dispatch_item = dispatch.items.first()
        recv_data = {
            dispatch_item.id: {
                'received_qty': Decimal("16.000"),
                'discrepancy_reason': '4 bottles broken in transit'
            }
        }
        dispatch = DistributionService.confirm_receipt(dispatch, recv_data, self.dest_user)

        # Destination stock must ONLY have received quantity
        dst_stock = BranchStock.objects.get(branch=self.dest_branch, product=self.product_a)
        self.assertEqual(dst_stock.quantity, Decimal("16.000"))

        # Check transfer & dispatch status
        trf.refresh_from_db()
        self.assertEqual(trf.status, 'discrepancy_flagged')
        self.assertEqual(dispatch.status, 'partially_received')

        trf_item = trf.items.first()
        self.assertEqual(trf_item.received_quantity, Decimal("16.000"))
        self.assertEqual(trf_item.discrepancy_quantity, Decimal("4.000"))
        self.assertEqual(trf_item.discrepancy_reason, '4 bottles broken in transit')

        # Supervisor resolves discrepancy via writeoff_loss
        resolutions = {
            trf_item.id: {
                'resolution': 'writeoff_loss',
                'notes': 'Carrier verified broken bottles upon delivery'
            }
        }
        trf = DistributionService.resolve_discrepancy(
            trf, resolutions, self.admin_user, resolution_notes="Written off per courier claim #992"
        )

        self.assertEqual(trf.status, 'resolved')
        self.assertEqual(trf.discrepancy_resolved_by, self.admin_user)
        self.assertIsNotNone(trf.discrepancy_resolved_at)

        # Check that transit_loss_writeoff movement was created
        loss_movement = StockMovement.objects.filter(
            branch=self.source_branch, product=self.product_a, movement_type='transit_loss_writeoff'
        ).first()
        self.assertIsNotNone(loss_movement)
        self.assertEqual(loss_movement.quantity_delta, Decimal("-4.000"))

    def test_discrepancy_handling_and_return_to_source(self):
        """Test short receipt resolved by returning missing/rejected units to source branch."""
        items_data = [{'product_id': self.product_b.id, 'quantity': Decimal("30.000")}]
        trf = DistributionService.create_transfer_request(
            business=self.business, source_branch=self.source_branch, dest_branch=self.dest_branch,
            items_data=items_data, user=self.dest_user
        )
        approved_map = {item.id: Decimal("30.000") for item in trf.items.all()}
        DistributionService.approve_transfer_request(trf, approved_map, self.mgr_user)

        dispatch_items = [{'item_id': item.id, 'quantity': Decimal("30.000")} for item in trf.items.all()]
        dispatch = DistributionService.dispatch(trf, dispatch_items, self.mgr_user)

        # Source stock is now 150 - 30 = 120
        src_stock_before = BranchStock.objects.get(branch=self.source_branch, product=self.product_b)
        self.assertEqual(src_stock_before.quantity, Decimal("120.000"))

        # Destination receives 20 units (10 rejected / left at source)
        dispatch_item = dispatch.items.first()
        recv_data = {
            dispatch_item.id: {
                'received_qty': Decimal("20.000"),
                'discrepancy_reason': '10 units returned to source depot'
            }
        }
        DistributionService.confirm_receipt(dispatch, recv_data, self.dest_user)

        # Supervisor resolves by returning to source
        trf.refresh_from_db()
        trf_item = trf.items.first()
        resolutions = {
            trf_item.id: {
                'resolution': 'returned_to_source',
                'notes': 'Re-stocked in source depot'
            }
        }
        DistributionService.resolve_discrepancy(trf, resolutions, self.admin_user, "Re-credited source inventory")

        # Source stock must now be 120 + 10 = 130
        src_stock_after = BranchStock.objects.get(branch=self.source_branch, product=self.product_b)
        self.assertEqual(src_stock_after.quantity, Decimal("130.000"))

        return_movement = StockMovement.objects.filter(
            branch=self.source_branch, product=self.product_b, movement_type='transit_return_in'
        ).first()
        self.assertIsNotNone(return_movement)
        self.assertEqual(return_movement.quantity_delta, Decimal("10.000"))

    def test_auto_approval_rule_threshold_evaluation(self):
        """Test auto-approval when value and quantity fall below rule thresholds."""
        rule = TransferApprovalRule.objects.create(
            business=self.business,
            name="Small Transfer Fast-Track",
            is_active=True,
            auto_approve_below_threshold=True,
            min_value_threshold=Decimal("500.00"),
            min_quantity_threshold=Decimal("50.000"),
            requires_hq_approval=False,
        )

        # Low-value request: 5 units of Product A ($20 each = $100 total)
        items_low = [{'product_id': self.product_a.id, 'quantity': Decimal("5.000")}]
        trf_auto = DistributionService.create_transfer_request(
            business=self.business, source_branch=self.source_branch, dest_branch=self.dest_branch,
            items_data=items_low, user=self.dest_user
        )
        self.assertEqual(trf_auto.status, 'approved')
        self.assertTrue(trf_auto.auto_approved)
        self.assertFalse(trf_auto.requires_approval)

        # High-value request: 40 units of Product A ($20 each = $800 total, exceeds $500)
        items_high = [{'product_id': self.product_a.id, 'quantity': Decimal("40.000")}]
        trf_manual = DistributionService.create_transfer_request(
            business=self.business, source_branch=self.source_branch, dest_branch=self.dest_branch,
            items_data=items_high, user=self.dest_user
        )
        self.assertEqual(trf_manual.status, 'pending')
        self.assertFalse(trf_manual.auto_approved)

        # If requires_hq_approval is enabled, even small transfer requires approval
        rule.requires_hq_approval = True
        rule.save()

        trf_hq_req = DistributionService.create_transfer_request(
            business=self.business, source_branch=self.source_branch, dest_branch=self.dest_branch,
            items_data=items_low, user=self.dest_user
        )
        self.assertEqual(trf_hq_req.status, 'pending')
        self.assertFalse(trf_hq_req.auto_approved)

    def test_insufficient_stock_prevents_dispatch(self):
        """Test that dispatching more than available branch stock raises ValidationError."""
        items_data = [{'product_id': self.product_a.id, 'quantity': Decimal("150.000")}]  # only 100 available
        trf = DistributionService.create_transfer_request(
            business=self.business, source_branch=self.source_branch, dest_branch=self.dest_branch,
            items_data=items_data, user=self.dest_user
        )
        approved_map = {item.id: Decimal("150.000") for item in trf.items.all()}
        DistributionService.approve_transfer_request(trf, approved_map, self.mgr_user)

        dispatch_items = [{'item_id': item.id, 'quantity': Decimal("150.000")} for item in trf.items.all()]
        with self.assertRaises(ValidationError):
            DistributionService.dispatch(trf, dispatch_items, self.mgr_user)

    def test_web_views_and_discrepancy_resolution_flow(self):
        """Test web HTTP endpoints for transfer lifecycle and discrepancy resolution."""
        self.client.login(username="admin_user", password="password123")

        # Create transfer via web form
        create_url = reverse('transfer_request_create')
        post_data = {
            'source_branch': self.source_branch.id,
            'destination_branch': self.dest_branch.id,
            'reason': 'Web test replenishment',
            'product_id[]': [self.product_a.id],
            'quantity[]': ['10'],
        }
        res = self.client.post(create_url, post_data, follow=True)
        self.assertEqual(res.status_code, 200)
        trf = StockTransferRequest.objects.filter(business=self.business).latest('created_at')

        # Approve via web
        appr_url = reverse('transfer_request_approve', kwargs={'pk': trf.pk})
        trf_item = trf.items.first()
        res = self.client.post(appr_url, {f'approved_qty_{trf_item.id}': '10'}, follow=True)
        self.assertEqual(res.status_code, 200)

        # Dispatch via web
        disp_url = reverse('transfer_request_dispatch', kwargs={'pk': trf.pk})
        res = self.client.post(disp_url, {f'dispatch_qty_{trf_item.id}': '10', 'dispatch_notes': 'Web test'}, follow=True)
        self.assertEqual(res.status_code, 200)
        dispatch = trf.dispatches.first()

        # Receive with discrepancy via web
        recv_url = reverse('dispatch_receive', kwargs={'pk': dispatch.pk})
        disp_item = dispatch.items.first()
        res = self.client.post(recv_url, {
            f'recv_qty_{disp_item.id}': '8',
            f'disc_reason_{disp_item.id}': '2 units missing in box',
        }, follow=True)
        self.assertEqual(res.status_code, 200)

        trf.refresh_from_db()
        self.assertEqual(trf.status, 'discrepancy_flagged')

        # Resolve discrepancy via web
        resolve_url = reverse('transfer_request_resolve_discrepancy', kwargs={'pk': trf.pk})
        res = self.client.post(resolve_url, {
            f'resolution_{trf_item.id}': 'writeoff_loss',
            f'notes_{trf_item.id}': 'Approved writeoff',
            'resolution_notes': 'Investigation complete - vendor credit claimed',
        }, follow=True)
        self.assertEqual(res.status_code, 200)

        trf.refresh_from_db()
        self.assertEqual(trf.status, 'resolved')

        # Test approval rules view
        rules_url = reverse('transfer_approval_rules')
        res = self.client.get(rules_url)
        self.assertEqual(res.status_code, 200)
        res = self.client.post(rules_url, {
            'name': 'Updated Policy',
            'is_active': 'on',
            'auto_approve_below_threshold': 'on',
            'min_value_threshold': '1000.00',
            'min_quantity_threshold': '100',
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        rule = TransferApprovalRule.objects.get(business=self.business)
        self.assertEqual(rule.name, 'Updated Policy')
        self.assertEqual(rule.min_value_threshold, Decimal('1000.00'))
