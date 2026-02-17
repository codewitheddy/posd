"""
Cash Float Management Views
Handles opening floats and additional cash given to cashiers
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta

from .models import CashFloat, Sale, User
from .decorators import business_required


@business_required
def cash_float_list(request, slug=None):
    """List all cash floats"""
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    cashier_filter = request.GET.get('cashier', 'all')
    date_filter = request.GET.get('date', 'today')
    
    # Base query
    floats = CashFloat.objects.filter(business=request.business).select_related('cashier', 'given_by')
    
    # Apply filters
    if status_filter != 'all':
        floats = floats.filter(status=status_filter)
    
    if cashier_filter != 'all':
        floats = floats.filter(cashier_id=cashier_filter)
    
    # Date filter
    today = timezone.now().date()
    if date_filter == 'today':
        floats = floats.filter(given_at__date=today)
    elif date_filter == 'week':
        week_ago = today - timedelta(days=7)
        floats = floats.filter(given_at__date__gte=week_ago)
    elif date_filter == 'month':
        month_ago = today - timedelta(days=30)
        floats = floats.filter(given_at__date__gte=month_ago)
    
    # Get cashiers for filter dropdown
    cashiers = User.objects.filter(
        business_memberships__business=request.business
    ).distinct()
    
    # Calculate totals
    total_active = floats.filter(status='active').aggregate(Sum('amount'))['amount__sum'] or 0
    total_returned = floats.filter(status='returned').aggregate(Sum('returned_amount'))['returned_amount__sum'] or 0
    
    context = {
        'floats': floats,
        'cashiers': cashiers,
        'status_filter': status_filter,
        'cashier_filter': cashier_filter,
        'date_filter': date_filter,
        'total_active': total_active,
        'total_returned': total_returned,
    }
    
    return render(request, 'pos/cash_float_list.html', context)


@business_required
def cash_float_give(request, slug=None):
    """Give cash float to a cashier"""
    if request.method == 'POST':
        cashier_id = request.POST.get('cashier')
        amount = request.POST.get('amount')
        float_type = request.POST.get('float_type', 'opening')
        notes = request.POST.get('notes', '')
        
        try:
            cashier = User.objects.get(id=cashier_id)
            amount = Decimal(amount)
            
            if amount <= 0:
                messages.error(request, 'Amount must be greater than zero')
                return redirect('cash_float_give', slug=request.business.slug)
            
            # Create cash float
            cash_float = CashFloat.objects.create(
                business=request.business,
                cashier=cashier,
                given_by=request.user,
                amount=amount,
                float_type=float_type,
                notes=notes
            )
            
            messages.success(
                request, 
                f'Float {cash_float.float_number} of KES {amount:,.2f} given to {cashier.username}'
            )
            return redirect('cash_float_list', slug=request.business.slug)
            
        except User.DoesNotExist:
            messages.error(request, 'Cashier not found')
        except Exception as e:
            messages.error(request, f'Error giving float: {str(e)}')
    
    # Get cashiers
    cashiers = User.objects.filter(
        business_memberships__business=request.business
    ).distinct()
    
    context = {
        'cashiers': cashiers,
    }
    
    return render(request, 'pos/cash_float_give.html', context)


@business_required
def cash_float_return(request, slug=None, pk=None):
    """Return cash float from cashier"""
    cash_float = get_object_or_404(CashFloat, pk=pk, business=request.business)
    
    if cash_float.status != 'active':
        messages.error(request, 'This float has already been returned or reconciled')
        return redirect('cash_float_list', slug=request.business.slug)
    
    if request.method == 'POST':
        returned_amount = request.POST.get('returned_amount')
        notes = request.POST.get('notes', '')
        
        try:
            returned_amount = Decimal(returned_amount)
            
            # Calculate expected return (float + cash sales - change given)
            # Get sales made by this cashier since float was given
            sales = Sale.objects.filter(
                business=request.business,
                cashier=cash_float.cashier,
                created_at__gte=cash_float.given_at,
                created_at__lte=timezone.now()
            )
            
            # Calculate cash received (only cash payments)
            cash_received = Decimal(0)
            for sale in sales:
                cash_payments = sale.payments.filter(payment_method__name='CASH')
                cash_received += cash_payments.aggregate(Sum('amount'))['amount__sum'] or 0
            
            # Calculate total change given
            total_change = sales.aggregate(Sum('change_given'))['change_given__sum'] or 0
            
            # Expected return = float + cash received - change given
            expected_return = cash_float.amount + cash_received - total_change
            
            # Return the float
            cash_float.return_float(returned_amount, notes)
            
            # Show variance message
            variance = returned_amount - expected_return
            if variance == 0:
                messages.success(request, f'Float {cash_float.float_number} returned successfully. No variance.')
            elif variance > 0:
                messages.warning(
                    request, 
                    f'Float {cash_float.float_number} returned with SURPLUS of KES {variance:,.2f}'
                )
            else:
                messages.error(
                    request, 
                    f'Float {cash_float.float_number} returned with SHORTAGE of KES {abs(variance):,.2f}'
                )
            
            return redirect('cash_float_detail', slug=request.business.slug, pk=cash_float.pk)
            
        except Exception as e:
            messages.error(request, f'Error returning float: {str(e)}')
    
    # Calculate expected return for display
    sales = Sale.objects.filter(
        business=request.business,
        cashier=cash_float.cashier,
        created_at__gte=cash_float.given_at,
        created_at__lte=timezone.now()
    )
    
    cash_received = Decimal(0)
    for sale in sales:
        cash_payments = sale.payments.filter(payment_method__name='CASH')
        cash_received += cash_payments.aggregate(Sum('amount'))['amount__sum'] or 0
    
    total_change = sales.aggregate(Sum('change_given'))['change_given__sum'] or 0
    expected_return = cash_float.amount + cash_received - total_change
    
    context = {
        'cash_float': cash_float,
        'sales_count': sales.count(),
        'cash_received': cash_received,
        'total_change': total_change,
        'expected_return': expected_return,
    }
    
    return render(request, 'pos/cash_float_return.html', context)


@business_required
def cash_float_detail(request, slug=None, pk=None):
    """View cash float details"""
    cash_float = get_object_or_404(CashFloat, pk=pk, business=request.business)
    
    # Get sales made during this float period
    end_time = cash_float.returned_at or timezone.now()
    sales = Sale.objects.filter(
        business=request.business,
        cashier=cash_float.cashier,
        created_at__gte=cash_float.given_at,
        created_at__lte=end_time
    ).order_by('-created_at')
    
    # Calculate cash transactions
    cash_received = Decimal(0)
    for sale in sales:
        cash_payments = sale.payments.filter(payment_method__name='CASH')
        cash_received += cash_payments.aggregate(Sum('amount'))['amount__sum'] or 0
    
    total_change = sales.aggregate(Sum('change_given'))['change_given__sum'] or 0
    expected_return = cash_float.amount + cash_received - total_change
    
    context = {
        'cash_float': cash_float,
        'sales': sales,
        'sales_count': sales.count(),
        'cash_received': cash_received,
        'total_change': total_change,
        'expected_return': expected_return,
    }
    
    return render(request, 'pos/cash_float_detail.html', context)


@business_required
def cash_float_reconcile(request, slug=None, pk=None):
    """Reconcile a returned float"""
    cash_float = get_object_or_404(CashFloat, pk=pk, business=request.business)
    
    if cash_float.status != 'returned':
        messages.error(request, 'Only returned floats can be reconciled')
        return redirect('cash_float_detail', slug=request.business.slug, pk=cash_float.pk)
    
    if request.method == 'POST':
        cash_float.reconcile()
        messages.success(request, f'Float {cash_float.float_number} has been reconciled')
        return redirect('cash_float_detail', slug=request.business.slug, pk=cash_float.pk)
    
    return render(request, 'pos/cash_float_reconcile.html', {'cash_float': cash_float})
