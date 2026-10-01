"""
Generic Approval Workflow Engine
Multi-level approvals with role-based routing, delegation, and notification hooks.
"""
import importlib
import logging
from typing import Optional
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from core.models.organization import Company
from core.models.workflows import (
    WorkflowDefinition,
    WorkflowStep,
    ApprovalRequest,
    ApprovalAction,
)
from core.events.bus import (
    publish,
    EVENT_WORKFLOW_COMPLETED,
    EVENT_WORKFLOW_REJECTED,
)
from core.notifications.service import send_notification

logger = logging.getLogger(__name__)


def can_user_approve_step(user: User, step: WorkflowStep, company: Company) -> bool:
    """Check if the user is authorized to approve the current step."""
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # Check designated individual
    if step.approver_user_id and step.approver_user_id == user.id:
        return True

    # Check explicit permission
    if step.approver_permission and user.has_perm(step.approver_permission):
        return True

    # Check company membership role
    if step.approver_role:
        membership = company.memberships.filter(user=user, is_active=True).first()
        if membership:
            if membership.is_admin_or_owner:
                return True
            if membership.role == step.approver_role:
                return True

    return False


def submit_for_approval(
    instance,
    workflow_code: str,
    requested_by: User,
    submission_notes: str = '',
    company: Optional[Company] = None,
) -> ApprovalRequest:
    """
    Submit an entity into a multi-step approval workflow.
    """
    content_type = ContentType.objects.get_for_model(instance)
    object_id = str(instance.pk)

    if not company and hasattr(instance, 'company'):
        company = getattr(instance, 'company', None)
    if not company:
        raise ValidationError("Workflow submission requires a valid Company.")

    workflow = WorkflowDefinition.objects.filter(
        company=company,
        code=workflow_code,
        is_active=True,
    ).first()

    if not workflow:
        raise ValidationError(f"Workflow '{workflow_code}' is not configured for {company.name}.")

    first_step = workflow.steps.order_by('step_number').first()

    with transaction.atomic():
        request_obj = ApprovalRequest.objects.create(
            workflow=workflow,
            company=company,
            content_type=content_type,
            object_id=object_id,
            requested_by=requested_by,
            current_step=first_step,
            status=ApprovalRequest.STATUS_PENDING,
            submission_notes=submission_notes,
        )

        logger.info("Created approval request #%s for %s #%s", request_obj.id, content_type.model, object_id)

    return request_obj


def process_approval(
    request_id: int,
    actor: User,
    action: str,
    comments: str = '',
    delegated_to: Optional[User] = None,
) -> ApprovalRequest:
    """
    Process an approval action (approve, reject, delegate).
    Advances step or completes workflow.
    """
    if action not in (ApprovalAction.ACTION_APPROVE, ApprovalAction.ACTION_REJECT, ApprovalAction.ACTION_DELEGATE):
        raise ValidationError(f"Invalid approval action: {action}")

    with transaction.atomic():
        req = ApprovalRequest.objects.select_for_update().get(id=request_id)

        if req.status != ApprovalRequest.STATUS_PENDING:
            raise ValidationError(f"Approval request #{req.id} is already {req.get_status_display()}.")

        current_step = req.current_step
        if not current_step:
            raise ValidationError("Approval request has no active step.")

        if not can_user_approve_step(actor, current_step, req.company):
            raise PermissionDenied(f"User {actor.username} is not authorized to approve step '{current_step.name}'.")

        # Record Action Audit Log
        ApprovalAction.objects.create(
            request=req,
            step=current_step,
            actor=actor,
            action=action,
            comments=comments,
            delegated_to=delegated_to,
        )

        if action == ApprovalAction.ACTION_APPROVE:
            # Check for subsequent step
            next_step = req.workflow.steps.filter(step_number__gt=current_step.step_number).order_by('step_number').first()

            if next_step:
                # Advance to next step
                req.current_step = next_step
                req.save(update_fields=['current_step', 'updated_at'])
                logger.info("Approval #%s advanced to step: %s", req.id, next_step.name)
            else:
                # Final step completed -> Approved!
                req.status = ApprovalRequest.STATUS_APPROVED
                req.completed_at = timezone.now()
                req.save(update_fields=['status', 'completed_at', 'updated_at'])

                # Publish domain event
                publish(
                    EVENT_WORKFLOW_COMPLETED,
                    {
                        'request_id': req.id,
                        'workflow_code': req.workflow.code,
                        'entity_type': req.content_type.model,
                        'entity_id': req.object_id,
                        'approved_by_id': actor.id,
                    },
                    company=req.company,
                )

                # Execute automatic completion callback if defined
                if req.workflow.auto_execute_service:
                    try:
                        mod_name, func_name = req.workflow.auto_execute_service.rsplit('.', 1)
                        mod = importlib.import_module(mod_name)
                        func = getattr(mod, func_name)
                        func(req.content_object, req)
                    except Exception as e:
                        logger.error("Auto execute service failed for workflow #%s: %s", req.id, e)

                # Notify submitter
                send_notification(
                    recipient=req.requested_by,
                    title="Request Approved",
                    message=f"Your request for {req.content_type.model} #{req.object_id} was approved by {actor.get_full_name() or actor.username}.",
                    company=req.company,
                )

        elif action == ApprovalAction.ACTION_REJECT:
            req.status = ApprovalRequest.STATUS_REJECTED
            req.completed_at = timezone.now()
            req.save(update_fields=['status', 'completed_at', 'updated_at'])

            # Publish domain event
            publish(
                EVENT_WORKFLOW_REJECTED,
                {
                    'request_id': req.id,
                    'workflow_code': req.workflow.code,
                    'entity_type': req.content_type.model,
                    'entity_id': req.object_id,
                    'rejected_by_id': actor.id,
                    'reason': comments,
                },
                company=req.company,
            )

            # Notify submitter
            send_notification(
                recipient=req.requested_by,
                title="Request Rejected",
                message=f"Your request for {req.content_type.model} #{req.object_id} was rejected. Reason: {comments}",
                company=req.company,
            )

        elif action == ApprovalAction.ACTION_DELEGATE:
            if not delegated_to:
                raise ValidationError("Delegation requires a target user.")
            current_step.approver_user = delegated_to
            current_step.save(update_fields=['approver_user'])

            send_notification(
                recipient=delegated_to,
                title="Approval Delegated to You",
                message=f"{actor.username} delegated an approval request for {req.content_type.model} #{req.object_id} to you.",
                company=req.company,
            )

        return req


def get_pending_approvals_for_user(user: User, company: Optional[Company] = None) -> QuerySet:
    """Return all pending approval requests actionable by the user."""
    if not user or not user.is_authenticated:
        return ApprovalRequest.objects.none()

    qs = ApprovalRequest.objects.filter(status=ApprovalRequest.STATUS_PENDING)
    if company:
        qs = qs.filter(company=company)

    if user.is_superuser:
        return qs

    # Filter by user assignment or role
    return qs.filter(
        Q(current_step__approver_user=user) |
        Q(current_step__approver_role__isnull=False)
    )
