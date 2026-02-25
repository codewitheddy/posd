from django.core.management.base import BaseCommand
from pos.models import DayClosureReport, Business
from datetime import datetime

class Command(BaseCommand):
    help = 'Check day closure reports in the database'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Day Closure Reports ==='))
        
        closures = DayClosureReport.objects.all().order_by('-closed_at')
        
        if not closures.exists():
            self.stdout.write(self.style.WARNING('No day closure reports found!'))
            return
        
        for closure in closures:
            self.stdout.write(f'\nID: {closure.id}')
            self.stdout.write(f'Business: {closure.business.name} (slug: {closure.business.slug})')
            self.stdout.write(f'Report Date: {closure.report_date}')
            self.stdout.write(f'Closed At: {closure.closed_at}')
            self.stdout.write(f'Closed By: {closure.closed_by.username}')
            self.stdout.write(f'Expected Cash: KES {closure.expected_cash}')
            self.stdout.write(f'Declared Cash: KES {closure.declared_cash}')
            self.stdout.write(f'Variance: KES {closure.variance}')
            self.stdout.write(f'Status: {closure.variance_status}')
            self.stdout.write('-' * 50)
        
        self.stdout.write(self.style.SUCCESS(f'\nTotal closures found: {closures.count()}'))
