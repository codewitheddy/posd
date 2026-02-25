"""
Management command to clear old activity logs
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from pos.models import ActivityLog


class Command(BaseCommand):
    help = 'Clear activity logs older than specified days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Delete logs older than this many days (default: 90)'
        )
        parser.add_argument(
            '--business',
            type=str,
            help='Business slug to clear logs for (optional, clears all if not specified)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )

    def handle(self, *args, **options):
        days = options['days']
        business_slug = options.get('business')
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(f"Clearing logs older than {days} days (before {cutoff_date.date()})")
        
        # Build query
        query = ActivityLog.objects.filter(timestamp__lt=cutoff_date)
        
        if business_slug:
            from pos.models import Business
            try:
                business = Business.objects.get(slug=business_slug)
                query = query.filter(business=business)
                self.stdout.write(f"Filtering for business: {business.name}")
            except Business.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Business with slug '{business_slug}' not found"))
                return
        
        count = query.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No old logs to delete"))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f"DRY RUN: Would delete {count} log entries"))
            
            # Show breakdown by action type
            from django.db.models import Count
            breakdown = query.values('action_type').annotate(count=Count('id')).order_by('-count')
            self.stdout.write("\nBreakdown by action type:")
            for item in breakdown:
                self.stdout.write(f"  {item['action_type']}: {item['count']}")
        else:
            deleted_count, _ = query.delete()
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} log entries"))
