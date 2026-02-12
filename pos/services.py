"""
Service layer for business logic
"""
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, Q
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.utils import timezone
from .models import (
    SupplierPayment, PaymentAllocation, Purchase, Supplier, 
    PaymentMethod, ActivityLog
)


class SupplierPaymentService:
    """Business logic for supplier payments"""
    
    @staticmethod
    @transaction.atomic
    def create_payment(supplier, amount, payment_date, payment_method, 
                      reference_number, notes, created_by, allocations=None):
        """
        Create a supplier payment with optional allocations
        
        Args:
            supplier: Supplier instance
            amount: Decimal payment amount
            payment_date: Date of payment
            payment_method: PaymentMethod instance
            reference_number: Optional reference string
            notes: Optional notes string
            created_by: User instance
            allocations: Optional list of dicts [{'purchase': Purchase, 'amount': Decimal}]
        
        Returns:
            SupplierPayment instance
        
        Raises:
            ValidationError: If validation fails
        """
        # Validate supplier is active
        if not supplier.is_active:
            raise ValidationError("Cannot create payment for inactive supplier")
        
        # Validate payment method is active
        if not payment_method.is_active:
            raise ValidationError("Cannot use inactive payment method")
        
        # Validate amount
        if amount <= Decimal('0.00'):
            raise ValidationError("Payment amount must be greater than zero")
        
        # Create payment
        payment = SupplierPayment.objects.create(
            supplier=supplier,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            created_by=created_by
        )
        
        # Create allocations if provided
        if allocations:
            total_allocated = Decimal('0.00')
            for alloc in allocations:
                purchase = alloc['purchase']
                alloc_amount = alloc['amount']
                
                # Validate purchase belongs to supplier
                if purchase.supplier != supplier:
                    raise ValidationError(f"Purchase {purchase.purchase_number} does not belong to this supplier")
                
                # Validate purchase is received
                if purchase.status != 'received':
                    raise ValidationError(f"Purchase {purchase.purchase_number} is not received")
                
                # Validate allocation doesn't exceed remaining balance
                remaining = purchase.remaining_balance()
                if alloc_amount > remaining:
                    raise ValidationError(
                        f"Allocation amount {alloc_amount} exceeds remaining balance {remaining} "
                        f"for purchase {purchase.purchase_number}"
                    )
                
                PaymentAllocation.objects.create(
                    payment=payment,
                    purchase=purchase,
                    amount=alloc_amount
                )
                total_allocated += alloc_amount
            
            # Validate total allocations don't exceed payment amount
            if total_allocated > amount:
                raise ValidationError("Total allocations exceed payment amount")
        else:
            # Auto-allocate using FIFO if no allocations specified
            SupplierPaymentService._auto_allocate_payment(payment)
        
        # Log activity
        ActivityLog.log_activity(
            user=created_by,
            action_type='create',
            description=f'Created supplier payment {payment.payment_number} for {supplier.name}',
            model_name='SupplierPayment',
            object_id=payment.id
        )
        
        return payment
    
    @staticmethod
    def _auto_allocate_payment(payment):
        """Automatically allocate payment to oldest unpaid purchases using FIFO"""
        remaining_amount = payment.amount
        
        # Get unpaid purchases ordered by date (oldest first)
        unpaid_purchases = Purchase.objects.filter(
            supplier=payment.supplier,
            status='received'
        ).annotate(
            allocated=Coalesce(Sum('payment_allocations__amount'), Decimal('0.00'))
        ).filter(
            allocated__lt=F('total_amount')
        ).order_by('date')
        
        for purchase in unpaid_purchases:
            if remaining_amount <= Decimal('0.00'):
                break
            
            purchase_remaining = purchase.remaining_balance()
            allocation_amount = min(remaining_amount, purchase_remaining)
            
            PaymentAllocation.objects.create(
                payment=payment,
                purchase=purchase,
                amount=allocation_amount
            )
            
            remaining_amount -= allocation_amount


class SupplierStatementService:
    """Business logic for generating supplier statements"""
    
    @staticmethod
    def generate_statement(supplier, start_date=None, end_date=None):
        """
        Generate statement data for a supplier
        
        Args:
            supplier: Supplier instance
            start_date: Optional start date (defaults to earliest transaction)
            end_date: Optional end date (defaults to today)
        
        Returns:
            dict with statement data
        """
        if end_date is None:
            end_date = timezone.now().date()
        
        # Calculate opening balance (transactions before start_date)
        opening_balance = Decimal('0.00')
        if start_date:
            opening_purchases = supplier.purchases.filter(
                status='received',
                date__lt=start_date
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            
            opening_payments = supplier.payments.filter(
                payment_date__lt=start_date
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            opening_balance = opening_purchases - opening_payments
        
        # Get transactions in period
        if start_date:
            purchases = supplier.purchases.filter(
                status='received',
                date__gte=start_date,
                date__lte=timezone.datetime.combine(end_date, timezone.datetime.max.time())
            ).order_by('date')
            
            payments = supplier.payments.filter(
                payment_date__gte=start_date,
                payment_date__lte=end_date
            ).order_by('payment_date')
        else:
            # No start date - get all transactions up to end_date
            purchases = supplier.purchases.filter(
                status='received',
                date__lte=timezone.datetime.combine(end_date, timezone.datetime.max.time())
            ).order_by('date')
            
            payments = supplier.payments.filter(
                payment_date__lte=end_date
            ).order_by('payment_date')
        
        # Combine and sort transactions
        transactions = []
        
        for purchase in purchases:
            transactions.append({
                'date': purchase.date.date(),
                'type': 'purchase',
                'reference': purchase.purchase_number,
                'description': f'Purchase: {purchase.purchase_number}',
                'debit': purchase.total_amount,
                'credit': Decimal('0.00'),
                'object': purchase
            })
        
        for payment in payments:
            transactions.append({
                'date': payment.payment_date,
                'type': 'payment',
                'reference': payment.payment_number,
                'description': f'Payment: {payment.payment_method.name}',
                'debit': Decimal('0.00'),
                'credit': payment.amount,
                'object': payment
            })
        
        # Sort by date
        transactions.sort(key=lambda x: x['date'])
        
        # Calculate running balance
        running_balance = opening_balance
        for trans in transactions:
            running_balance += trans['debit'] - trans['credit']
            trans['balance'] = running_balance
        
        closing_balance = running_balance
        
        return {
            'supplier': supplier,
            'start_date': start_date,
            'end_date': end_date,
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'transactions': transactions,
            'total_purchases': sum(t['debit'] for t in transactions),
            'total_payments': sum(t['credit'] for t in transactions),
        }
    
    @staticmethod
    def generate_aging_analysis(as_of_date=None):
        """
        Generate aging analysis for all suppliers
        
        Args:
            as_of_date: Optional date for aging calculation (defaults to today)
        
        Returns:
            list of dicts with aging data per supplier
        """
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        suppliers_with_balance = Supplier.objects.filter(
            purchases__status='received'
        ).distinct()
        
        aging_data = []
        
        for supplier in suppliers_with_balance:
            # Get unpaid or partially paid purchases
            purchases = Purchase.objects.filter(
                supplier=supplier,
                status='received'
            ).annotate(
                allocated=Coalesce(Sum('payment_allocations__amount'), Decimal('0.00'))
            ).filter(
                allocated__lt=F('total_amount')
            )
            
            current = Decimal('0.00')
            days_30 = Decimal('0.00')
            days_60 = Decimal('0.00')
            days_90_plus = Decimal('0.00')
            
            for purchase in purchases:
                remaining = purchase.remaining_balance()
                days_old = (as_of_date - purchase.date.date()).days
                
                if days_old <= 30:
                    current += remaining
                elif days_old <= 60:
                    days_30 += remaining
                elif days_old <= 90:
                    days_60 += remaining
                else:
                    days_90_plus += remaining
            
            total_outstanding = current + days_30 + days_60 + days_90_plus
            
            if total_outstanding > Decimal('0.00'):
                aging_data.append({
                    'supplier': supplier,
                    'current': current,
                    '30_days': days_30,
                    '60_days': days_60,
                    '90_plus': days_90_plus,
                    'total': total_outstanding
                })
        
        return aging_data
