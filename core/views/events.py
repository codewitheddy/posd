"""
Backoffice Outbox Event Views
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from core.models.events import OutboxEvent
from core.views.base import CoreListView
from core.views.modules import AdminRequiredMixin


class OutboxEventListView(AdminRequiredMixin, CoreListView):
    """View and inspect outbox event stream and delivery status."""
    model = OutboxEvent
    template_name = 'core/events/event_list.html'
    context_object_name = 'events'
    paginate_by = 50
    company_field = 'company'
    module_key = 'core'

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        search = self.request.GET.get('q')
        if search:
            qs = qs.filter(event_name__icontains=search)
        return qs.prefetch_related('deliveries').order_by('-created_at')


class OutboxEventRetryView(AdminRequiredMixin, View):
    """Reset a dead letter or failed outbox event for re-dispatch."""

    def post(self, request, pk):
        event = get_object_or_404(OutboxEvent, id=pk)
        event.status = OutboxEvent.STATUS_PENDING
        event.attempts = 0
        event.last_error = ''
        event.traceback = ''
        event.save()
        messages.success(request, f"Event '{event.event_name}' re-queued for dispatch.")
        return redirect('core_event_list')
