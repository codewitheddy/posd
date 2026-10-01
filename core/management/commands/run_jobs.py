"""
Management Command: run_jobs
Worker daemon that polls, locks, and executes background jobs from the DB-backed Job table.
"""
import time
import socket
import os
from django.core.management.base import BaseCommand
from core.jobs.queue import JobQueue


class Command(BaseCommand):
    help = "Runs background jobs from the database queue."

    def add_arguments(self, parser):
        parser.add_argument(
            '--daemon',
            action='store_true',
            help='Run worker continuously in a loop.',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=3,
            help='Sleep interval in seconds when no jobs are pending.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Max number of jobs to execute before stopping (0 = unlimited).',
        )
        parser.add_argument(
            '--worker-id',
            type=str,
            default='',
            help='Custom worker identifier string.',
        )

    def handle(self, *args, **options):
        is_daemon = options['daemon']
        interval = options['interval']
        limit = options['limit']
        worker_id = options['worker_id'] or f"{socket.gethostname()}-{os.getpid()}"

        self.stdout.write(self.style.SUCCESS(f"Starting Job Worker [{worker_id}] (Daemon: {is_daemon})..."))
        jobs_processed = 0

        try:
            while True:
                job = JobQueue.claim_next_job(worker_id=worker_id)
                if job:
                    self.stdout.write(f"Claimed job: {job.name} (#{job.id})")
                    success = JobQueue.execute_job(job)
                    jobs_processed += 1
                    if success:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Finished job: {job.name}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"  ✗ Failed job: {job.name} (Status: {job.status})"))

                    if limit > 0 and jobs_processed >= limit:
                        self.stdout.write(f"Reached limit of {limit} jobs. Exiting.")
                        break
                else:
                    if not is_daemon:
                        self.stdout.write("No pending jobs found. Exiting.")
                        break
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nWorker stopped by user."))
