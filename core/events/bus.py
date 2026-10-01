"""
Event Bus & Transactional Outbox Engine
Decoupled asynchronous domain event publishing and subscriber dispatch.
"""
import logging
import traceback
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional
from django.db import connection, transaction
from django.utils import timezone
from core.models.events import OutboxEvent, EventDelivery

logger = logging.getLogger(__name__)


# ── Canonical Event Catalog ──────────────────────────────────────────────────
EVENT_HR_EMPLOYEE_HIRED = 'hr.employee_hired.v1'
EVENT_HR_EMPLOYEE_EXITED = 'hr.employee_exited.v1'
EVENT_HR_EMPLOYEE_TRANSFERRED = 'hr.employee_transferred.v1'
EVENT_HR_PAYROLL_LOCKED = 'hr.payroll_run_locked.v1'

EVENT_POS_SALE_COMPLETED = 'pos.sale_completed.v1'
EVENT_POS_SALE_REFUNDED = 'pos.sale_refunded.v1'
EVENT_POS_SHIFT_CLOSED = 'pos.shift_closed.v1'
EVENT_POS_SALES_DAY_CLOSED = 'pos.sales_day_closed.v1'

EVENT_INVENTORY_STOCK_ADJUSTED = 'inventory.stock_adjusted.v1'
EVENT_WORKFLOW_COMPLETED = 'core.workflow_completed.v1'
EVENT_WORKFLOW_REJECTED = 'core.workflow_rejected.v1'


class EventBus:
    """
    In-memory registry of event subscribers with transactional outbox persistence.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable) -> None:
        """Register a handler function for an event."""
        if handler not in self._subscribers[event_name]:
            self._subscribers[event_name].append(handler)
            logger.debug("Registered subscriber %s for event '%s'", handler.__name__, event_name)

    def get_subscribers(self, event_name: str) -> List[Callable]:
        """Return all subscribers registered for an event name."""
        return self._subscribers.get(event_name, [])

    def publish(
        self,
        event_name: str,
        payload: Dict[str, Any],
        company=None,
        idempotency_key: str = '',
    ) -> OutboxEvent:
        """
        Publish a domain event to the outbox table inside the current transaction.
        """
        # Idempotency check
        if idempotency_key:
            existing = OutboxEvent.objects.filter(
                idempotency_key=idempotency_key,
                status__in=[OutboxEvent.STATUS_PENDING, OutboxEvent.STATUS_DISPATCHED],
            ).first()
            if existing:
                return existing

        event = OutboxEvent.objects.create(
            company=company,
            event_name=event_name,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        logger.info("Published outbox event: '%s' (#%s)", event_name, event.id)
        return event

    def dispatch_pending_events(self, batch_size: int = 50) -> Dict[str, int]:
        """
        Fetch and dispatch pending outbox events to registered subscribers.
        Uses database row locking to prevent duplicate processing by concurrent dispatchers.
        """
        stats = {'dispatched': 0, 'failed': 0, 'dead_letter': 0}

        # Select candidate pending/failed events
        with transaction.atomic():
            qs = OutboxEvent.objects.filter(
                status__in=[OutboxEvent.STATUS_PENDING, OutboxEvent.STATUS_FAILED]
            ).order_by('created_at')

            backend = connection.vendor
            if backend in ('postgresql', 'mysql'):
                try:
                    qs = qs.select_for_update(skip_locked=True)
                except Exception:
                    qs = qs.select_for_update()

            events_to_process = list(qs[:batch_size])

            for event in events_to_process:
                event.status = OutboxEvent.STATUS_PROCESSING
                event.attempts += 1
                event.save(update_fields=['status', 'attempts', 'updated_at'])

        # Process subscribers outside main lock transaction to prevent holding table locks
        for event in events_to_process:
            subscribers = self.get_subscribers(event.event_name)
            all_succeeded = True
            last_err = ''
            tb_str = ''

            if not subscribers:
                # No subscribers registered yet: mark dispatched
                event.status = OutboxEvent.STATUS_DISPATCHED
                event.dispatched_at = timezone.now()
                event.save(update_fields=['status', 'dispatched_at', 'updated_at'])
                stats['dispatched'] += 1
                continue

            for handler in subscribers:
                subscriber_name = f"{handler.__module__}.{handler.__qualname__}"
                try:
                    # Execute idempotent subscriber
                    handler(event.payload)

                    EventDelivery.objects.create(
                        event=event,
                        subscriber_name=subscriber_name,
                        status=EventDelivery.STATUS_SUCCESS,
                        attempt_number=event.attempts,
                    )
                except Exception as exc:
                    all_succeeded = False
                    last_err = str(exc)
                    tb_str = traceback.format_exc()
                    logger.error("Subscriber %s failed on event #%s: %s", subscriber_name, event.id, exc)

                    EventDelivery.objects.create(
                        event=event,
                        subscriber_name=subscriber_name,
                        status=EventDelivery.STATUS_FAILED,
                        error_message=last_err,
                        traceback=tb_str,
                        attempt_number=event.attempts,
                    )

            if all_succeeded:
                event.status = OutboxEvent.STATUS_DISPATCHED
                event.dispatched_at = timezone.now()
                event.last_error = ''
                event.traceback = ''
                event.save(update_fields=['status', 'dispatched_at', 'last_error', 'traceback', 'updated_at'])
                stats['dispatched'] += 1
            else:
                if event.attempts >= event.max_attempts:
                    event.status = OutboxEvent.STATUS_DEAD_LETTER
                    stats['dead_letter'] += 1
                else:
                    event.status = OutboxEvent.STATUS_FAILED
                    stats['failed'] += 1

                event.last_error = last_err
                event.traceback = tb_str
                event.save(update_fields=['status', 'last_error', 'traceback', 'updated_at'])

        return stats


# Global Event Bus Singleton
event_bus = EventBus()


def subscribe(event_name: str):
    """Decorator to register a function as an event subscriber."""
    def decorator(func: Callable):
        event_bus.subscribe(event_name, func)
        return func
    return decorator


def publish(event_name: str, payload: Dict[str, Any], company=None, idempotency_key: str = '') -> OutboxEvent:
    """Convenience helper to publish events to the outbox."""
    return event_bus.publish(event_name, payload, company=company, idempotency_key=idempotency_key)
