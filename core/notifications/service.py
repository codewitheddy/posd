"""
Platform Notification Dispatcher Service
Handles in-app notifications, email dispatch, and pluggable SMS/WhatsApp channels.
"""
import logging
from typing import Optional
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import QuerySet
from core.models.notifications import Notification
from core.models.organization import Company

logger = logging.getLogger(__name__)


def send_notification(
    recipient,
    title: str,
    message: str,
    notification_type: str = Notification.TYPE_INFO,
    channel: str = Notification.CHANNEL_IN_APP,
    link_url: str = '',
    company: Optional[Company] = None,
) -> Notification:
    """
    Send a notification to a user across the requested delivery channel.
    """
    notif = Notification.objects.create(
        recipient=recipient,
        company=company,
        title=title,
        message=message,
        notification_type=notification_type,
        channel=channel,
        link_url=link_url,
    )

    # Deliver via Channel
    if channel == Notification.CHANNEL_EMAIL:
        if recipient.email:
            try:
                send_mail(
                    subject=f"[{company.name if company else 'Platform'}] {title}",
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient.email],
                    fail_silently=True,
                )
                logger.info("Email notification sent to %s", recipient.email)
            except Exception as e:
                logger.error("Failed to send email notification to %s: %s", recipient.email, e)

    elif channel in (Notification.CHANNEL_SMS, Notification.CHANNEL_WHATSAPP):
        # Pluggable SMS/WhatsApp hook (e.g. Africa's Talking / Twilio)
        phone = getattr(recipient, 'core_profile', None) and recipient.core_profile.phone
        logger.info("[SMS/WhatsApp Provider Stub] Queued %s to %s (%s): %s", channel, recipient.username, phone, message)

    return notif


def get_unread_notifications(user) -> QuerySet:
    """Return all unread notifications for a user."""
    if not user or not user.is_authenticated:
        return Notification.objects.none()
    return Notification.objects.filter(recipient=user, is_read=False)


def mark_all_notifications_as_read(user) -> int:
    """Mark all unread notifications for a user as read."""
    if not user or not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
