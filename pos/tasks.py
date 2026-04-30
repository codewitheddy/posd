"""
Celery background tasks for heavy operations.

Offloads email sending, report generation, and data exports
from the request/response cycle.
"""
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


# ── Email tasks ───────────────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_campaign_emails(self, campaign_id):
    """
    Send campaign emails to all target customers.
    Replaces the synchronous loop in campaign_send view.
    """
    try:
        from .models import Campaign, Customer
        from .email_service import EmailService

        campaign = Campaign.objects.select_related('segment', 'business').get(pk=campaign_id)
        customers = (
            campaign.segment.get_customers()
            if campaign.segment
            else Customer.objects.filter(business=campaign.business, is_active=True)
        )

        email_service = EmailService(campaign.business)
        sent = failed = 0

        for customer in customers.only('id', 'email', 'name'):
            if not customer.email:
                continue
            try:
                email_service.send_custom_email(
                    to_email=customer.email,
                    subject=campaign.subject or campaign.name,
                    message=campaign.message,
                    customer_name=customer.name,
                )
                sent += 1
            except Exception as exc:
                logger.warning(f"Failed to email customer {customer.id}: {exc}")
                failed += 1

        campaign.status = 'sent'
        campaign.recipients_count = sent
        from django.utils import timezone
        campaign.sent_at = timezone.now()
        campaign.save(update_fields=['status', 'recipients_count', 'sent_at'])

        logger.info(f"Campaign {campaign_id}: sent={sent}, failed={failed}")
        return {'sent': sent, 'failed': failed}

    except Exception as exc:
        logger.error(f"Campaign {campaign_id} task failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_purchase_order_email(self, purchase_id):
    """Send purchase order email to supplier in background."""
    try:
        from .models import Purchase
        from .email_service import EmailService
        purchase = Purchase.objects.select_related('supplier', 'business').prefetch_related('items__product').get(pk=purchase_id)
        result = EmailService.send_purchase_order(purchase)
        logger.info(f"Purchase order email for {purchase_id}: {'sent' if result else 'skipped'}")
        return result
    except Exception as exc:
        logger.error(f"Purchase order email {purchase_id} failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_payment_confirmation_email(self, payment_id):
    """Send supplier payment confirmation in background."""
    try:
        from .models import SupplierPayment
        from .email_service import EmailService
        payment = SupplierPayment.objects.select_related('supplier', 'business', 'payment_method').get(pk=payment_id)
        result = EmailService.send_payment_confirmation(payment)
        logger.info(f"Payment confirmation email for {payment_id}: {'sent' if result else 'skipped'}")
        return result
    except Exception as exc:
        logger.error(f"Payment confirmation email {payment_id} failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_grn_notification_email(self, grn_id):
    """Send GRN notification to supplier in background."""
    try:
        from .models import GoodsReceivedNote
        from .email_service import EmailService
        grn = GoodsReceivedNote.objects.select_related('supplier', 'business', 'related_purchase').prefetch_related('items__product').get(pk=grn_id)
        result = EmailService.send_grn_notification(grn)
        logger.info(f"GRN notification email for {grn_id}: {'sent' if result else 'skipped'}")
        return result
    except Exception as exc:
        logger.error(f"GRN notification email {grn_id} failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def send_license_expiry_reminder(self, business_id, days_remaining):
    """Send license expiry reminder in background."""
    try:
        from .models import Business
        from .email_service import EmailService
        business = Business.objects.get(pk=business_id)
        result = EmailService.send_license_expiry_reminder(business, days_remaining)
        logger.info(f"License reminder for business {business_id}: {'sent' if result else 'skipped'}")
        return result
    except Exception as exc:
        logger.error(f"License reminder for business {business_id} failed: {exc}")
        raise self.retry(exc=exc)


# ── Report / export tasks ─────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=1)
def generate_analytics_report(self, business_id, report_type, days=30):
    """
    Pre-compute analytics and store in cache.
    Call this from a scheduled beat task or on-demand.
    """
    try:
        from .models import Business
        from .analytics_service import AnalyticsService
        from .cache_utils import set_dashboard_stats
        from django.utils import timezone

        business = Business.objects.get(pk=business_id)
        service = AnalyticsService(business)

        if report_type == 'dashboard':
            data = service.get_dashboard_summary(days=days)
            date_str = timezone.now().date().isoformat()
            set_dashboard_stats(business_id, date_str, data)
        elif report_type == 'sales_trends':
            data = service.get_sales_trends(days=days)
        elif report_type == 'best_sellers':
            data = service.get_best_sellers(days=days)
        else:
            data = {}

        logger.info(f"Analytics report '{report_type}' generated for business {business_id}")
        return data

    except Exception as exc:
        logger.error(f"Analytics report failed for business {business_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1)
def export_report_csv(self, business_id, report_type, params=None):
    """
    Generate a CSV export in the background and store result.
    Returns the CSV content as a string (store in cache/S3 for download).
    """
    import csv
    import io
    from django.core.cache import cache

    params = params or {}
    try:
        from .models import Business, Customer, Sale
        from django.db.models import Sum, Count, Q
        from django.utils import timezone

        business = Business.objects.get(pk=business_id)
        output = io.StringIO()
        writer = csv.writer(output)

        if report_type == 'top_customers':
            days = params.get('days', 90)
            since = timezone.now() - timezone.timedelta(days=days)
            customers = Customer.objects.filter(business=business).annotate(
                purchase_count=Count('purchases', filter=Q(purchases__date__gte=since)),
                amount_spent=Sum('purchases__total', filter=Q(purchases__date__gte=since)),
            ).filter(amount_spent__gt=0).order_by('-amount_spent')[:500]

            writer.writerow(['Name', 'Phone', 'Type', 'Purchases', 'Total Spent'])
            for c in customers:
                writer.writerow([c.name, c.phone, c.customer_type, c.purchase_count, c.amount_spent or 0])

        csv_content = output.getvalue()
        cache_key = f'csv_export:{business_id}:{report_type}'
        cache.set(cache_key, csv_content, timeout=3600)  # available for 1 hour

        logger.info(f"CSV export '{report_type}' ready for business {business_id}")
        return cache_key

    except Exception as exc:
        logger.error(f"CSV export failed for business {business_id}: {exc}")
        raise self.retry(exc=exc)


# ── Webhook delivery task ─────────────────────────────────────────────────────

@shared_task(bind=True, max_retries=3)
def deliver_webhook(self, webhook_id: int, event: str, data: dict):
    """
    Deliver a webhook payload to the subscriber URL.
    Retries up to 3 times with exponential backoff: 30s, 60s, 120s.
    """
    import json

    try:
        import requests
        from .models import Webhook, WebhookDelivery
        from .webhook_service import _build_payload, _sign

        hook = Webhook.objects.select_related('business').get(pk=webhook_id, is_active=True)
        payload = _build_payload(event, data, hook.business)
        payload_bytes = json.dumps(payload, default=str).encode()
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Event': event,
            'X-Webhook-ID': payload['id'],
        }
        if hook.secret:
            headers['X-Webhook-Signature'] = _sign(payload_bytes, hook.secret)

        resp = requests.post(hook.url, data=payload_bytes, headers=headers, timeout=10)
        WebhookDelivery.objects.create(
            webhook=hook, event=event, payload=payload,
            response_status=resp.status_code,
            response_body=resp.text[:2000],
            success=resp.status_code < 400,
            attempt=self.request.retries + 1,
        )
        if resp.status_code >= 400:
            raise Exception(f"HTTP {resp.status_code}")

    except Webhook.DoesNotExist:
        pass  # Webhook deleted — skip silently
    except Exception as exc:
        logger.warning(f"Webhook delivery failed (attempt {self.request.retries + 1}): {exc}")
        delay = 30 * (2 ** self.request.retries)  # 30s, 60s, 120s
        raise self.retry(exc=exc, countdown=delay)
