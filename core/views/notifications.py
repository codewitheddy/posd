"""
User Notification Views
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView
from core.models.notifications import Notification
from core.notifications.service import mark_all_notifications_as_read


class NotificationListView(LoginRequiredMixin, ListView):
    """List all notifications for the current user."""
    model = Notification
    template_name = 'core/notifications/notification_list.html'
    context_object_name = 'notifications'
    paginate_by = 30

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')


class NotificationMarkReadView(LoginRequiredMixin, View):
    """Mark a single notification as read."""

    def post(self, request, pk):
        notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notif.mark_as_read()
        if notif.link_url:
            return redirect(notif.link_url)
        return redirect('core_notification_list')


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    """Mark all notifications for the user as read."""

    def post(self, request):
        mark_all_notifications_as_read(request.user)
        return redirect('core_notification_list')
