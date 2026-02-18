"""
Fix cash payment amounts that exceed sale totals
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Q
from pos.models import Sale, SalePayment, Business
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fix cash payment amounts that were recorded as cash tendered instead of sale amount'

    def add_arguments(self, parser):
        parser.add_argument(
            '--business',
            type=str,
            help='Business slug (optional, fixes all if not specified)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        business_slug = options.get('business')
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n=== DRY RUN MODE ===\n'))
        
        # Get businesses to process
        if business_slug:
            try:
                businesses = [Business.objects.get(slug=business_slug)]
            except Business.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Business "{business_slug}" not found'))
                return
        else:
            businesses = Business.objects.all()
        
        total_fixed = 0
        total_amount_corrected = Decimal('0.00')
        
        for business in businesses:
            self.stdout.write(f'\nProcessing: {business.name}')
            self.stdout.write('-' * 50)
            
            # Find sales where total payments exceed sale total
            sales = Sale.objects.filter(business=business).prefetch_related('payments')
            
            for sale in sales:
                sale_total = sale.total
                payments = sale.payments.all()
                
                if not payments.exists():
                    continue
                
                total_payments = payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
                
                # Check if overpaid
                if total_payments > sale_total:
                    overpayment = total_payments - sale_total
                    
                    # Check if there's a cash payment
                    cash_payments = payments.filter(
                        Q(payment_method__code='CASH') | Q(payment_method__name__iexact='CASH')
                    )
                    
                    if cash_payments.exists():
                        self.stdout.write(f'\n  Sale #{sale.invoice_number}')
                        self.stdout.write(f'    Sale Total: KES {sale_total}')
                        self.stdout.write(f'    Payments Total: KES {total_payments}')
                        self.stdout.write(f'    Overpayment: KES {overpayment}')
                        
                        # Show all payments
                        self.stdout.write('    Payments:')
                        for payment in payments:
                            is_cash = (payment.payment_method.code == 'CASH' or 
                                     payment.payment_method.name.upper() == 'CASH')
                            indicator = '💵' if is_cash else ''
                            self.stdout.write(
                                f'      {indicator} {payment.payment_method.name}: KES {payment.amount}'
                            )
                        
                        # Fix: Reduce cash payment by overpayment amount
                        cash_payment = cash_payments.first()
                        new_amount = cash_payment.amount - overpayment
                        
                        if new_amount >= 0:
                            self.stdout.write(f'    Fix: Reduce cash payment from KES {cash_payment.amount} to KES {new_amount}')
                            
                            if not dry_run:
                                cash_payment.amount = new_amount
                                cash_payment.save()
                                self.stdout.write(self.style.SUCCESS('      ✓ Fixed'))
                            else:
                                self.stdout.write(self.style.WARNING('      (Would fix in real run)'))
                            
                            total_fixed += 1
                            total_amount_corrected += overpayment
                        else:
                            self.stdout.write(self.style.ERROR(
                                f'    ⚠️  Cannot fix: New amount would be negative ({new_amount})'
                            ))
        
        self.stdout.write('\n' + '=' * 50)
        if total_fixed == 0:
            self.stdout.write(self.style.SUCCESS('\n✓ No issues found!'))
        else:
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f'\n{total_fixed} sale(s) would be fixed'
                ))
                self.stdout.write(self.style.WARNING(
                    f'Total amount to correct: KES {total_amount_corrected}'
                ))
                self.stdout.write(self.style.WARNING('\nRun without --dry-run to apply fixes'))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f'\n✓ Fixed {total_fixed} sale(s)'
                ))
                self.stdout.write(self.style.SUCCESS(
                    f'Total amount corrected: KES {total_amount_corrected}'
                ))
        
        self.stdout.write('')
