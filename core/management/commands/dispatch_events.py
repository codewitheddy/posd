"""
Management Command: dispatch_events
Dispatches pending transactional Outbox events to registered subscribers.
"""
import time
from django.core.management.base import BaseCommand
from core.events.bus import event_bus


class Command(BaseCommand):
    help = "Dispatches pending transactional Outbox events to subscribers."

    def add_arguments(self, parser):
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run event dispatcher continuously in a loop.',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=3,
            help='Polling interval in seconds when no pending events exist.',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Batch size per dispatch iteration.',
        )

    def handle(self, *args, **options):
        is_daemon = options['daemon']
        interval = options['interval']
        batch_size = options['batch_size']

        self.stdout.write(self.style.SUCCESS(f"Starting Outbox Event Dispatcher (Daemon: {is_daemon})..."))

        try:
            while True:
                stats = event_bus.dispatch_pending_events(batch_size=batch_size)
                total_processed = stats['dispatched'] + stats['failed'] + stats['dead_letter']

                if total_processed > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Dispatched: {stats['dispatched']}, Failed: {stats['failed']}, Dead Letter: {stats['dead_letter']}"
                        )
                    )
                else:
                    if not is_daemon:
                        self.stdout.write("No pending outbox events. Exiting.")
                        break
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nDispatcher stopped by user."))
