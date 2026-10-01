"""
Core Platform URLs
"""
from django.urls import path
from core.views import (
    PlatformDashboardView,
    ModuleControlView,
    ModuleToggleView,
    SwitchBranchView,
    JobListView,
    JobRetryView,
    AuditLogListView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    OutboxEventListView,
    OutboxEventRetryView,
    ApprovalInboxView,
    ApprovalProcessView,
)

urlpatterns = [
    path('dashboard/', PlatformDashboardView.as_view(), name='core_dashboard'),
    path('modules/', ModuleControlView.as_view(), name='core_module_list'),
    path('modules/<str:module_key>/toggle/', ModuleToggleView.as_view(), name='core_module_toggle'),
    path('branch/switch/<int:branch_id>/', SwitchBranchView.as_view(), name='core_switch_branch'),
    path('jobs/', JobListView.as_view(), name='core_job_list'),
    path('jobs/<uuid:job_id>/retry/', JobRetryView.as_view(), name='core_job_retry'),
    path('audit/', AuditLogListView.as_view(), name='core_audit_list'),
    path('notifications/', NotificationListView.as_view(), name='core_notification_list'),
    path('notifications/<int:pk>/read/', NotificationMarkReadView.as_view(), name='core_notification_read'),
    path('notifications/mark-all-read/', NotificationMarkAllReadView.as_view(), name='core_notification_mark_all_read'),
    path('events/', OutboxEventListView.as_view(), name='core_event_list'),
    path('events/<uuid:pk>/retry/', OutboxEventRetryView.as_view(), name='core_event_retry'),
    path('workflows/inbox/', ApprovalInboxView.as_view(), name='core_approval_inbox'),
    path('workflows/<int:pk>/process/', ApprovalProcessView.as_view(), name='core_approval_process'),
]
