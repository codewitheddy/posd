"""
CRM Views: Customer Credit, Campaigns, Segments, Reports
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q, F, Avg
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from decimal import Decimal
import csv
import json

from .models import (
    Customer, CustomerPayment, CustomerSegment, Campaign,
    Sale, PaymentMethod, LoyaltyTransaction, Business
)
from .decorators import business_required, business_permission_required


# ==================== CUSTOMER CREDIT ====================

@business_required
def customer_credit_list(request, slug=None):
    """List customers with credit balances"""
    customers = Customer.objects.filter(
        business=request.business,
        credit_limit__gt=0,
    ).order_by('-credit_balance')

    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(name__icontains=search) | Q(phone__icontains=search)
        )

    status = request.GET.get('status', '')
    if status == 'overdue':
        customers = customers.filter(credit_balance__gt=0)
    elif status == 'clear':
        customers = customers.filter(credit_balance=0)

    total_outstanding = customers.aggregate(t=Sum('credit_balance'))['t'] or 0

    context = {
        'customers': customers,
        'search': search,
        'status': status,
        'total_outstanding': total_outstanding,
    }
    return render(request, 'pos/crm/credit_list.html', context)


@business_required
def customer_credit_detail(request, slug=None, pk=None):
    """Customer credit statement"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)

    credit_sales = Sale.objects.filter(
        business=request.business,
        customer=customer,
        is_credit_sale=True,
    ).order_by('-date')

    payments = CustomerPayment.objects.filter(
        business=request.business,
        customer=customer,
    ).order_by('-created_at')

    payment_methods = PaymentMethod.objects.filter(business=request.business, is_active=True)

    # Aging buckets
    today = timezone.now().date()
    aging = {'current': 0, '30': 0, '60': 0, '90plus': 0}
    for sale in credit_sales:
        days_old = (today - sale.date.date()).days
        outstanding = sale.total - sale.credit_paid
        if outstanding <= 0:
            continue
        if days_old <= 30:
            aging['current'] += float(outstanding)
        elif days_old <= 60:
            aging['30'] += float(outstanding)
        elif days_old <= 90:
            aging['60'] += float(outstanding)
        else:
            aging['90plus'] += float(outstanding)

    context = {
        'customer': customer,
        'credit_sales': credit_sales,
        'payments': payments,
        'payment_methods': payment_methods,
        'aging': aging,
    }
    return render(request, 'pos/crm/credit_detail.html', context)


@business_required
def customer_credit_payment(request, slug=None, pk=None):
    """Record a payment against customer credit"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0'))
        payment_method_id = request.POST.get('payment_method')
        reference = request.POST.get('reference', '')
        notes = request.POST.get('notes', '')

        if amount <= 0:
            messages.error(request, 'Amount must be greater than zero.')
        elif amount > customer.credit_balance:
            messages.error(request, f'Amount exceeds outstanding balance of KES {customer.credit_balance}.')
        else:
            pm = None
            if payment_method_id:
                pm = PaymentMethod.objects.filter(pk=payment_method_id, business=request.business).first()

            CustomerPayment.objects.create(
                business=request.business,
                customer=customer,
                amount=amount,
                payment_method=pm,
                reference=reference,
                notes=notes,
                recorded_by=request.user,
            )
            messages.success(request, f'Payment of KES {amount} recorded for {customer.name}.')
            return redirect('customer_credit_detail', slug=slug, pk=pk)

    payment_methods = PaymentMethod.objects.filter(business=request.business, is_active=True)
    return render(request, 'pos/crm/credit_payment.html', {
        'customer': customer,
        'payment_methods': payment_methods,
    })


@business_required
def credit_aging_report(request, slug=None):
    """Aging report for all customers with credit"""
    customers = Customer.objects.filter(
        business=request.business,
        credit_balance__gt=0,
    )

    today = timezone.now().date()
    rows = []
    totals = {'current': 0, '30': 0, '60': 0, '90plus': 0, 'total': 0}

    for customer in customers:
        aging = {'current': 0, '30': 0, '60': 0, '90plus': 0}
        credit_sales = Sale.objects.filter(
            business=request.business,
            customer=customer,
            is_credit_sale=True,
        )
        for sale in credit_sales:
            outstanding = float(sale.total - sale.credit_paid)
            if outstanding <= 0:
                continue
            days_old = (today - sale.date.date()).days
            if days_old <= 30:
                aging['current'] += outstanding
            elif days_old <= 60:
                aging['30'] += outstanding
            elif days_old <= 90:
                aging['60'] += outstanding
            else:
                aging['90plus'] += outstanding

        row_total = sum(aging.values())
        if row_total > 0:
            rows.append({'customer': customer, **aging, 'total': row_total})
            for k in totals:
                if k != 'total':
                    totals[k] += aging.get(k, 0)
            totals['total'] += row_total

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="aging_report.csv"'
        w = csv.writer(response)
        w.writerow(['Customer', 'Phone', '0-30 Days', '31-60 Days', '61-90 Days', '90+ Days', 'Total'])
        for row in rows:
            w.writerow([
                row['customer'].name, row['customer'].phone,
                row['current'], row['30'], row['60'], row['90plus'], row['total']
            ])
        return response

    return render(request, 'pos/crm/aging_report.html', {
        'rows': rows, 'totals': totals,
    })


# ==================== CUSTOMER STATEMENT ====================

@business_required
def customer_statement(request, slug=None, pk=None):
    """Printable customer credit statement"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    credit_sales = Sale.objects.filter(
        business=request.business, customer=customer, is_credit_sale=True
    ).order_by('date')
    payments = CustomerPayment.objects.filter(
        business=request.business, customer=customer
    ).order_by('created_at')

    if date_from:
        credit_sales = credit_sales.filter(date__date__gte=date_from)
        payments = payments.filter(created_at__date__gte=date_from)
    if date_to:
        credit_sales = credit_sales.filter(date__date__lte=date_to)
        payments = payments.filter(created_at__date__lte=date_to)

    # Build combined timeline
    timeline = []
    for s in credit_sales:
        timeline.append({
            'date': s.date.date(), 'type': 'sale',
            'description': f'Invoice {s.invoice_number}',
            'debit': s.total, 'credit': Decimal('0'),
        })
    for p in payments:
        timeline.append({
            'date': p.created_at.date(), 'type': 'payment',
            'description': f'Payment{" - " + p.reference if p.reference else ""}',
            'debit': Decimal('0'), 'credit': p.amount,
        })
    timeline.sort(key=lambda x: x['date'])

    # Running balance
    balance = Decimal('0')
    for row in timeline:
        balance += row['debit'] - row['credit']
        row['balance'] = balance

    return render(request, 'pos/crm/customer_statement.html', {
        'customer': customer,
        'timeline': timeline,
        'closing_balance': balance,
        'date_from': date_from,
        'date_to': date_to,
    })


# ==================== SEGMENTS ====================

@business_required
@business_permission_required('is_manager')
def segment_list(request, slug=None):
    segments = CustomerSegment.objects.filter(business=request.business).annotate(
        customer_count=Count('id')
    )
    return render(request, 'pos/crm/segment_list.html', {'segments': segments})


@business_required
@business_permission_required('is_manager')
def segment_create(request, slug=None):
    if request.method == 'POST':
        CustomerSegment.objects.create(
            business=request.business,
            name=request.POST['name'],
            description=request.POST.get('description', ''),
            criteria=request.POST['criteria'],
            criteria_value=request.POST.get('criteria_value', ''),
        )
        messages.success(request, 'Segment created.')
        return redirect('segment_list', slug=slug)
    return render(request, 'pos/crm/segment_form.html', {'segment': None})


@business_required
@business_permission_required('is_manager')
def segment_edit(request, slug=None, pk=None):
    segment = get_object_or_404(CustomerSegment, business=request.business, pk=pk)
    if request.method == 'POST':
        segment.name = request.POST['name']
        segment.description = request.POST.get('description', '')
        segment.criteria = request.POST['criteria']
        segment.criteria_value = request.POST.get('criteria_value', '')
        segment.save()
        messages.success(request, 'Segment updated.')
        return redirect('segment_list', slug=slug)
    return render(request, 'pos/crm/segment_form.html', {'segment': segment})


@business_required
@business_permission_required('is_manager')
def segment_customers(request, slug=None, pk=None):
    """Preview customers in a segment"""
    segment = get_object_or_404(CustomerSegment, business=request.business, pk=pk)
    customers = segment.get_customers()
    return render(request, 'pos/crm/segment_customers.html', {
        'segment': segment, 'customers': customers,
    })


# ==================== CAMPAIGNS ====================

@business_required
@business_permission_required('is_manager')
def campaign_list(request, slug=None):
    campaigns = Campaign.objects.filter(business=request.business)
    return render(request, 'pos/crm/campaign_list.html', {'campaigns': campaigns})


@business_required
@business_permission_required('is_manager')
def campaign_create(request, slug=None):
    segments = CustomerSegment.objects.filter(business=request.business)
    if request.method == 'POST':
        segment_id = request.POST.get('segment')
        segment = CustomerSegment.objects.filter(pk=segment_id, business=request.business).first() if segment_id else None
        Campaign.objects.create(
            business=request.business,
            name=request.POST['name'],
            subject=request.POST.get('subject', ''),
            message=request.POST['message'],
            channel=request.POST['channel'],
            segment=segment,
            created_by=request.user,
        )
        messages.success(request, 'Campaign created.')
        return redirect('campaign_list', slug=slug)
    return render(request, 'pos/crm/campaign_form.html', {'campaign': None, 'segments': segments})


@business_required
@business_permission_required('is_manager')
def campaign_detail(request, slug=None, pk=None):
    campaign = get_object_or_404(Campaign, business=request.business, pk=pk)
    customers = campaign.segment.get_customers() if campaign.segment else Customer.objects.filter(business=request.business, is_active=True)
    return render(request, 'pos/crm/campaign_detail.html', {
        'campaign': campaign, 'customers': customers,
    })


@business_required
@business_permission_required('is_manager')
def campaign_send(request, slug=None, pk=None):
    """Mark campaign as sent (actual sending via email_service)"""
    campaign = get_object_or_404(Campaign, business=request.business, pk=pk)
    if request.method == 'POST' and campaign.status == 'draft':
        customers = campaign.segment.get_customers() if campaign.segment else Customer.objects.filter(business=request.business, is_active=True)
        sent = 0
        failed = 0

        if campaign.channel == 'email':
            from .email_service import EmailService
            email_service = EmailService(request.business)
            for customer in customers:
                if customer.email:
                    try:
                        email_service.send_custom_email(
                            to_email=customer.email,
                            subject=campaign.subject or campaign.name,
                            message=campaign.message,
                            customer_name=customer.name,
                        )
                        sent += 1
                    except Exception:
                        failed += 1

        campaign.status = 'sent'
        campaign.sent_at = timezone.now()
        campaign.recipients_count = sent
        campaign.save()
        messages.success(request, f'Campaign sent to {sent} customers. {failed} failed.')
    return redirect('campaign_detail', slug=slug, pk=pk)


# ==================== CRM REPORTS ====================

@business_required
@business_permission_required('can_view_reports')
def crm_reports(request, slug=None):
    """CRM reports hub"""
    return render(request, 'pos/crm/reports.html')


@business_required
@business_permission_required('can_view_reports')
def report_top_customers(request, slug=None):
    days = int(request.GET.get('days', 90))
    since = timezone.now() - timezone.timedelta(days=days)

    customers = Customer.objects.filter(business=request.business).annotate(
        purchase_count=Count('purchases', filter=Q(purchases__date__gte=since)),
        amount_spent=Sum('purchases__total', filter=Q(purchases__date__gte=since)),
    ).filter(amount_spent__gt=0).order_by('-amount_spent')[:50]

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="top_customers.csv"'
        w = csv.writer(response)
        w.writerow(['Name', 'Phone', 'Type', 'Purchases', 'Total Spent'])
        for c in customers:
            w.writerow([c.name, c.phone, c.customer_type, c.purchase_count, c.amount_spent or 0])
        return response

    return render(request, 'pos/crm/report_top_customers.html', {
        'customers': customers, 'days': days,
    })


@business_required
@business_permission_required('can_view_reports')
def report_loyalty(request, slug=None):
    """Loyalty program report"""
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timezone.timedelta(days=days)

    earned = LoyaltyTransaction.objects.filter(
        customer__business=request.business,
        transaction_type='earn',
        created_at__gte=since,
    ).aggregate(total=Sum('points'), count=Count('id'))

    redeemed = LoyaltyTransaction.objects.filter(
        customer__business=request.business,
        transaction_type='redeem',
        created_at__gte=since,
    ).aggregate(total=Sum('points'), count=Count('id'))

    top_earners = Customer.objects.filter(business=request.business).order_by('-loyalty_points')[:20]

    tier_breakdown = Customer.objects.filter(business=request.business, is_active=True).values('tier').annotate(count=Count('id')).order_by('tier')

    return render(request, 'pos/crm/report_loyalty.html', {
        'earned': earned,
        'redeemed': redeemed,
        'top_earners': top_earners,
        'tier_breakdown': tier_breakdown,
        'days': days,
    })


@business_required
@business_permission_required('can_view_reports')
def report_credit(request, slug=None):
    """Customer credit report"""
    customers = Customer.objects.filter(
        business=request.business,
        credit_balance__gt=0,
    ).order_by('-credit_balance')

    total_outstanding = customers.aggregate(t=Sum('credit_balance'))['t'] or 0
    total_limit = customers.aggregate(t=Sum('credit_limit'))['t'] or 0

    recent_payments = CustomerPayment.objects.filter(
        business=request.business,
    ).select_related('customer').order_by('-created_at')[:20]

    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="credit_report.csv"'
        w = csv.writer(response)
        w.writerow(['Customer', 'Phone', 'Credit Limit', 'Outstanding', 'Available'])
        for c in customers:
            w.writerow([c.name, c.phone, c.credit_limit, c.credit_balance, c.get_available_credit()])
        return response

    return render(request, 'pos/crm/report_credit.html', {
        'customers': customers,
        'total_outstanding': total_outstanding,
        'total_limit': total_limit,
        'recent_payments': recent_payments,
    })


# ==================== CUSTOMER DETAIL ENHANCED ====================

@business_required
def customer_detail_enhanced(request, slug=None, pk=None):
    """Enhanced customer detail with credit, loyalty, timeline"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)

    purchases = Sale.objects.filter(
        business=request.business, customer=customer
    ).prefetch_related('loyalty_transactions').order_by('-date')[:20]

    credit_payments = CustomerPayment.objects.filter(
        business=request.business, customer=customer
    ).order_by('-created_at')[:10]

    loyalty_txns = customer.loyalty_transactions.order_by('-created_at')[:10]

    tier_info = customer.get_tier_display_info()
    progress_percentage = 0
    points_to_next = 0
    if tier_info['next']:
        points_to_next = tier_info['next'] - customer.lifetime_points
        progress_percentage = min(100, (customer.lifetime_points / tier_info['next']) * 100)

    context = {
        'customer': customer,
        'purchases': purchases,
        'credit_payments': credit_payments,
        'loyalty_txns': loyalty_txns,
        'tier_info': tier_info,
        'progress_percentage': progress_percentage,
        'points_to_next': points_to_next,
        'tags': customer.get_tags_list(),
    }
    return render(request, 'pos/crm/customer_detail.html', context)


# ==================== CREDIT SALE API ====================

@business_required
def api_customer_credit_info(request, slug=None, pk=None):
    """AJAX: return customer credit info for POS"""
    customer = get_object_or_404(Customer, business=request.business, pk=pk)
    return JsonResponse({
        'credit_limit': float(customer.credit_limit),
        'credit_balance': float(customer.credit_balance),
        'available_credit': float(customer.get_available_credit()),
        'loyalty_points': customer.loyalty_points,
        'tier': customer.tier,
        'customer_type': customer.customer_type,
    })
