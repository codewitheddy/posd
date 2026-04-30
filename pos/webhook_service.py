"""
Webhook dispatch service.
Signs payloads with HMAC-SHA256 and delivers them via Celery (or inline fallback).
"""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
import requests

try:
    from .models import WebhookDelivery
except Exception:  # pragma: no cover - safe fallback for import-time edge cases
    WebhookDelivery = None

logger = logging.getLogger(__name__)


def _build_payload(event: str, data: dict, business) -> dict:
    return {
        'id': str(uuid.uuid4()),
        'event': event,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'business': {'id': business.id, 'name': business.name, 'slug': business.slug},
        'data': data,
    }


def _sign(payload_bytes: bytes, secret: str) -> str:
    return 'sha256=' + hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()


def dispatch_event(event: str, data: dict, business):
    """
    Find all active webhooks for this business subscribed to `event`
    and enqueue delivery tasks.
    """
    from .models import Webhook
    hooks = Webhook.objects.filter(business=business, is_active=True)
    for hook in hooks:
        if hook.subscribes_to(event):
            try:
                from .tasks import deliver_webhook
                deliver_webhook.delay(hook.id, event, data)
            except Exception:
                # Celery not available — deliver inline (best-effort)
                _deliver_inline(hook, event, data)


def _deliver_inline(hook, event: str, data: dict):
    """Synchronous fallback delivery (no Celery)."""
    global WebhookDelivery
    if WebhookDelivery is None:
        from .models import WebhookDelivery as WebhookDeliveryModel
        WebhookDelivery = WebhookDeliveryModel

    payload = _build_payload(event, data, hook.business)
    payload_bytes = json.dumps(payload, default=str).encode()
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Event': event,
        'X-Webhook-ID': payload['id'],
    }
    if hook.secret:
        headers['X-Webhook-Signature'] = _sign(payload_bytes, hook.secret)

    try:
        resp = requests.post(hook.url, data=payload_bytes, headers=headers, timeout=10)
        WebhookDelivery.objects.create(
            webhook=hook, event=event, payload=payload,
            response_status=resp.status_code,
            response_body=resp.text[:2000],
            success=resp.status_code < 400,
        )
    except Exception as exc:
        WebhookDelivery.objects.create(
            webhook=hook, event=event, payload=payload,
            response_body=str(exc)[:2000],
            success=False,
        )
