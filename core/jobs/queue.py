"""
DB-Backed Job Queue Engine
Pure Django asynchronous and batch job execution engine with locking and retries.
"""
import importlib
import logging
import traceback
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional, Union

from django.db import connection, transaction
from django.utils import timezone
from core.models.jobs import Job

logger = logging.getLogger(__name__)


def resolve_task_callable(task_path: str) -> Callable:
    """Resolve dotted python path to callable function."""
    if '.' not in task_path:
        raise ValueError(f"Invalid task path: {task_path}. Must be dotted path.")
    module_path, func_name = task_path.rsplit('.', 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


class JobQueue:
    """
    Central Job Queue Service.
    """

    @classmethod
    def enqueue(
        cls,
        task: Union[Callable, str],
        name: str = '',
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        company=None,
        priority: int = 100,
        max_attempts: int = 3,
        scheduled_at: Optional[Any] = None,
        idempotency_key: str = '',
        user=None,
    ) -> Job:
        """
        Enqueue a new job for background execution.
        """
        if callable(task):
            task_path = f"{task.__module__}.{task.__qualname__}"
            if not name:
                name = task.__name__.replace('_', ' ').title()
        else:
            task_path = str(task)
            if not name:
                name = task_path.split('.')[-1].replace('_', ' ').title()

        args = args or []
        kwargs = kwargs or {}

        # Check idempotency
        if idempotency_key:
            existing = Job.objects.filter(
                idempotency_key=idempotency_key,
                status__in=[Job.STATUS_PENDING, Job.STATUS_RUNNING, Job.STATUS_COMPLETED],
            ).first()
            if existing:
                return existing

        job = Job.objects.create(
            company=company,
            name=name,
            task_path=task_path,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_attempts=max_attempts,
            scheduled_at=scheduled_at or timezone.now(),
            idempotency_key=idempotency_key,
            created_by=user,
        )
        logger.info("Enqueued background job: %s (#%s)", job.name, job.id)
        return job

    @classmethod
    def claim_next_job(cls, worker_id: str = 'worker_default') -> Optional[Job]:
        """
        Atomically claim the next pending job ready for execution using row locks.
        """
        now = timezone.now()
        with transaction.atomic():
            # Query candidate jobs
            qs = Job.objects.filter(
                status=Job.STATUS_PENDING,
                scheduled_at__lte=now,
            ).order_by('priority', 'scheduled_at')

            # Use select_for_update with skip_locked where supported
            backend_name = connection.vendor
            if backend_name in ('postgresql', 'mysql', 'oracle'):
                try:
                    qs = qs.select_for_update(skip_locked=True)
                except Exception:
                    qs = qs.select_for_update()
            elif backend_name == 'sqlite':
                # SQLite handles table locking automatically in transaction
                pass

            job = qs.first()
            if not job:
                return None

            job.status = Job.STATUS_RUNNING
            job.locked_by = worker_id
            job.locked_at = now
            job.started_at = now
            job.attempts += 1
            job.save(update_fields=['status', 'locked_by', 'locked_at', 'started_at', 'attempts', 'updated_at'])
            return job

    @classmethod
    def execute_job(cls, job: Job) -> bool:
        """
        Execute a single claimed job, capture results or handle retries with backoff.
        """
        logger.info("Executing job: %s (#%s) Attempt %d/%d", job.name, job.id, job.attempts, job.max_attempts)
        try:
            func = resolve_task_callable(job.task_path)
            
            # Pass job instance if the task accepts job keyword arg
            kwargs = dict(job.kwargs)
            
            result = func(*job.args, **kwargs)
            
            job.status = Job.STATUS_COMPLETED
            job.result = result if isinstance(result, (dict, list, str, int, float, bool)) else str(result)
            job.progress = 100
            job.progress_message = "Completed successfully."
            job.completed_at = timezone.now()
            job.error_message = ''
            job.traceback = ''
            job.save()
            logger.info("Job completed successfully: %s (#%s)", job.name, job.id)
            return True

        except Exception as exc:
            tb = traceback.format_exc()
            logger.error("Job execution failed: %s (#%s): %s", job.name, job.id, exc)
            
            if job.attempts < job.max_attempts:
                # Exponential backoff retry: 2^attempts * 10 seconds
                backoff_seconds = (2 ** job.attempts) * 10
                job.status = Job.STATUS_PENDING
                job.scheduled_at = timezone.now() + timedelta(seconds=backoff_seconds)
                job.error_message = f"Attempt {job.attempts} failed: {str(exc)}"
                job.traceback = tb
                job.save()
                logger.warning("Job #%s scheduled for retry in %ds", job.id, backoff_seconds)
            else:
                job.status = Job.STATUS_FAILED
                job.error_message = str(exc)
                job.traceback = tb
                job.completed_at = timezone.now()
                job.save()
                logger.error("Job #%s permanently failed after %d attempts", job.id, job.attempts)

            return False
