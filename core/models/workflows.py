"""
Generic Approval Workflow Engine Models
Configurable multi-level approval workflows for HR, POS, and Accounting.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from core.models.base import TimeStampedModel


class WorkflowDefinition(TimeStampedModel):
    """
    Template definition for a multi-step approval process.
    """
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='workflows',
        db_index=True,
    )
    name = models.CharField(max_length=100, help_text="e.g. 'Staff Leave Approval', 'Large POS Refund'")
    code = models.CharField(max_length=50, db_index=True, help_text="e.g. 'hr_leave', 'pos_refund', 'supplier_payment'")
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Target entity model being approved",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    auto_execute_service = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional dotted service called when final step is approved",
    )

    class Meta:
        verbose_name = 'Workflow Definition'
        verbose_name_plural = 'Workflow Definitions'
        unique_together = [['company', 'code']]
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.company.name})"


class WorkflowStep(models.Model):
    """
    Individual sequential step in an approval workflow.
    """
    workflow = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.CASCADE,
        related_name='steps',
        db_index=True,
    )
    step_number = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=100, help_text="e.g. 'Department Head Review', 'Director Signoff'")
    approver_role = models.CharField(
        max_length=50,
        blank=True,
        help_text="Role allowed to approve e.g. 'manager', 'admin', 'owner'",
    )
    approver_permission = models.CharField(
        max_length=100,
        blank=True,
        help_text="Permission codename required e.g. 'hr.approve_leave'",
    )
    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text="Specific user assignment (overrides role if set)",
    )
    timeout_hours = models.PositiveIntegerField(default=48)

    class Meta:
        verbose_name = 'Workflow Step'
        verbose_name_plural = 'Workflow Steps'
        unique_together = [['workflow', 'step_number']]
        ordering = ['workflow', 'step_number']

    def __str__(self):
        return f"Step {self.step_number}: {self.name} ({self.workflow.name})"


class ApprovalRequest(TimeStampedModel):
    """
    Live approval instance tracking the approval state of a specific document/entity.
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Approval'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    workflow = models.ForeignKey(
        WorkflowDefinition,
        on_delete=models.PROTECT,
        related_name='requests',
        db_index=True,
    )
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name='approval_requests',
        db_index=True,
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        db_index=True,
    )
    object_id = models.CharField(max_length=100, db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='submitted_approvals',
    )
    current_step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    submission_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Approval Request'
        verbose_name_plural = 'Approval Requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'company']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"Approval for {self.content_type.model} #{self.object_id} [{self.get_status_display()}]"


class ApprovalAction(models.Model):
    """
    Audit log of decisions (Approve, Reject, Delegate) made on an ApprovalRequest.
    """
    ACTION_APPROVE = 'approve'
    ACTION_REJECT = 'reject'
    ACTION_DELEGATE = 'delegate'
    ACTION_ESCALATE = 'escalate'

    ACTION_CHOICES = [
        (ACTION_APPROVE, 'Approved'),
        (ACTION_REJECT, 'Rejected'),
        (ACTION_DELEGATE, 'Delegated'),
        (ACTION_ESCALATE, 'Escalated'),
    ]

    request = models.ForeignKey(
        ApprovalRequest,
        on_delete=models.CASCADE,
        related_name='actions',
        db_index=True,
    )
    step = models.ForeignKey(
        WorkflowStep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='approval_decisions',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    comments = models.TextField(blank=True)
    delegated_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Approval Action'
        verbose_name_plural = 'Approval Actions'
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.actor.username} {self.action} on Request #{self.request_id} @ {self.timestamp:%Y-%m-%d %H:%M}"
