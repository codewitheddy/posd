"""
POS Terminal Synchronization Service
Handles bidirectional sync between physical POSTerminals and Central Server:
- Upstream: Ingests queued offline outbox sales, enforces idempotency, deducts branch stock with warning on oversold items.
- Downstream: Packages catalog updates, branch stock display levels, and branch distribution (requisitions/transfers/dispatches) status changes.
"""

from decimal import Decimal
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.contrib.auth.models import User

from .models import (
    POSTerminal, Sale, SaleItem, SalePayment, Product, Category,
    PaymentMethod, Customer, VATCode, BranchStock, StockMovement,
    StockRequisition, StockTransferRequest, Dispatch
)


class TerminalSyncService:
    """
    Core sync engine for offline-resilient POS terminals.
    """

    @classmethod
    def process_sync(cls, terminal: POSTerminal, payload: dict, performed_by=None) -> dict:
        """
        Executes a single-round-trip synchronization for the given POSTerminal.
        """
        now = timezone.now()
        outbox = payload.get('outbox', []) or payload.get('sales', [])
        since_raw = payload.get('since_timestamp') or payload.get('last_sync')

        since_dt = None
        if since_raw:
            if isinstance(since_raw, datetime):
                since_dt = since_raw
            else:
                try:
                    since_dt = parse_datetime(str(since_raw))
                    if since_dt is None:
                        since_dt = datetime.fromisoformat(str(since_raw).replace('Z', '+00:00'))
                except Exception:
                    since_dt = None

        processed_sales = []

        # -------------------------------------------------------------
        # 1. UPSTREAM PROCESSING (Offline Outbox Sales)
        # -------------------------------------------------------------
        for sale_data in outbox:
            idempotency_key = sale_data.get('idempotency_key')
            
            # Idempotency Check: if key already processed, return existing receipt safely
            if idempotency_key:
                existing_sale = Sale.objects.filter(
                    business=terminal.business,
                    idempotency_key=idempotency_key
                ).first()
                if existing_sale:
                    processed_sales.append({
                        'idempotency_key': idempotency_key,
                        'sale_id': existing_sale.id,
                        'invoice_number': existing_sale.invoice_number,
                        'status': 'already_processed',
                        'warnings': [],
                    })
                    continue

            # Process new offline sale
            try:
                with transaction.atomic():
                    # Resolve cashier
                    cashier_id = sale_data.get('cashier_id')
                    cashier = None
                    if cashier_id:
                        cashier = User.objects.filter(pk=cashier_id).first()
                    if not cashier:
                        cashier = performed_by or terminal.business.owner

                    # Resolve customer
                    customer_id = sale_data.get('customer_id')
                    customer = None
                    if customer_id:
                        customer = Customer.objects.filter(pk=customer_id, business=terminal.business).first()

                    # Resolve timestamp
                    client_time_raw = sale_data.get('client_created_at') or sale_data.get('created_at') or sale_data.get('date')
                    client_dt = None
                    if client_time_raw:
                        try:
                            client_dt = parse_datetime(str(client_time_raw))
                            if client_dt is None:
                                client_dt = datetime.fromisoformat(str(client_time_raw).replace('Z', '+00:00'))
                        except Exception:
                            client_dt = None
                    if not client_dt:
                        client_dt = now

                    # Parse numerical fields
                    subtotal = Decimal(str(sale_data.get('subtotal', '0.00')))
                    vat_rate = Decimal(str(sale_data.get('vat_rate', '16.00')))
                    vat_amount = Decimal(str(sale_data.get('vat_amount', '0.00')))
                    discount_type = sale_data.get('discount_type', 'percentage')
                    discount_value = Decimal(str(sale_data.get('discount_value', '0.00')))
                    discount_amount = Decimal(str(sale_data.get('discount_amount', '0.00')))
                    total = Decimal(str(sale_data.get('total', '0.00')))
                    amount_paid = Decimal(str(sale_data.get('amount_paid', total)))
                    change_given = Decimal(str(sale_data.get('change_given', '0.00')))
                    is_credit_sale = bool(sale_data.get('is_credit_sale', False))
                    credit_paid = Decimal(str(sale_data.get('credit_paid', '0.00')))

                    sale = Sale(
                        business=terminal.business,
                        branch=terminal.branch,
                        terminal=terminal,
                        idempotency_key=idempotency_key,
                        is_offline_sync=True,
                        client_created_at=client_dt,
                        date=client_dt,
                        cashier=cashier,
                        customer=customer,
                        subtotal=subtotal,
                        vat_rate=vat_rate,
                        vat_amount=vat_amount,
                        discount_type=discount_type,
                        discount_value=discount_value,
                        discount_amount=discount_amount,
                        total=total,
                        amount_paid=amount_paid,
                        change_given=change_given,
                        is_credit_sale=is_credit_sale,
                        credit_paid=credit_paid,
                    )
                    sale.save()

                    warnings = []
                    items_data = sale_data.get('items', [])
                    for item_data in items_data:
                        product_id = item_data.get('product_id')
                        try:
                            product = Product.objects.get(pk=product_id, business=terminal.business)
                        except Product.DoesNotExist:
                            warnings.append(f"Product ID {product_id} not found in business catalog.")
                            continue

                        quantity = Decimal(str(item_data.get('quantity', '1.000')))
                        unit_price = Decimal(str(item_data.get('unit_price', getattr(product, 'unit_price', Decimal('0.00')))))
                        cost_price_val = item_data.get('cost_price_at_sale')
                        if cost_price_val is not None:
                            cost_price = Decimal(str(cost_price_val))
                        else:
                            cost_price = product.cost_price

                        SaleItem.objects.create(
                            business=terminal.business,
                            sale=sale,
                            product=product,
                            quantity=quantity,
                            unit_price=unit_price,
                            cost_price_at_sale=cost_price,
                            note=item_data.get('note', ''),
                            unit_type=item_data.get('unit_type', 'base'),
                            unit_name=item_data.get('unit_name', ''),
                        )

                        # Deduct from BranchStock with negative stock allowance
                        stock, _ = BranchStock.objects.get_or_create(
                            branch=terminal.branch,
                            product=product,
                            defaults={
                                'average_cost': product.cost_price or Decimal('0.00'),
                                'quantity': Decimal('0.000')
                            }
                        )
                        updated_stock, movement = stock.deduct(
                            qty=quantity,
                            movement_type='sale',
                            reference_obj=sale,
                            user=cashier,
                            terminal=terminal,
                            idempotency_key=idempotency_key,
                            note=f"Offline POS sale via {terminal.terminal_code}"
                        )
                        if updated_stock.quantity < Decimal('0.000'):
                            warnings.append(
                                f"Product '{product.name}' was oversold while offline (current branch balance: {updated_stock.quantity})"
                            )

                    # Create payments
                    payments_data = sale_data.get('payments', [])
                    if payments_data:
                        for pdata in payments_data:
                            pm_id = pdata.get('payment_method_id')
                            pm_code = pdata.get('payment_method') or pdata.get('code')
                            pm = None
                            if pm_id:
                                pm = PaymentMethod.objects.filter(pk=pm_id, business=terminal.business).first()
                            elif pm_code:
                                pm = PaymentMethod.objects.filter(code=pm_code, business=terminal.business).first() or \
                                     PaymentMethod.objects.filter(name__iexact=pm_code, business=terminal.business).first()
                            if not pm:
                                pm, _ = PaymentMethod.objects.get_or_create(
                                    business=terminal.business,
                                    code='CASH',
                                    defaults={'name': 'Cash', 'is_active': True}
                                )
                            payment_amt = Decimal(str(pdata.get('amount', total)))
                            ref_no = pdata.get('reference_number', pdata.get('reference_code', ''))
                            SalePayment.objects.create(
                                business=terminal.business,
                                sale=sale,
                                payment_method=pm,
                                amount=payment_amt,
                                reference_number=ref_no
                            )

                    processed_sales.append({
                        'idempotency_key': idempotency_key,
                        'sale_id': sale.id,
                        'invoice_number': sale.invoice_number,
                        'status': 'processed',
                        'warnings': warnings,
                    })

            except Exception as e:
                processed_sales.append({
                    'idempotency_key': idempotency_key,
                    'status': 'error',
                    'error': str(e),
                    'warnings': [],
                })

        # -------------------------------------------------------------
        # 2. DOWNSTREAM PACKAGING (Updates since last sync)
        # -------------------------------------------------------------
        # Products
        products_qs = Product.objects.filter(business=terminal.business).select_related('unit')
        if since_dt:
            products_qs = products_qs.filter(updated_at__gte=since_dt)
        products_data = [
            {
                'id': p.id,
                'name': p.name,
                'product_code': p.product_code,
                'barcode': p.barcode or '',
                'unit_price': str(p.unit_price),
                'price': str(p.unit_price),
                'cost_price': str(p.cost_price),
                'is_active': p.is_active,
                'unit_of_measure': p.unit.abbreviation if p.unit else '',
                'vat_code_id': p.vat_code_id,
                'category_id': p.category_id,
                'updated_at': p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in products_qs
        ]

        # Categories
        categories_qs = Category.objects.filter(business=terminal.business)
        if since_dt:
            categories_qs = categories_qs.filter(created_at__gte=since_dt)
        categories_data = [
            {
                'id': c.id,
                'name': c.name,
                'is_active': True,
                'created_at': c.created_at.isoformat() if c.created_at else None,
            }
            for c in categories_qs
        ]

        # VAT Codes
        vat_codes_qs = VATCode.objects.filter(business=terminal.business)
        if since_dt:
            vat_codes_qs = vat_codes_qs.filter(updated_at__gte=since_dt)
        vat_codes_data = [
            {
                'id': v.id,
                'code': v.code,
                'name': v.name,
                'vat_rate': str(v.vat_rate),
                'rate': str(v.vat_rate),
                'is_active': v.is_active,
            }
            for v in vat_codes_qs
        ]

        # Payment Methods
        pm_qs = PaymentMethod.objects.filter(business=terminal.business, is_active=True)
        payment_methods_data = [
            {
                'id': pm.id,
                'code': pm.code,
                'name': pm.name,
                'requires_reference': pm.requires_reference,
            }
            for pm in pm_qs
        ]

        # Branch Stock Display Levels
        stock_qs = BranchStock.objects.filter(branch=terminal.branch).select_related('product')
        branch_stock_levels = [
            {
                'product_id': st.product_id,
                'product_name': st.product.name,
                'quantity': str(st.quantity),
                'average_cost': str(st.average_cost),
                'reorder_level': str(st.reorder_level),
                'is_low_stock': st.is_low_stock,
            }
            for st in stock_qs
        ]

        # Requisitions raised by this branch
        req_qs = StockRequisition.objects.filter(
            requesting_branch=terminal.branch
        ).prefetch_related('items__product')
        if since_dt:
            req_qs = req_qs.filter(updated_at__gte=since_dt)
        requisitions_data = [
            {
                'id': r.id,
                'reference_number': r.reference_number,
                'status': r.status,
                'status_display': r.get_status_display(),
                'notes': r.notes,
                'rejection_reason': r.rejection_reason,
                'created_at': r.created_at.isoformat(),
                'updated_at': r.updated_at.isoformat(),
                'items': [
                    {
                        'product_id': it.product_id,
                        'product_name': it.product.name,
                        'requested_quantity': str(it.requested_quantity),
                        'approved_quantity': str(it.approved_quantity) if it.approved_quantity is not None else None,
                        'dispatched_quantity': str(it.dispatched_quantity),
                        'received_quantity': str(it.received_quantity),
                    }
                    for it in r.items.all()
                ]
            }
            for r in req_qs
        ]

        # Inter-Branch Transfers involving this branch
        transfer_qs = StockTransferRequest.objects.filter(
            Q(source_branch=terminal.branch) | Q(destination_branch=terminal.branch)
        ).prefetch_related('items__product')
        if since_dt:
            transfer_qs = transfer_qs.filter(updated_at__gte=since_dt)
        transfers_data = [
            {
                'id': t.id,
                'reference_number': t.reference_number,
                'source_branch_id': t.source_branch_id,
                'destination_branch_id': t.destination_branch_id,
                'status': t.status,
                'status_display': t.get_status_display(),
                'reason': t.reason,
                'rejection_reason': t.rejection_reason,
                'created_at': t.created_at.isoformat(),
                'updated_at': t.updated_at.isoformat(),
                'items': [
                    {
                        'product_id': it.product_id,
                        'product_name': it.product.name,
                        'requested_quantity': str(it.requested_quantity),
                        'approved_quantity': str(it.approved_quantity) if it.approved_quantity is not None else None,
                        'dispatched_quantity': str(it.dispatched_quantity),
                        'received_quantity': str(it.received_quantity),
                    }
                    for it in t.items.all()
                ]
            }
            for t in transfer_qs
        ]

        # Dispatches involving this branch
        dispatch_qs = Dispatch.objects.filter(
            Q(source_branch=terminal.branch) | Q(destination_branch=terminal.branch)
        )
        if since_dt:
            dispatch_qs = dispatch_qs.filter(dispatched_at__gte=since_dt)
        dispatches_data = [
            {
                'id': d.id,
                'reference_number': d.reference_number,
                'source_branch_id': d.source_branch_id,
                'destination_branch_id': d.destination_branch_id,
                'status': d.status,
                'status_display': d.get_status_display(),
                'notes': d.notes,
                'dispatched_at': d.dispatched_at.isoformat() if d.dispatched_at else None,
                'received_at': d.received_at.isoformat() if d.received_at else None,
            }
            for d in dispatch_qs
        ]

        # -------------------------------------------------------------
        # 3. FINALIZE TERMINAL STATE
        # -------------------------------------------------------------
        POSTerminal.objects.filter(pk=terminal.pk).update(
            last_sync_at=now,
            last_active_at=now,
            sync_status='synced'
        )

        return {
            'server_timestamp': now.isoformat(),
            'terminal': {
                'id': terminal.id,
                'terminal_code': terminal.terminal_code,
                'name': terminal.name,
                'branch_id': terminal.branch_id,
                'branch_name': terminal.branch.name if terminal.branch else '',
            },
            'processed_sales': processed_sales,
            'catalog_updates': {
                'products': products_data,
                'categories': categories_data,
                'vat_codes': vat_codes_data,
                'payment_methods': payment_methods_data,
            },
            'branch_stock_levels': branch_stock_levels,
            'distribution_updates': {
                'requisitions': requisitions_data,
                'transfers': transfers_data,
                'dispatches': dispatches_data,
            }
        }
