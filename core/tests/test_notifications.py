"""
Unit Tests for Notification Dispatcher and Context Processor
"""
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from core.models.notifications import Notification
from core.models.organization import Company
from core.notifications.service import (
    send_notification,
    get_unread_notifications,
    mark_all_notifications_as_read,
)
from core.context_processors import core_platform_context


class NotificationTests(TestCase):
    """Test suite for notifications and context processor."""

    def setUp(self):
        self.factory = RequestFactory()
        self.company = Company.objects.create(name='Prime Ltd', slug='prime-ltd')
        self.user = User.objects.create_user(username='notify_user', email='notify@prime.com')

    def test_send_in_app_notification(self):
        """Test sending and reading in-app notifications."""
        notif = send_notification(
            recipient=self.user,
            title='Low Stock Alert',
            message='Milk 500ml is below reorder level.',
            notification_type=Notification.TYPE_WARNING,
            company=self.company,
        )

        self.assertIsNotNone(notif.pk)
        self.assertFalse(notif.is_read)

        unread = get_unread_notifications(self.user)
        self.assertEqual(unread.count(), 1)

        # Mark as read
        notif.mark_as_read()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)
        self.assertEqual(get_unread_notifications(self.user).count(), 0)

    def test_mark_all_as_read(self):
        """Test bulk marking all user notifications as read."""
        for i in range(3):
            send_notification(
                recipient=self.user,
                title=f"Alert #{i}",
                message=f"Message content #{i}",
            )

        self.assertEqual(get_unread_notifications(self.user).count(), 3)
        updated_count = mark_all_notifications_as_read(self.user)
        self.assertEqual(updated_count, 3)
        self.assertEqual(get_unread_notifications(self.user).count(), 0)

    def test_core_platform_context_processor(self):
        """Test context processor injects unread notifications."""
        send_notification(
            recipient=self.user,
            title='Approval Required',
            message='Leave request submitted by John Doe',
        )

        request = self.factory.get('/')
        request.user = self.user
        request.company = self.company

        ctx = core_platform_context(request)
        self.assertEqual(ctx['unread_notifications_count'], 1)
        self.assertEqual(len(ctx['unread_notifications_list']), 1)
        self.assertEqual(ctx['platform_company'], self.company)
