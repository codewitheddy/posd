"""
Management command to check supplier statement data
"""
from django.core.management.base import BaseCommand
from pos.models import Supplier, Purchase, SupplierPayment
from pos.services import SupplierStatementService
from decimal import Decimal


class Command(BaseCommand):
    help = 'Check supplier statement data for debugging'

    def add_arguments(self, parser):
        parser.add_argument('supplier_id', type=int, help='Supplier ID')
        parser.add_argument('--business', type=str, help='Business slug')

    def handle(self, *args, **options):
        supplier_id = options['supplier_id']
        business_slug = options.get('business')

        try:
            if business_slug:
                from pos.models import Business
                business = Business.objects.get(slug=business_slug)
                supplier = Supplier.objects.get(pk=supplier_id, business=business)
            else:
                supplier = Supplier.objects.get(pk=supplier_id)

            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Supplier Statement Check: {supplier.name}")
            self.stdout.write(f"{'='*60}\n")

            # Check purchases
            purchases = supplier.purchases.filter(status='received').order_by('-date')
            self.stdout.write(f"\n📦 PURCHASES (Received):")
            self.stdout.write(f"{'='*60}")
            total_purchases = Decimal('0.00')
            for purchase in purchases[:10]:  # Show last 10
                self.stdout.write(f"  {purchase.purchase_number}")
                self.stdout.write(f"    Date: {purchase.date}")
                self.stdout.write(f"    Amount: KES {purchase.total_amount}")
                self.stdout.write(f"    Status: {purchase.status}")
                total_purchases += purchase.total_amount
            
            if purchases.count() > 10:
                self.stdout.write(f"  ... and {purchases.count() - 10} more")
            
            self.stdout.write(f"\n  Total Purchases: KES {total_purchases}")

            # Check payments
            payments = supplier.payments.all().order_by('-payment_date')
            self.stdout.write(f"\n\n💰 PAYMENTS:")
            self.stdout.write(f"{'='*60}")
            total_payments = Decimal('0.00')
            for payment in payments[:10]:  # Show last 10
                self.stdout.write(f"  {payment.payment_number}")
                self.stdout.write(f"    Date: {payment.payment_date}")
                self.stdout.write(f"    Amount: KES {payment.amount}")
                self.stdout.write(f"    Method: {payment.payment_method.name}")
                total_payments += payment.amount
            
            if payments.count() > 10:
                self.stdout.write(f"  ... and {payments.count() - 10} more")
            
            self.stdout.write(f"\n  Total Payments: KES {total_payments}")

            # Check GRNs
            grns = supplier.goods_returned_notes.filter(status='credited').order_by('-credit_note_date')
            self.stdout.write(f"\n\n↩️  GOODS RETURNED (Credited):")
            self.stdout.write(f"{'='*60}")
            total_returns = Decimal('0.00')
            for grn in grns[:10]:
                credit_amount = grn.credit_note_amount or grn.total_value
                self.stdout.write(f"  {grn.grn_number}")
                self.stdout.write(f"    Date: {grn.credit_note_date}")
                self.stdout.write(f"    Amount: KES {credit_amount}")
                self.stdout.write(f"    Reason: {grn.get_return_reason_display()}")
                total_returns += credit_amount
            
            if grns.count() > 10:
                self.stdout.write(f"  ... and {grns.count() - 10} more")
            
            self.stdout.write(f"\n  Total Returns: KES {total_returns}")

            # Calculate balance
            self.stdout.write(f"\n\n📊 BALANCE CALCULATION:")
            self.stdout.write(f"{'='*60}")
            self.stdout.write(f"  Total Purchases:  KES {total_purchases}")
            self.stdout.write(f"  Total Payments:   KES {total_payments}")
            self.stdout.write(f"  Total Returns:    KES {total_returns}")
            self.stdout.write(f"  {'─'*58}")
            balance = total_purchases - total_payments - total_returns
            self.stdout.write(f"  Outstanding:      KES {balance}")

            # Generate statement using service
            self.stdout.write(f"\n\n📄 STATEMENT SERVICE OUTPUT:")
            self.stdout.write(f"{'='*60}")
            statement = SupplierStatementService.generate_statement(supplier)
            self.stdout.write(f"  Opening Balance:  KES {statement['opening_balance']}")
            self.stdout.write(f"  Total Purchases:  KES {statement['total_purchases']}")
            self.stdout.write(f"  Total Payments:   KES {statement['total_payments']}")
            self.stdout.write(f"  Total Returns:    KES {statement['total_returns']}")
            self.stdout.write(f"  Closing Balance:  KES {statement['closing_balance']}")
            self.stdout.write(f"  Transactions:     {len(statement['transactions'])}")

            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(self.style.SUCCESS('✓ Check complete'))

        except Supplier.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'✗ Supplier with ID {supplier_id} not found'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error: {str(e)}'))
            import traceback
            traceback.print_exc()
