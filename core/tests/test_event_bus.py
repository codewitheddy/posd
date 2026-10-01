"""
Unit Tests for Event Bus & Outbox Pattern
"""
from django.test import TestCase
from core.models.events import OutboxEvent, EventDelivery
from core.models.organization import Company
from core.events.bus import (
    EventBus,
    publish,
    event_bus,
    EVENT_POS_SALE_COMPLETED,
    EVENT_HR_EMPLOYEE_HIRED,
)


class EventBusTests(TestCase):
    """Test suite for transactional outbox publishing and subscriber dispatch."""

    def setUp(self):
        self.company = Company.objects.create(name='Prime Enterprise', slug='prime-ent')
        self.bus = EventBus()

    def test_publish_creates_outbox_event(self):
        """Test publishing an event writes an OutboxEvent row."""
        event = publish(
            event_name=EVENT_POS_SALE_COMPLETED,
            payload={'sale_id': 1001, 'invoice': 'INV-001', 'total': '2500.00'},
            company=self.company,
            idempotency_key='sale_event_1001',
        )

        self.assertIsNotNone(event.pk)
        self.assertEqual(event.event_name, EVENT_POS_SALE_COMPLETED)
        self.assertEqual(event.status, OutboxEvent.STATUS_PENDING)
        self.assertEqual(event.payload['invoice'], 'INV-001')

    def test_subscriber_dispatch_success(self):
        """Test that dispatch_pending_events delivers payload to registered subscribers."""
        received_payloads = []

        def test_subscriber(payload):
            received_payloads.append(payload)

        self.bus.subscribe('test.notification.v1', test_subscriber)

        event = self.bus.publish(
            event_name='test.notification.v1',
            payload={'message': 'Hello Event Bus'},
            company=self.company,
        )

        stats = self.bus.dispatch_pending_events(batch_size=10)
        self.assertEqual(stats['dispatched'], 1)

        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.STATUS_DISPATCHED)
        self.assertIsNotNone(event.dispatched_at)
        self.assertEqual(len(received_payloads), 1)
        self.assertEqual(received_payloads[0]['message'], 'Hello Event Bus')

        # Check delivery record
        delivery = EventDelivery.objects.filter(event=event).first()
        self.assertIsNotNone(delivery)
        self.assertEqual(delivery.status, EventDelivery.STATUS_SUCCESS)

    def test_failing_subscriber_triggers_dead_letter_after_max_attempts(self):
        """Test that recurring subscriber errors move outbox event to dead letter."""
        def failing_subscriber(payload):
            raise ConnectionError("Subscriber downstream timeout")

        self.bus.subscribe('test.failing.v1', failing_subscriber)

        event = self.bus.publish(
            event_name='test.failing.v1',
            payload={'data': 123},
        )
        event.max_attempts = 2
        event.save()

        # First dispatch attempt -> failed
        self.bus.dispatch_pending_events(batch_size=10)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.STATUS_FAILED)
        self.assertEqual(event.attempts, 1)

        # Second dispatch attempt -> dead_letter
        self.bus.dispatch_pending_events(batch_size=10)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.STATUS_DEAD_LETTER)
        self.assertEqual(event.attempts, 2)
        self.assertIn("downstream timeout", event.last_error)
