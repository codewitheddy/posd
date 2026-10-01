"""
Unit Tests for DB-Backed Job Queue
"""
from django.contrib.auth.models import User
from django.test import TestCase
from core.models.jobs import Job
from core.models.organization import Company
from core.jobs.queue import JobQueue


def sample_successful_task(x: int, y: int) -> int:
    """Sample task for testing."""
    return x + y


def sample_failing_task():
    """Sample task that raises an error."""
    raise RuntimeError("Intentional task failure for test")


class JobQueueTests(TestCase):
    """Test suite for Job Queue operations, locking, execution, and retries."""

    def setUp(self):
        self.company = Company.objects.create(name='Test Corp', slug='test-corp')
        self.user = User.objects.create_user(username='jobadmin', email='job@example.com')

    def test_enqueue_and_claim_job(self):
        """Test enqueueing a job and atomically claiming it."""
        job = JobQueue.enqueue(
            task=sample_successful_task,
            name='Add Numbers',
            args=[10, 25],
            company=self.company,
            priority=50,
            user=self.user,
        )

        self.assertIsNotNone(job)
        self.assertEqual(job.status, Job.STATUS_PENDING)
        self.assertEqual(job.name, 'Add Numbers')

        # Claim job
        claimed = JobQueue.claim_next_job(worker_id='test_worker_1')
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, job.id)
        self.assertEqual(claimed.status, Job.STATUS_RUNNING)
        self.assertEqual(claimed.locked_by, 'test_worker_1')
        self.assertEqual(claimed.attempts, 1)

    def test_execute_successful_job(self):
        """Test full execution lifecycle of a successful job."""
        job = JobQueue.enqueue(
            task=sample_successful_task,
            args=[15, 35],
            company=self.company,
        )
        claimed = JobQueue.claim_next_job(worker_id='w1')
        success = JobQueue.execute_job(claimed)

        self.assertTrue(success)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_COMPLETED)
        self.assertEqual(job.result, 50)
        self.assertEqual(job.progress, 100)

    def test_execute_failing_job_with_retry(self):
        """Test that failing jobs are scheduled for retry with exponential backoff."""
        job = JobQueue.enqueue(
            task=sample_failing_task,
            max_attempts=3,
        )
        claimed = JobQueue.claim_next_job(worker_id='w1')
        success = JobQueue.execute_job(claimed)

        self.assertFalse(success)
        job.refresh_from_db()
        self.assertEqual(job.status, Job.STATUS_PENDING)  # Re-queued for retry
        self.assertEqual(job.attempts, 1)
        self.assertIn("Intentional task failure", job.error_message)

    def test_idempotent_enqueueing(self):
        """Test that duplicate idempotency_key does not create duplicate pending jobs."""
        job1 = JobQueue.enqueue(
            task=sample_successful_task,
            args=[1, 2],
            idempotency_key='unique_key_123',
        )
        job2 = JobQueue.enqueue(
            task=sample_successful_task,
            args=[1, 2],
            idempotency_key='unique_key_123',
        )

        self.assertEqual(job1.id, job2.id)
        self.assertEqual(Job.objects.filter(idempotency_key='unique_key_123').count(), 1)
