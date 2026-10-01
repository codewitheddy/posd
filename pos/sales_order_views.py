"""
B2B Sales Order & Delivery Note Back Office Views
Provides listing, creation, details, dispatching, and fulfillment tracking for
wholesale and corporate client distribution workflows.
"""
import logging
from decimal import Decimal
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum, Count, Value, DecimalField
from django.db.models.functions import Coalesce
from django.db import transaction

from pos.models import (
    Business, Customer, Product, Branch,
    SalesOrder, SalesOrderItem, SalesOrderStatus,
    DeliveryNote, DeliveryNoteItem, DeliveryNoteStatus
)
from pos.decorators import business_required, business_permission_required
from pos.sales_order_services import (
    create_sales_order, confirm_sales_order,
    create_delivery_note_from_order, dispatch_delivery_note,
    complete_delivery_note
)

logger = logging.getLogger(__name__)


# ============================================================================
# SALES ORDERS
# ============================================================================

@login_required
@business_required
def sales_order_list(request, slug=None):
    """List B2B Sales Orders with search, filters, pagination, and summary metrics."""
    orders = SalesOrder.objects.filter(business=request.business).select_related(
        'customer', 'created_by', 'branch'
    ).annotate(
        items_count=Count('items', distinct=True)
    )

    # Filters
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        orders = orders.filter(status=status_filter)

    customer_filter = request.GET.get('customer', '').strip()
    if customer_filter:
        orders = orders.filter(customer_id=customer_filter)

    search = request.GET.get('q', '').strip()
    if search:
        orders = orders.filter(
            Q(order_number__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search) |
            Q(notes__icontains=search)
        )

    from_date = request.GET.get('from_date', '').strip()
    if from_date:
        try:
            orders = orders.filter(order_date__gte=datetime.strptime(from_date, '%Y-%m-%d').date())
        except ValueError:
            pass

    to_date = request.GET.get('to_date', '').strip()
    if to_date:
        try:
            orders = orders.filter(order_date__lte=datetime.strptime(to_date, '%Y-%m-%d').date())
        except ValueError:
            pass

    # Summary Metrics
    all_orders = SalesOrder.objects.filter(business=request.business)
    metrics = {
        'total_orders': all_orders.count(),
        'total_value': all_orders.aggregate(
            val=Coalesce(Sum('total_amount'), Value(Decimal('0.00'), output_field=DecimalField(max_digits=14, decimal_places=2)))
        )['val'],
        'draft_count': all_orders.filter(status=SalesOrderStatus.DRAFT).count(),
        'confirmed_count': all_orders.filter(status=SalesOrderStatus.CONFIRMED).count(),
        'delivered_count': all_orders.filter(status=SalesOrderStatus.DELIVERED).count(),
    }

    paginator = Paginator(orders, 25)
    page = request.GET.get('page', 1)
    try:
        orders_page = paginator.page(page)
    except PageNotAnInteger:
        orders_page = paginator.page(1)
    except EmptyPage:
        orders_page = paginator.page(paginator.num_pages)

    customers = Customer.objects.filter(business=request.business, is_active=True).order_by('name')

    context = {
        'orders': orders_page,
        'page_obj': orders_page,
        'paginator': paginator,
        'is_paginated': orders_page.has_other_pages(),
        'metrics': metrics,
        'customers': customers,
        'status_choices': SalesOrderStatus.choices,
        'status_filter': status_filter,
        'customer_filter': customer_filter,
        'search': search,
        'from_date': from_date,
        'to_date': to_date,
        'business_slug': slug or getattr(request.business, 'slug', 'main-store'),
    }
    return render(request, 'pos/sales_orders/order_list.html', context)


@login_required
@business_required
def sales_order_detail(request, slug=None, pk=None):
    """Detailed view of a Sales Order with line items, fulfillment progress, and delivery notes."""
    sales_order = get_object_or_404(
        SalesOrder.objects.select_related('customer', 'created_by', 'confirmed_by', 'branch'),
        business=request.business,
        pk=pk
    )
    items = sales_order.items.select_related('product').all()
    deliveries = sales_order.delivery_notes.select_related('created_by', 'dispatched_by').all()

    can_dispatch = sales_order.status in (
        SalesOrderStatus.CONFIRMED, SalesOrderStatus.PROCESSING, SalesOrderStatus.PARTIALLY_DELIVERED
    ) and any(it.quantity_pending_delivery > Decimal('0.000') for it in items)

    context = {
        'order': sales_order,
        'items': items,
        'deliveries': deliveries,
        'can_dispatch': can_dispatch,
        'can_confirm': sales_order.status == SalesOrderStatus.DRAFT,
        'can_cancel': sales_order.status in (SalesOrderStatus.DRAFT, SalesOrderStatus.CONFIRMED),
        'business_slug': slug or getattr(request.business, 'slug', 'main-store'),
    }
    return render(request, 'pos/sales_orders/order_detail.html', context)


@login_required
@business_required
@require_POST
def sales_order_confirm(request, slug=None, pk=None):
    """Confirm a draft sales order."""
    sales_order = get_object_or_404(SalesOrder, business=request.business, pk=pk)
    try:
        confirm_sales_order(sales_order, user=request.user)
        messages.success(request, f"Sales Order #{sales_order.order_number} confirmed successfully.")
    except Exception as e:
        messages.error(request, f"Error confirming sales order: {e}")
    return redirect('sales_order_detail', slug=slug, pk=pk)


@login_required
@business_required
@require_POST
def sales_order_cancel(request, slug=None, pk=None):
    """Cancel a sales order."""
    sales_order = get_object_or_404(SalesOrder, business=request.business, pk=pk)
    if sales_order.delivery_notes.filter(status=DeliveryNoteStatus.DISPATCHED).exists():
        messages.error(request, "Cannot cancel a sales order with already dispatched deliveries.")
        return redirect('sales_order_detail', slug=slug, pk=pk)

    sales_order.status = SalesOrderStatus.CANCELLED
    sales_order.save(update_fields=['status', 'updated_at'])
    messages.success(request, f"Sales Order #{sales_order.order_number} has been cancelled.")
    return redirect('sales_order_detail', slug=slug, pk=pk)


# ============================================================================
# DELIVERY NOTES / GOODS DISPATCH
# ============================================================================

@login_required
@business_required
def delivery_note_list(request, slug=None):
    """List Goods Dispatch / Delivery Notes with filtering and pagination."""
    deliveries = DeliveryNote.objects.filter(business=request.business).select_related(
        'customer', 'sales_order', 'created_by', 'dispatched_by', 'branch'
    ).annotate(
        items_count=Count('items', distinct=True)
    )

    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        deliveries = deliveries.filter(status=status_filter)

    search = request.GET.get('q', '').strip()
    if search:
        deliveries = deliveries.filter(
            Q(delivery_number__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(carrier_name__icontains=search) |
            Q(tracking_number__icontains=search) |
            Q(driver_name__icontains=search) |
            Q(vehicle_reg__icontains=search)
        )

    all_deliveries = DeliveryNote.objects.filter(business=request.business)
    metrics = {
        'total_deliveries': all_deliveries.count(),
        'draft_count': all_deliveries.filter(status=DeliveryNoteStatus.DRAFT).count(),
        'dispatched_count': all_deliveries.filter(status=DeliveryNoteStatus.DISPATCHED).count(),
        'delivered_count': all_deliveries.filter(status=DeliveryNoteStatus.DELIVERED).count(),
    }

    paginator = Paginator(deliveries, 25)
    page = request.GET.get('page', 1)
    try:
        deliveries_page = paginator.page(page)
    except PageNotAnInteger:
        deliveries_page = paginator.page(1)
    except EmptyPage:
        deliveries_page = paginator.page(paginator.num_pages)

    context = {
        'deliveries': deliveries_page,
        'page_obj': deliveries_page,
        'paginator': paginator,
        'is_paginated': deliveries_page.has_other_pages(),
        'metrics': metrics,
        'status_choices': DeliveryNoteStatus.choices,
        'status_filter': status_filter,
        'search': search,
        'business_slug': slug or getattr(request.business, 'slug', 'main-store'),
    }
    return render(request, 'pos/deliveries/delivery_list.html', context)


@login_required
@business_required
def delivery_note_detail(request, slug=None, pk=None):
    """Detailed view of a Goods Dispatch / Delivery Note."""
    delivery = get_object_or_404(
        DeliveryNote.objects.select_related('customer', 'sales_order', 'created_by', 'dispatched_by', 'branch'),
        business=request.business,
        pk=pk
    )
    items = delivery.items.select_related('product', 'sales_order_item').all()

    context = {
        'delivery': delivery,
        'items': items,
        'can_dispatch': delivery.status == DeliveryNoteStatus.DRAFT,
        'can_complete': delivery.status == DeliveryNoteStatus.DISPATCHED,
        'business_slug': slug or getattr(request.business, 'slug', 'main-store'),
    }
    return render(request, 'pos/deliveries/delivery_detail.html', context)


@login_required
@business_required
@require_POST
def delivery_note_dispatch(request, slug=None, pk=None):
    """Execute physical stock deduction and GL COGS journal posting for a delivery note."""
    delivery = get_object_or_404(DeliveryNote, business=request.business, pk=pk)
    try:
        dispatch_delivery_note(delivery, user=request.user)
        messages.success(request, f"Delivery Note #{delivery.delivery_number} successfully dispatched and stock deducted.")
    except Exception as e:
        messages.error(request, f"Error dispatching delivery note: {e}")
    return redirect('delivery_note_detail', slug=slug, pk=pk)


@login_required
@business_required
@require_POST
def delivery_note_complete(request, slug=None, pk=None):
    """Mark a dispatched delivery note as delivered upon client signoff."""
    delivery = get_object_or_404(DeliveryNote, business=request.business, pk=pk)
    recipient_name = request.POST.get('recipient_name', '').strip()
    try:
        complete_delivery_note(delivery, recipient_name=recipient_name, user=request.user)
        messages.success(request, f"Delivery Note #{delivery.delivery_number} marked as Delivered.")
    except Exception as e:
        messages.error(request, f"Error completing delivery note: {e}")
    return redirect('delivery_note_detail', slug=slug, pk=pk)


@login_required
@business_required
def delivery_note_create_from_order(request, slug=None, order_id=None):
    """Generate delivery note from Sales Order."""
    sales_order = get_object_or_404(SalesOrder, business=request.business, pk=order_id)
    if request.method == 'POST':
        carrier_info = {
            'carrier_name': request.POST.get('carrier_name', '').strip(),
            'tracking_number': request.POST.get('tracking_number', '').strip(),
            'vehicle_reg': request.POST.get('vehicle_reg', '').strip(),
            'driver_name': request.POST.get('driver_name', '').strip(),
            'driver_phone': request.POST.get('driver_phone', '').strip(),
            'recipient_name': request.POST.get('recipient_name', '').strip(),
            'delivery_address': request.POST.get('delivery_address', '').strip(),
            'notes': request.POST.get('notes', '').strip(),
        }

        # Parse item quantities from POST
        quantities = {}
        for key, val in request.POST.items():
            if key.startswith('item_qty_') and val:
                try:
                    item_id = int(key.replace('item_qty_', ''))
                    quantities[item_id] = Decimal(str(val))
                except (ValueError, InvalidOperation):
                    pass

        try:
            dn = create_delivery_note_from_order(
                sales_order=sales_order,
                items_quantities=quantities if quantities else None,
                user=request.user,
                carrier_info=carrier_info,
            )
            messages.success(request, f"Draft Delivery Note #{dn.delivery_number} created.")
            return redirect('delivery_note_detail', slug=slug, pk=dn.pk)
        except Exception as e:
            messages.error(request, f"Error creating delivery note: {e}")

    items = sales_order.items.select_related('product').all()
    context = {
        'order': sales_order,
        'items': items,
        'business_slug': slug or getattr(request.business, 'slug', 'main-store'),
    }
    return render(request, 'pos/deliveries/delivery_create.html', context)
