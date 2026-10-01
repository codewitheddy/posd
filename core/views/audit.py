"""
Backoffice Unified Audit Log Views
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from core.models.audit import AuditLog
from core.views.base import CoreListView
from core.views.modules import AdminRequiredMixin


class AuditLogListView(AdminRequiredMixin, CoreListView):
    """View and inspect immutable system audit trail."""
    model = AuditLog
    template_name = 'core/audit/audit_list.html'
    context_object_name = 'audit_logs'
    paginate_by = 50
    company_field = 'company'
    module_key = 'core'

    def get_queryset(self):
        qs = super().get_queryset()
        action = self.request.GET.get('action')
        if action:
            qs = qs.filter(action=action)
        search = self.request.GET.get('q')
        if search:
            qs = qs.filter(object_repr__icontains=search)
        return qs.select_related('user', 'company', 'content_type').order_by('-timestamp')
