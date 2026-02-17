"""
Management command to diagnose cash calculation issues
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Q
from pos.models import Business, SalePayment, CashFloat, Shift
from decimal import Decimal
from datetime import datetime


class Command(BaseCommand):
    help = 'Diagnose cash calculation issues for a specific date'

    def add_arguments(self, parser):
        parser.add_argument('business_id', type=int, help='Business ID')
        parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD), defaults to today')

    def handle(self, *args, **options):
        business_id = options['business_id']
        date_str = options.get('date')
        
        try:
            business = Business.objects.get(id=business_id)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business with ID {business_id} does not exist'))
            return
        
        # Parse date
        if date_str:
            report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            report_date = datetime.now().date()
        
        self.stdout.write(self.style.SUCCESS(f'\n=== CASH CALCULATION DIAGNOSIS ==='))
        self.stdout.write(f'Business: {business.name}')
        self.stdout.write(f'Date: {report_date}\n')
        
        # 1. Check all sales for the date
        from pos.models import Sale
        sales = Sale.objects.filter(
            business=business,
            date__date=report_date
        )
        total_sales = sales.count()
        self.stdout.write(f'📊 Total Sales: {total_sales}')
        
        # 2. Check all sale payments
        all_payments = SalePayment.objects.filter(
            sale__business=business,
            sale__date__date=report_date
        )
        total_payments_count = all_payments.count()
        total_payments_amount = all_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        self.stdout.write(f'💰 Total Payments: {total_payments_count} transactions, KES {total_payments_amount:,.2f}')
        
        # 3. Check payment methods
        self.stdout.write(f'\n📋 Payment Methods Breakdown:')
        payment_breakdown = all_payments.values(
            'payment_method__name',
            'payment_method__code'
        ).annotate(
            count=Sum('id'),
            total=Sum('amount')
        ).order_by('-total')
        
        for pm in payment_breakdown:
            self.stdout.write(
                f'  - {pm["payment_method__name"]} (code: "{pm["payment_method__code"]}"): '
                f'{pm["count"]} transactions, KES {pm["total"]:,.2f}'
            )
        
        # 4. Check CASH payments with different filters
        self.stdout.write(f'\n💵 CASH Payment Analysis:')
        
        # Filter 1: By code='CASH'
        cash_by_code = all_payments.filter(payment_method__code='CASH').aggregate(
            total=Sum('amount'))['total'] or Decimal('0.00')
        count_by_code = all_payments.filter(payment_method__code='CASH').count()
        self.stdout.write(f'  By code="CASH": {count_by_code} transactions, KES {cash_by_code:,.2f}')
        
        # Filter 2: By name (case-insensitive exact)
        cash_by_name = all_payments.filter(payment_method__name__iexact='CASH').aggregate(
            total=Sum('amount'))['total'] or Decimal('0.00')
        count_by_name = all_payments.filter(payment_method__name__iexact='CASH').count()
        self.stdout.write(f'  By name="CASH" (exact): {count_by_name} transactions, KES {cash_by_name:,.2f}')
        
        # Filter 3: Combined (what we use in code)
        cash_combined = all_payments.filter(
            Q(payment_method__code='CASH') | Q(payment_method__name__iexact='CASH')
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        count_combined = all_payments.filter(
            Q(payment_method__code='CASH') | Q(payment_method__name__iexact='CASH')
        ).count()
        self.stdout.write(f'  Combined filter: {count_combined} transactions, KES {cash_combined:,.2f}')
        
        # 5. Check cash floats
        self.stdout.write(f'\n🏦 Cash Floats:')
        cash_floats = CashFloat.objects.filter(
            business=business,
            given_at__date=report_date
        )
        
        if cash_floats.exists():
            for cf in cash_floats:
                self.stdout.write(
                    f'  - {cf.float_number}: {cf.cashier.username}, '
                    f'KES {cf.amount:,.2f}, Status: {cf.status}, Type: {cf.float_type}'
                )
            
            opening_floats = cash_floats.filter(float_type='opening').aggregate(
                total=Sum('amount'))['total'] or Decimal('0.00')
            additional_floats = cash_floats.filter(float_type='additional').aggregate(
                total=Sum('amount'))['total'] or Decimal('0.00')
            total_floats = opening_floats + additional_floats
            
            self.stdout.write(f'  Opening Floats: KES {opening_floats:,.2f}')
            self.stdout.write(f'  Additional Floats: KES {additional_floats:,.2f}')
            self.stdout.write(f'  Total Floats: KES {total_floats:,.2f}')
        else:
            self.stdout.write('  No cash floats found for this date')
        
        # 6. Check shifts
        self.stdout.write(f'\n⏰ Shifts:')
        from django.contrib.auth.models import User
        business_cashiers = User.objects.filter(business_memberships__business=business)
        shifts = Shift.objects.filter(
            cashier__in=business_cashiers,
            start_time__date=report_date
        )
        
        if shifts.exists():
            for shift in shifts:
                self.stdout.write(
                    f'  - {shift.shift_number}: {shift.cashier.username}, '
                    f'Opening: KES {shift.opening_cash:,.2f}, '
                    f'Status: {shift.status}'
                )
            
            opening_cash_shifts = shifts.aggregate(total=Sum('opening_cash'))['total'] or Decimal('0.00')
            self.stdout.write(f'  Total Opening Cash (from shifts): KES {opening_cash_shifts:,.2f}')
        else:
            self.stdout.write('  No shifts found for this date')
        
        # 7. Calculate expected cash
        self.stdout.write(f'\n🧮 Expected Cash Calculation:')
        
        # Determine opening cash
        opening_cash = Decimal('0.00')
        if cash_floats.exists():
            total_floats = cash_floats.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            opening_cash = total_floats
            self.stdout.write(f'  Opening Cash (from floats): KES {opening_cash:,.2f}')
        elif shifts.exists():
            opening_cash = shifts.aggregate(total=Sum('opening_cash'))['total'] or Decimal('0.00')
            self.stdout.write(f'  Opening Cash (from shifts): KES {opening_cash:,.2f}')
        else:
            self.stdout.write(f'  Opening Cash: KES 0.00 (no floats or shifts found)')
        
        self.stdout.write(f'  Cash Sales: KES {cash_combined:,.2f}')
        expected_cash = opening_cash + cash_combined
        self.stdout.write(self.style.SUCCESS(f'  EXPECTED CASH: KES {expected_cash:,.2f}'))
        
        # 8. Summary
        self.stdout.write(f'\n📝 SUMMARY:')
        self.stdout.write(f'  Opening Cash: KES {opening_cash:,.2f}')
        self.stdout.write(f'  + Cash Sales: KES {cash_combined:,.2f}')
        self.stdout.write(f'  = Expected Cash: KES {expected_cash:,.2f}')
        
        if expected_cash != (opening_cash + cash_combined):
            self.stdout.write(self.style.ERROR(f'\n⚠️  CALCULATION MISMATCH DETECTED!'))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Calculation is correct'))
        
        # 9. Check for issues
        self.stdout.write(f'\n🔍 POTENTIAL ISSUES:')
        issues_found = False
        
        if total_sales > 0 and total_payments_count == 0:
            self.stdout.write(self.style.ERROR('  ⚠️  Sales exist but no payments recorded!'))
            issues_found = True
        
        if cash_combined == 0 and total_payments_amount > 0:
            self.stdout.write(self.style.ERROR('  ⚠️  No CASH payments found, but other payments exist!'))
            self.stdout.write('     Check if payment method code/name is set correctly.')
            issues_found = True
        
        if not cash_floats.exists() and not shifts.exists():
            self.stdout.write(self.style.WARNING('  ⚠️  No cash floats or shifts found for this date.'))
            self.stdout.write('     Opening cash will be 0.')
            issues_found = True
        
        if not issues_found:
            self.stdout.write(self.style.SUCCESS('  ✓ No obvious issues detected'))
        
        self.stdout.write(f'\n')
