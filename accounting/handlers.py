"""
Accounting Domain Event Handlers
Idempotent subscriber functions reacting to system outbox events.
"""
import logging

logger = logging.getLogger(__name__)


def on_employee_hired(event_payload: dict) -> None:
    """Example handler for employee_hired event."""
    pass
