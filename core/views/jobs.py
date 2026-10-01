"""
Backoffice Job Queue Views
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from core.models.jobs import Job
from core.views.base import CoreListView
from core.views.modules import AdminRequiredMixin


class JobListView(AdminRequiredMixin, CoreListView):
    """View and monitor background queue jobs."""
    model = Job
    template_name = 'core/jobs/job_list.html'
    context_object_name = 'jobs'
    paginate_by = 25
    company_field = 'company'
    module_key = 'core'

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        search = self.request.GET.get('q')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs.order_by('-created_at')


class JobRetryView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Reset a failed or cancelled job to pending status for retry."""

    def post(self, request, job_id):
        job = get_object_or_404(Job, id=job_id)
        job.status = Job.STATUS_PENDING
        job.attempts = 0
        job.error_message = ''
        job.traceback = ''
        job.scheduled_at = timezone.now()
        job.save()
        messages.success(request, f"Job '{job.name}' queued for retry.")
        return redirect('core_job_list')
