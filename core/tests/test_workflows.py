"""
Unit Tests for Generic Approval Workflow Engine
"""
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from core.models.organization import Company, Branch, CompanyMembership
from core.models.workflows import (
    WorkflowDefinition,
    WorkflowStep,
    ApprovalRequest,
    ApprovalAction,
)
from core.models.events import OutboxEvent
from core.workflows.engine import (
    submit_for_approval,
    process_approval,
    can_user_approve_step,
)


class ApprovalWorkflowTests(TestCase):
    """Test suite for multi-step approval workflows."""

    def setUp(self):
        self.company = Company.objects.create(name='Workflow Corp', slug='workflow-corp')
        self.branch = Branch.objects.create(company=self.company, name='Main Branch', code='MAIN')

        # Users
        self.submitter = User.objects.create_user(username='requester', email='req@corp.com')
        self.manager = User.objects.create_user(username='manager', email='mgr@corp.com')
        self.director = User.objects.create_user(username='director', email='dir@corp.com')
        self.unauthorized = User.objects.create_user(username='stranger', email='stranger@corp.com')

        # Memberships
        CompanyMembership.objects.create(company=self.company, user=self.submitter, role=CompanyMembership.ROLE_STAFF)
        CompanyMembership.objects.create(company=self.company, user=self.manager, role=CompanyMembership.ROLE_MANAGER)
        CompanyMembership.objects.create(company=self.company, user=self.director, role=CompanyMembership.ROLE_OWNER)
        CompanyMembership.objects.create(company=self.company, user=self.unauthorized, role=CompanyMembership.ROLE_STAFF)

        # Create 2-step Workflow Definition for Branch changes
        self.content_type = ContentType.objects.get_for_model(Branch)
        self.workflow = WorkflowDefinition.objects.create(
            company=self.company,
            name='Branch Modification Approval',
            code='branch_mod',
            content_type=self.content_type,
        )
        self.step1 = WorkflowStep.objects.create(
            workflow=self.workflow,
            step_number=1,
            name='Manager Review',
            approver_role='manager',
        )
        self.step2 = WorkflowStep.objects.create(
            workflow=self.workflow,
            step_number=2,
            name='Director Authorization',
            approver_role='owner',
        )

    def test_workflow_submission_and_step_progression(self):
        """Test submitting for approval and progressing through 2 approval steps."""
        # 1. Submit for approval
        req = submit_for_approval(
            instance=self.branch,
            workflow_code='branch_mod',
            requested_by=self.submitter,
            submission_notes='Requesting branch budget increase',
            company=self.company,
        )

        self.assertIsNotNone(req.pk)
        self.assertEqual(req.status, ApprovalRequest.STATUS_PENDING)
        self.assertEqual(req.current_step, self.step1)

        # 2. Unauthorized user attempts to approve step 1 -> PermissionDenied
        with self.assertRaises(PermissionDenied):
            process_approval(
                request_id=req.id,
                actor=self.unauthorized,
                action='approve',
            )

        # 3. Manager approves Step 1 -> Advances to Step 2
        req = process_approval(
            request_id=req.id,
            actor=self.manager,
            action='approve',
            comments='Looks good from management perspective',
        )
        self.assertEqual(req.status, ApprovalRequest.STATUS_PENDING)
        self.assertEqual(req.current_step, self.step2)

        # 4. Director approves Step 2 -> Final Approval!
        req = process_approval(
            request_id=req.id,
            actor=self.director,
            action='approve',
            comments='Authorized by Director',
        )
        self.assertEqual(req.status, ApprovalRequest.STATUS_APPROVED)
        self.assertIsNotNone(req.completed_at)

        # Check domain event was published
        event = OutboxEvent.objects.filter(
            event_name='core.workflow_completed.v1',
            company=self.company,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload['request_id'], req.id)

    def test_workflow_rejection(self):
        """Test rejecting an approval request."""
        req = submit_for_approval(
            instance=self.branch,
            workflow_code='branch_mod',
            requested_by=self.submitter,
            company=self.company,
        )

        req = process_approval(
            request_id=req.id,
            actor=self.manager,
            action='reject',
            comments='Budget exceeded limit',
        )

        self.assertEqual(req.status, ApprovalRequest.STATUS_REJECTED)
        self.assertIsNotNone(req.completed_at)

        # Check domain event was published
        event = OutboxEvent.objects.filter(
            event_name='core.workflow_rejected.v1',
            company=self.company,
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload['reason'], 'Budget exceeded limit')
