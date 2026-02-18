"""
List dates with sales for a business
"""
from django.core.management.base import BaseCommand
from django.db.models import Count
from pos.models import Sale, Business


class Command(BaseCommand):
    help = 'List dates with sales'

    def add_arguments(self, parser):
        parser.add_argument('business_slug', type=str, help='Business slug')

    def handle(self, *args, **options):
        business_slug = options['business_slug']
        
        try:
            business = Business.objects.get(slug=business_slug)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business "{business_slug}" not found'))
            return
        
        sales_by_date = Sale.objects.filter(
            business=business
        ).values('date__date').annotate(
            count=Count('id')
        ).order_by('-date__date')[:10]
        
        self.stdout.write(f'\nRecent sales dates for {business.name}:\n')
        
        if not sales_by_date:
            self.stdout.write(self.style.WARNING('No sales found'))
            return
        
        for item in sales_by_date:
            self.stdout.write(f'  {item["date__date"]}: {item["count"]} sales')
        
        self.stdout.write('\nUse: python manage.py diagnose_z_report_cash <slug> --date YYYY-MM-DD\n')
