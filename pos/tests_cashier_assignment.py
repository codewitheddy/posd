from decimal import Decimal
from datetime import date, timedelta
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from pos.models import (
    Business, BusinessMembership, Branch, BranchMembership, POSTerminal,
    CashierTillAssignment, CashierTransferRequest, CashierAssignmentAuditLog
)
from pos.cashier_assignment_service import CashierAssignmentService


class CashierAssignmentSystemTests(TestCase):
    """
    Comprehensive test suite for the multi-branch cashier-to-till assignment
    and cross-branch transfer system.
    """

    def setUp(self):
        # 1. Users
        self.owner = User.objects.create_user(username='business_owner', password='password123')
        self.mgr_branch_a = User.objects.create_user(username='manager_a', password='password123')
        self.mgr_branch_b = User.objects.create_user(username='manager_b', password='password123')
        self.cashier1 = User.objects.create_user(username='cashier_alice', password='password123')
        self.cashier2 = User.objects.create_user(username='cashier_bob', password='password123')
        self.cashier3 = User.objects.create_user(username='cashier_charlie', password='password123')

        # 2. Business
        self.business = Business.objects.create(
            name='Apex Supermarkets Chain',
            slug='apex-chain',
            owner=self.owner,
        )

        BusinessMembership.objects.create(user=self.owner, business=self.business, role='owner')
        BusinessMembership.objects.create(user=self.mgr_branch_a, business=self.business, role='manager')
        BusinessMembership.objects.create(user=self.mgr_branch_b, business=self.business, role='manager')
        BusinessMembership.objects.create(user=self.cashier1, business=self.business, role='cashier')
        BusinessMembership.objects.create(user=self.cashier2, business=self.business, role='cashier')
        BusinessMembership.objects.create(user=self.cashier3, business=self.business, role='cashier')

        # 3. Branches
        self.branch_a = Branch.objects.create(
            business=self.business,
            name='Nairobi CBD Branch',
            code='BR-CBD',
            is_default=True,
            is_active=True,
        )
        self.branch_b = Branch.objects.create(
            business=self.business,
            name='Westlands Branch',
            code='BR-WEST',
            is_active=True,
        )

        # 4. Branch Memberships
        BranchMembership.objects.create(user=self.mgr_branch_a, branch=self.branch_a, role='branch_manager', is_home_branch=True, is_active=True)
        BranchMembership.objects.create(user=self.mgr_branch_b, branch=self.branch_b, role='branch_manager', is_home_branch=True, is_active=True)
        
        # Cashier 1 & 3 home branch is Branch A
        self.alice_home_mem = BranchMembership.objects.create(
            user=self.cashier1, branch=self.branch_a, role='cashier', is_home_branch=True, is_active=True
        )
        self.charlie_home_mem = BranchMembership.objects.create(
            user=self.cashier3, branch=self.branch_a, role='cashier', is_home_branch=True, is_active=True
        )
        # Cashier 2 home branch is Branch B
        self.bob_home_mem = BranchMembership.objects.create(
            user=self.cashier2, branch=self.branch_b, role='cashier', is_home_branch=True, is_active=True
        )

        # 5. POSTerminals (Tills)
        self.till_a1 = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch_a,
            name='CBD Till 1',
            terminal_code='CBD-T1',
            device_token='token-cbd-1',
            operational_status='available',
            is_active=True,
        )
        self.till_a2 = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch_a,
            name='CBD Till 2',
            terminal_code='CBD-T2',
            device_token='token-cbd-2',
            operational_status='available',
            is_active=True,
        )
        self.till_b1 = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch_b,
            name='Westlands Till 1',
            terminal_code='WEST-T1',
            device_token='token-west-1',
            operational_status='available',
            is_active=True,
        )

        self.client = APIClient()

    # ── TEST 1: Cross-Branch Transfer Request & Approval Lifecycle ────────────

    def test_temporary_transfer_lifecycle(self):
        """Test requesting, approving, and verifying temporary transfer."""
        today = timezone.localdate()
        start_date = today
        end_date = today + timedelta(days=7)

        # Request transfer from CBD (Branch A) to Westlands (Branch B)
        transfer = CashierAssignmentService.request_transfer(
            business=self.business,
            cashier=self.cashier1,
            from_branch=self.branch_a,
            to_branch=self.branch_b,
            transfer_type='temporary',
            start_date=start_date,
            end_date=end_date,
            requested_by=self.mgr_branch_a,
            reason='Staff shortage at Westlands'
        )

        self.assertEqual(transfer.status, 'pending')
        self.assertEqual(transfer.transfer_type, 'temporary')

        # Rule 2: Origin manager (or other unauthorized user) CANNOT approve
        with self.assertRaises(PermissionError):
            CashierAssignmentService.approve_transfer(transfer, approved_by=self.cashier2)

        # Rule 2: Receiving branch manager CAN approve
        approved_transfer = CashierAssignmentService.approve_transfer(
            transfer, approved_by=self.mgr_branch_b, notes='Approved by Westlands Mgr'
        )
        self.assertEqual(approved_transfer.status, 'approved')
        self.assertEqual(approved_transfer.approved_by, self.mgr_branch_b)

        # Verify active branch during transfer window resolves to Branch B
        active_branch, is_temp, active_req = CashierAssignmentService.get_active_cashier_branch(self.cashier1, target_date=today + timedelta(days=2))
        self.assertEqual(active_branch, self.branch_b)
        self.assertTrue(is_temp)
        self.assertEqual(active_req, approved_transfer)

        # Audit log verified
        audit_exists = CashierAssignmentAuditLog.objects.filter(
            cashier=self.cashier1, action='transfer_approved'
        ).exists()
        self.assertTrue(audit_exists)

    def test_temporary_transfer_auto_reversion(self):
        """Test that after end_date, the cashier automatically reverts to their home branch."""
        today = timezone.localdate()
        start_date = today - timedelta(days=10)
        end_date = today - timedelta(days=2)  # Expired 2 days ago

        transfer = CashierTransferRequest.objects.create(
            business=self.business,
            cashier=self.cashier1,
            from_branch=self.branch_a,
            to_branch=self.branch_b,
            transfer_type='temporary',
            start_date=start_date,
            end_date=end_date,
            status='approved',
            requested_by=self.mgr_branch_a,
            approved_by=self.mgr_branch_b,
        )

        # Target date is TODAY (after end_date) -> should revert to Branch A (Home)
        active_branch, is_temp, active_req = CashierAssignmentService.get_active_cashier_branch(self.cashier1, target_date=today)
        self.assertEqual(active_branch, self.branch_a)
        self.assertFalse(is_temp)
        self.assertIsNone(active_req)

    def test_permanent_transfer_updates_home_branch(self):
        """Test permanent transfer updates home branch membership."""
        today = timezone.localdate()
        transfer = CashierAssignmentService.request_transfer(
            business=self.business,
            cashier=self.cashier1,
            from_branch=self.branch_a,
            to_branch=self.branch_b,
            transfer_type='permanent',
            start_date=today,
            requested_by=self.mgr_branch_a,
            reason='Permanent relocation'
        )
        CashierAssignmentService.approve_transfer(transfer, approved_by=self.mgr_branch_b)

        # Check membership
        home_mems = BranchMembership.objects.filter(user=self.cashier1, is_home_branch=True)
        self.assertEqual(home_mems.count(), 1)
        self.assertEqual(home_mems.first().branch, self.branch_b)

    def test_transfer_rejection_and_cancellation(self):
        """Test rejection by receiving manager and cancellation by requester."""
        today = timezone.localdate()
        # Test Rejection
        transfer1 = CashierAssignmentService.request_transfer(
            business=self.business, cashier=self.cashier1,
            from_branch=self.branch_a, to_branch=self.branch_b,
            transfer_type='temporary', start_date=today, end_date=today + timedelta(days=3),
            requested_by=self.mgr_branch_a, reason='Temporary help'
        )
        rejected = CashierAssignmentService.reject_transfer(transfer1, rejected_by=self.mgr_branch_b, rejection_reason='No vacancy')
        self.assertEqual(rejected.status, 'rejected')
        self.assertEqual(rejected.rejection_reason, 'No vacancy')

        # Test Cancellation
        transfer2 = CashierAssignmentService.request_transfer(
            business=self.business, cashier=self.cashier1,
            from_branch=self.branch_a, to_branch=self.branch_b,
            transfer_type='temporary', start_date=today, end_date=today + timedelta(days=3),
            requested_by=self.mgr_branch_a, reason='Temporary help'
        )
        cancelled = CashierAssignmentService.cancel_transfer(transfer2, user=self.mgr_branch_a, reason='No longer needed')
        self.assertEqual(cancelled.status, 'cancelled')

    # ── TEST 2: Till Availability & Shift Scheduling ──────────────────────────

    def test_till_availability_and_assignment(self):
        """Test scheduling a cashier to a till and preventing overlapping assignments."""
        now = timezone.now()
        shift_start = now + timedelta(hours=1)
        shift_end = now + timedelta(hours=9)

        # 1. Successful assignment for Alice on Till A1
        assignment1 = CashierAssignmentService.assign_cashier_to_till(
            business=self.business,
            cashier=self.cashier1,
            terminal=self.till_a1,
            branch=self.branch_a,
            shift_start=shift_start,
            shift_end=shift_end,
            assigned_by=self.mgr_branch_a,
            hourly_rate=Decimal('250.00'),
            notes='Morning shift'
        )
        self.assertEqual(assignment1.status, 'scheduled')
        self.assertEqual(assignment1.hourly_rate, Decimal('250.00'))

        # 2. Prevent overlapping assignment on the same till for Charlie (Till Conflict)
        overlapping_start = shift_start + timedelta(hours=2)
        overlapping_end = shift_end + timedelta(hours=2)
        with self.assertRaises(ValueError) as ctx:
            CashierAssignmentService.assign_cashier_to_till(
                business=self.business,
                cashier=self.cashier3,  # Charlie is also active at Branch A
                terminal=self.till_a1,  # Same till
                branch=self.branch_a,
                shift_start=overlapping_start,
                shift_end=overlapping_end,
                assigned_by=self.mgr_branch_a,
            )
        self.assertIn("already assigned", str(ctx.exception))

        # 3. Prevent overlapping assignment for Alice on another till (Cashier Conflict)
        with self.assertRaises(ValueError) as ctx:
            CashierAssignmentService.assign_cashier_to_till(
                business=self.business,
                cashier=self.cashier1,  # Alice already scheduled on Till 1
                terminal=self.till_a2,  # Different till
                branch=self.branch_a,
                shift_start=overlapping_start,
                shift_end=overlapping_end,
                assigned_by=self.mgr_branch_a,
            )
        self.assertIn("already scheduled", str(ctx.exception))

    def test_cross_branch_cashier_conflict_prevention(self):
        """Test that a cashier cannot be scheduled across two branches during overlapping hours."""
        now = timezone.now()
        shift_start = now + timedelta(hours=1)
        shift_end = now + timedelta(hours=5)

        # Give Alice membership in Branch B as well for testing
        BranchMembership.objects.create(user=self.cashier1, branch=self.branch_b, role='cashier', is_active=True)

        # Assign Alice to Till A1 at Nairobi CBD
        CashierAssignmentService.assign_cashier_to_till(
            business=self.business,
            cashier=self.cashier1,
            terminal=self.till_a1,
            branch=self.branch_a,
            shift_start=shift_start,
            shift_end=shift_end,
            assigned_by=self.mgr_branch_a,
        )

        # Attempt to assign Alice to Westlands Till B1 at same time -> Must fail
        with self.assertRaises(ValueError) as ctx:
            CashierAssignmentService.assign_cashier_to_till(
                business=self.business,
                cashier=self.cashier1,
                terminal=self.till_b1,
                branch=self.branch_b,
                shift_start=shift_start + timedelta(minutes=30),
                shift_end=shift_end + timedelta(minutes=30),
                assigned_by=self.mgr_branch_b,
            )
        self.assertIn("already scheduled at", str(ctx.exception))

    def test_inactive_or_offline_till_rejected(self):
        """Test that assigning an offline or inactive till raises an error."""
        now = timezone.now()
        self.till_a2.operational_status = 'offline'
        self.till_a2.save()

        with self.assertRaises(ValueError) as ctx:
            CashierAssignmentService.assign_cashier_to_till(
                business=self.business,
                cashier=self.cashier1,
                terminal=self.till_a2,
                branch=self.branch_a,
                shift_start=now + timedelta(hours=1),
                shift_end=now + timedelta(hours=5),
            )
        self.assertIn("offline", str(ctx.exception))

    # ── TEST 3: Shift Activation, Till Release & Labor Reporting ─────────────

    def test_activation_and_release_lifecycle(self):
        """Test activating a till assignment, updating terminal status, and releasing till."""
        now = timezone.now()
        assignment = CashierTillAssignment.objects.create(
            business=self.business,
            cashier=self.cashier1,
            terminal=self.till_a1,
            branch=self.branch_a,
            shift_start=now - timedelta(hours=4),
            shift_end=now + timedelta(hours=4),
            hourly_rate=Decimal('300.00'),
            status='scheduled'
        )

        # Activate
        CashierAssignmentService.activate_assignment(assignment, actual_start=now - timedelta(hours=4))
        assignment.refresh_from_db()
        self.till_a1.refresh_from_db()
        self.assertEqual(assignment.status, 'active')
        self.assertEqual(self.till_a1.operational_status, 'in_use')

        # Release
        CashierAssignmentService.release_till(assignment, actual_end=now)
        assignment.refresh_from_db()
        self.till_a1.refresh_from_db()
        self.assertEqual(assignment.status, 'completed')
        self.assertEqual(self.till_a1.operational_status, 'available')
        
        # Hours worked = 4.0, Labor Cost = 4.0 * 300 = 1200.00
        self.assertEqual(assignment.calculate_hours_worked(), Decimal('4.00'))
        self.assertEqual(assignment.calculate_labor_cost(), Decimal('1200.00'))

    def test_branch_labor_report(self):
        """Test labor report calculation aggregated by branch."""
        now = timezone.now()
        # Shift 1 for Alice: 4 hours @ 200/hr = 800
        CashierTillAssignment.objects.create(
            business=self.business,
            cashier=self.cashier1,
            terminal=self.till_a1,
            branch=self.branch_a,
            shift_start=now - timedelta(hours=8),
            shift_end=now - timedelta(hours=4),
            actual_start=now - timedelta(hours=8),
            actual_end=now - timedelta(hours=4),
            hourly_rate=Decimal('200.00'),
            status='completed'
        )

        # Shift 2 for Alice: 2 hours @ 200/hr = 400
        CashierTillAssignment.objects.create(
            business=self.business,
            cashier=self.cashier1,
            terminal=self.till_a2,
            branch=self.branch_a,
            shift_start=now - timedelta(hours=3),
            shift_end=now - timedelta(hours=1),
            actual_start=now - timedelta(hours=3),
            actual_end=now - timedelta(hours=1),
            hourly_rate=Decimal('200.00'),
            status='completed'
        )

        report = CashierAssignmentService.get_branch_labor_report(self.branch_a)
        self.assertEqual(report['total_shifts'], 2)
        self.assertEqual(report['total_hours_worked'], Decimal('6.00'))
        self.assertEqual(report['total_labor_cost'], Decimal('1200.00'))
        self.assertEqual(len(report['cashiers']), 1)
        self.assertEqual(report['cashiers'][0]['cashier_name'], self.cashier1.username)

    # ── TEST 4: REST API Endpoints ────────────────────────────────────────────

    def test_api_transfer_request_create_and_approve(self):
        """Test REST API for creating and approving transfers."""
        self.client.force_authenticate(user=self.owner)
        today = timezone.localdate()

        # POST cashier-transfers
        payload = {
            'business': self.business.id,
            'cashier': self.cashier1.id,
            'from_branch': self.branch_a.id,
            'to_branch': self.branch_b.id,
            'transfer_type': 'temporary',
            'start_date': str(today),
            'end_date': str(today + timedelta(days=5)),
            'reason': 'API Test Transfer',
        }
        url = reverse('cashiertransfer-list')
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transfer_id = response.data['id']

        # Action: approve
        approve_url = reverse('cashiertransfer-approve', kwargs={'pk': transfer_id})
        approve_res = self.client.post(approve_url, {'notes': 'API Approved'}, format='json')
        self.assertEqual(approve_res.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_res.data['status'], 'approved')

    def test_api_till_assignment_lifecycle(self):
        """Test REST API for assigning, activating, and releasing a till."""
        self.client.force_authenticate(user=self.owner)
        now = timezone.now()

        payload = {
            'business': self.business.id,
            'cashier': self.cashier1.id,
            'terminal': self.till_a1.id,
            'branch': self.branch_a.id,
            'shift_start': (now + timedelta(hours=1)).isoformat(),
            'shift_end': (now + timedelta(hours=9)).isoformat(),
            'hourly_rate': '250.00',
            'notes': 'API Assigned Shift',
        }
        url = reverse('tillassignment-list')
        create_res = self.client.post(url, payload, format='json')
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        assign_id = create_res.data['id']

        # Activate
        activate_url = reverse('tillassignment-activate', kwargs={'pk': assign_id})
        activate_res = self.client.post(activate_url, format='json')
        self.assertEqual(activate_res.status_code, status.HTTP_200_OK)
        self.assertEqual(activate_res.data['status'], 'active')

        # Release
        release_url = reverse('tillassignment-release', kwargs={'pk': assign_id})
        release_res = self.client.post(release_url, {'notes': 'Shift ended via API'}, format='json')
        self.assertEqual(release_res.status_code, status.HTTP_200_OK)
        self.assertEqual(release_res.data['status'], 'completed')

    def test_api_branch_till_status_and_labor_report(self):
        """Test GET till-status and labor-report endpoints."""
        self.client.force_authenticate(user=self.owner)

        status_url = reverse('api_branch_till_status', kwargs={'branch_id': self.branch_a.id})
        status_res = self.client.get(status_url)
        self.assertEqual(status_res.status_code, status.HTTP_200_OK)
        self.assertIn('total_tills', status_res.data)
        self.assertEqual(status_res.data['total_tills'], 2)

        labor_url = reverse('api_branch_labor_report', kwargs={'branch_id': self.branch_a.id})
        labor_res = self.client.get(labor_url)
        self.assertEqual(labor_res.status_code, status.HTTP_200_OK)
        self.assertIn('total_hours_worked', labor_res.data)
        self.assertIn('total_labor_cost', labor_res.data)

    # ── TEST 5: Web Dashboard UI & View Actions ───────────────────────────────

    def test_web_dashboard_view(self):
        """Test web dashboard rendering and context."""
        self.client.force_login(user=self.owner)
        url = reverse('cashier_assignment_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Till &amp; Cashier Allocation")
        self.assertContains(response, "CBD-T1")
