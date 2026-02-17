"""
Management command to check sales dates for a business
"""
from django.core.management.base import BaseCommand
from pos.models import Business, Sale, SalePayment
from django.db.models import Sum, Count


class Command(BaseCommand):
    help = 'Check sales dates for a business'

    def add_arguments(self, parser):
        parser.add_argument('business_id', type=int, help='Business ID')

    def handle(self, *args, **options):
        business_id = options['business_id']
        
        try:
            business = Business.objects.get(id=business_id)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business with ID {business_id} does not exist'))
            return
        
        self.stdout.write(f'\nBusiness: {business.name}\n')
        
        # Get all sales
        sales = Sale.objects.filter(business=business)
        total_sales = sales.count()
        
        self.stdout.write(f'Total Sales: {total_sales}\n')
        
        if total_sales == 0:
            self.stdout.write('No sales found for this business.')
            return
        
        # Group by date
        sales_by_date = sales.extra(
            select={'date_only': 'DATE(date)'}
        ).values('date_only').annotate(
            count=Count('id'),
            total=Sum('total')
        ).order_by('-date_only')
        
        self.stdout.write('Sales by Date:')
        for item in sales_by_date:
            self.stdout.write(f'  {item["date_only"]}: {item["count"]} sales, KES {item["total"]:,.2f}')
        
        # Check payments
        self.stdout.write(f'\nPayment Methods Used:')
        payments = SalePayment.objects.filter(sale__business=business)
        payment_methods = payments.values(
            'payment_method__name',
            'payment_method__code'
        ).annotate(
            count=Count('id'),
            total=Sum('amount')
        ).order_by('-total')
        
        for pm in payment_methods:
            self.stdout.write(
                f'  {pm["payment_method__name"]} (code: "{pm["payment_method__code"]}"): '
                f'{pm["count"]} transactions, KES {pm["total"]:,.2f}'
            )
