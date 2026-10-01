"""
Core Views Package
"""
from core.views.base import (
    ModuleEnabledRequiredMixin,
    CSVExportMixin,
    CoreListView,
    CoreDetailView,
    CoreCreateView,
    CoreUpdateView,
    CoreDeleteView,
)
from core.scoping import CompanyBranchScopeMixin
from core.views.modules import (
    ModuleControlView,
    ModuleToggleView,
)
from core.views.dashboard import (
    PlatformDashboardView,
    SwitchBranchView,
)
from core.views.jobs import (
    JobListView,
    JobRetryView,
)
from core.views.audit import (
    AuditLogListView,
)
from core.views.notifications import (
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
)
from core.views.events import (
    OutboxEventListView,
    OutboxEventRetryView,
)
from core.views.workflows import (
    ApprovalInboxView,
    ApprovalProcessView,
)

__all__ = [
    'ModuleEnabledRequiredMixin',
    'CSVExportMixin',
    'CoreListView',
    'CoreDetailView',
    'CoreCreateView',
    'CoreUpdateView',
    'CoreDeleteView',
    'ModuleControlView',
    'ModuleToggleView',
    'PlatformDashboardView',
    'SwitchBranchView',
    'JobListView',
    'JobRetryView',
    'AuditLogListView',
    'NotificationListView',
    'NotificationMarkReadView',
    'NotificationMarkAllReadView',
    'OutboxEventListView',
    'OutboxEventRetryView',
    'ApprovalInboxView',
    'ApprovalProcessView',
]
