"""
Backoffice Approval Workflow Views
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView
from core.models.workflows import ApprovalRequest
from core.workflows.engine import process_approval, get_pending_approvals_for_user
from core.scoping import get_current_company


class ApprovalInboxView(LoginRequiredMixin, ListView):
    """View pending approval requests actionable by the current user."""
    template_name = 'core/workflows/approval_inbox.html'
    context_object_name = 'approval_requests'
    paginate_by = 30

    def get_queryset(self):
        company = get_current_company(self.request)
        return get_pending_approvals_for_user(self.request.user, company).select_related(
            'workflow', 'requested_by', 'current_step', 'content_type'
        ).order_by('-created_at')


class ApprovalProcessView(LoginRequiredMixin, View):
    """Handle approval decisions (Approve, Reject, Delegate)."""

    def post(self, request, pk):
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')

        try:
            req = process_approval(
                request_id=pk,
                actor=request.user,
                action=action,
                comments=comments,
            )
            messages.success(request, f"Approval request #{req.id} {req.get_status_display().lower()} successfully.")
        except Exception as e:
            messages.error(request, f"Failed to process approval: {str(e)}")

        return redirect('core_approval_inbox')
