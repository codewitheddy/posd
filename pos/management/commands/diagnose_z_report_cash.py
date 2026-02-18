"""
Management command to diagnose Z-report cash calculation
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Q
from pos.models import Sale, SalePayment, Business
from datetime import datetime, date
from decimal import Decimal


class Command(BaseCommand):
    help = 'Diagnose Z-report cash calculation'

    def add_arguments(self, parser):
        parser.add_argument('business_slug', type=str, help='Business slug')
        parser.add_argument(
            '--date',
            type=str,
            help='Date to check (YYYY-MM-DD), defaults to today',
        )

    def handle(self, *args, **options):
        business_slug = options['business_slug']
        report_date_str = options.get('date')
        
        if report_date_str:
            report_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        else:
            report_date = date.today()
        
        try:
            business = Business.objects.get(slug=business_slug)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business "{business_slug}" not found'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\n=== Z-Report Cash Diagnosis ==='))
        self.stdout.write(f'Business: {business.name}')
        self.stdout.write(f'Date: {report_date}\n')
        
        # Get all sales for the date
        sales = Sale.objects.filter(
            business=business,
            date__date=report_date
        )
        
        self.stdout.write(f'Total Sales: {sales.count()}')
        
        if not sales.exists():
            self.stdout.write(self.style.WARNING('No sales found for this date'))
            return
        
        # Show each sale with its payments
        self.stdout.write(self.style.SUCCESS('\n=== Sales Breakdown ===\n'))
        
        total_sale_amounts = Decimal('0.00')
        total_cash_from_payments = Decimal('0.00')
        
        for sale in sales:
            self.stdout.write(f'\nSale #{sale.invoice_number}')
            self.stdout.write(f'  Total: KES {sale.total}')
            
            total_sale_amounts += sale.total
            
            # Get payments for this sale
            payments = SalePayment.objects.filter(sale=sale)
            
            if not payments.exists():
                self.stdout.write(self.style.WARNING('  ⚠️  No payments recorded!'))
                continue
            
            self.stdout.write('  Payments:')
            sale_cash_total = Decimal('0.00')
            
            for payment in payments:
                is_cash = (payment.payment_method.code == 'CASH' or 
                          payment.payment_method.name.upper() == 'CASH')
                
                cash_indicator = '💵 CASH' if is_cash else ''
                
                self.stdout.write(
                    f'    • {payment.payment_method.name:15} '
                    f'KES {payment.amount:>10.2f} {cash_indicator}'
                )
                
                if is_cash:
                    sale_cash_total += payment.amount
                    total_cash_from_payments += payment.amount
            
            if sale_cash_total > 0:
                self.stdout.write(f'  Cash from this sale: KES {sale_cash_total}')
        
        # Calculate using the same logic as Z-report
        self.stdout.write(self.style.SUCCESS('\n=== Z-Report Calculation ===\n'))
        
        cash_payments_query = SalePayment.objects.filter(
            sale__business=business,
            sale__date__date=report_date
        ).filter(
            Q(payment_method__code='CASH') | Q(payment_method__name__iexact='CASH')
        )
        
        self.stdout.write(f'Cash payments found: {cash_payments_query.count()}')
        
        cash_payments_total = cash_payments_query.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        self.stdout.write(f'\nTotal Sale Amounts: KES {total_sale_amounts}')
        self.stdout.write(f'Total Cash Payments: KES {cash_payments_total}')
        self.stdout.write(f'Manual Count: KES {total_cash_from_payments}')
        
        if cash_payments_total != total_cash_from_payments:
            self.stdout.write(self.style.ERROR('\n⚠️  MISMATCH DETECTED!'))
            self.stdout.write(f'Difference: KES {abs(cash_payments_total - total_cash_from_payments)}')
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ Calculations match!'))
        
        # Check for potential issues
        self.stdout.write(self.style.WARNING('\n=== Potential Issues ===\n'))
        
        # Check for sales without payments
        sales_without_payments = sales.filter(payments__isnull=True)
        if sales_without_payments.exists():
            self.stdout.write(self.style.ERROR(
                f'⚠️  {sales_without_payments.count()} sale(s) have NO payments recorded!'
            ))
            for sale in sales_without_payments:
                self.stdout.write(f'  • Sale #{sale.invoice_number} - KES {sale.total}')
        
        # Check for payment method issues
        cash_methods = SalePayment.objects.filter(
            sale__business=business,
            sale__date__date=report_date
        ).values('payment_method__name', 'payment_method__code').distinct()
        
        self.stdout.write('\nPayment methods used today:')
        for method in cash_methods:
            is_cash = (method['payment_method__code'] == 'CASH' or 
                      method['payment_method__name'].upper() == 'CASH')
            indicator = '💵 (counted as cash)' if is_cash else ''
            self.stdout.write(
                f'  • {method["payment_method__name"]} '
                f'(code: {method["payment_method__code"]}) {indicator}'
            )
        
        self.stdout.write('')
