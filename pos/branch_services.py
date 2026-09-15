"""
Service layer for multi-branch operations.
BranchStockService, StockTransferService, ConsolidatedReportService.
"""
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Count, F, Q, ExpressionWrapper, DecimalField
from django.utils import timezone
from django.conf import settings

from .models import (
    Branch, BranchMembership, BranchStock, StockTransfer,
    BranchPriceOverride, Product, Sale, SaleItem, BusinessMembership,
    InsufficientStockError, BranchInactiveError, PlanLimitError,
    InvalidTransferStateError, StockRequisition, StockRequisitionItem,
    StockTransferRequest, StockTransferItem, Dispatch, DispatchItem, StockMovement,
    TransferEvent, TransferApprovalRule,
)
from django.core.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Access & Permission helpers
# ---------------------------------------------------------------------------

def is_owner_or_admin(user, business):
    """Return True if user is owner/admin of the business or a superuser."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    if business and getattr(business, 'owner_id', None) == user.id:
        return True
    return BusinessMembership.objects.filter(
        user=user, business=business, is_active=True,
        role__in=['owner', 'admin'],
    ).exists() or BranchMembership.objects.filter(
        user=user, branch__business=business, is_active=True,
        role='hq_admin',
    ).exists()


def is_branch_manager(user, branch):
    """Return True if user is a branch manager or owner/admin."""
    if is_owner_or_admin(user, branch.business):
        return True
    return BranchMembership.objects.filter(
        user=user, branch=branch, is_active=True,
        role__in=['manager', 'branch_manager', 'stock_manager'],
    ).exists()


def get_user_branches(user, business):
    """Return branches the user can access (all for owner/admin/hq_admin, assigned for others)."""
    if is_owner_or_admin(user, business):
        return Branch.objects.filter(business=business, is_active=True)
    return Branch.objects.filter(
        business=business,
        is_active=True,
        memberships__user=user,
        memberships__is_active=True,
    ).distinct()


def can_user_request_transfer(user, business, branch=None):
    """Check if user is authorized to raise a transfer request."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or is_owner_or_admin(user, business):
        return True
    if user.has_perm('pos.add_stocktransferrequest'):
        return True
    if branch:
        return BranchMembership.objects.filter(
            user=user, branch=branch, is_active=True,
            role__in=['manager', 'branch_manager', 'stock_manager', 'cashier'],
        ).exists()
    return False


def can_user_approve_transfer(user, business, source_branch=None):
    """Check if user is authorized to approve a transfer request."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or is_owner_or_admin(user, business):
        return True
    if user.has_perm('pos.change_stocktransferrequest'):
        return True
    if source_branch:
        return is_branch_manager(user, source_branch)
    return False


def can_user_dispatch_transfer(user, business, source_branch=None):
    """Check if user is authorized to dispatch goods."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or is_owner_or_admin(user, business):
        return True
    if user.has_perm('pos.add_dispatch'):
        return True
    if source_branch:
        return is_branch_manager(user, source_branch)
    return False


def can_user_receive_transfer(user, business, dest_branch=None):
    """Check if user is authorized to receive goods at destination."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or is_owner_or_admin(user, business):
        return True
    if user.has_perm('pos.change_dispatch'):
        return True
    if dest_branch:
        return BranchMembership.objects.filter(
            user=user, branch=dest_branch, is_active=True,
        ).exists()
    return False


def can_user_resolve_discrepancy(user, business):
    """Check if user is authorized to resolve transfer discrepancies."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or is_owner_or_admin(user, business):
        return True
    return user.has_perm('pos.change_stocktransferrequest')


def branch_required(view_func):
    """View decorator — returns 403 if request.branch is None."""
    from functools import wraps
    from django.http import HttpResponseForbidden

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, 'branch', None):
            return HttpResponseForbidden('A branch context is required for this action.')
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Transfer Audit & Rule Helpers
# ---------------------------------------------------------------------------

def log_transfer_event(business=None, parent_obj=None, from_status='', to_status='', event_type='note_added', user=None, notes='', metadata=None):
    """Record an immutable TransferEvent row for audit history."""
    if not business and parent_obj:
        business = getattr(parent_obj, 'business', None)

    req_obj = parent_obj if isinstance(parent_obj, StockRequisition) else None
    trf_obj = parent_obj if isinstance(parent_obj, StockTransferRequest) else None
    dsp_obj = parent_obj if isinstance(parent_obj, Dispatch) else None

    if dsp_obj:
        if dsp_obj.requisition:
            req_obj = dsp_obj.requisition
        if dsp_obj.transfer_request:
            trf_obj = dsp_obj.transfer_request

    return TransferEvent.objects.create(
        business=business,
        transfer_request=trf_obj,
        requisition=req_obj,
        dispatch=dsp_obj,
        from_status=from_status or '',
        to_status=to_status or getattr(parent_obj, 'status', ''),
        event_type=event_type,
        performed_by=user,
        notes=notes or '',
        metadata=metadata or {},
    )


def evaluate_transfer_approval_rules(business, source_branch, dest_branch, items_data, user=None):
    """
    Calculate estimated total monetary value and evaluate active TransferApprovalRules.
    Returns: dict(total_estimated_value, total_quantity, requires_approval, auto_approved, rule_applied)
    """
    total_value = Decimal('0.00')
    total_qty = Decimal('0.000')

    for item in items_data:
        p_val = item.get('product_id') if 'product_id' in item else item.get('product')
        p_id = p_val.id if hasattr(p_val, 'id') else int(p_val)
        q_val = item.get('quantity') if 'quantity' in item else item.get('requested_quantity', 0)
        qty = Decimal(str(q_val))
        if qty <= 0:
            continue

        total_qty += qty
        src_stock = BranchStock.objects.filter(branch=source_branch, product_id=p_id).first()
        if src_stock and src_stock.average_cost > 0:
            unit_cost = src_stock.average_cost
        else:
            product = Product.objects.filter(pk=p_id).first()
            unit_cost = product.cost_price if product else Decimal('0.00')

        total_value += (qty * unit_cost).quantize(Decimal('0.01'))

    rule = TransferApprovalRule.objects.filter(business=business, is_active=True).first()
    if not rule:
        return {
            'total_estimated_value': total_value,
            'total_quantity': total_qty,
            'requires_approval': True,
            'auto_approved': False,
            'rule_applied': None,
        }

    if rule.auto_approve_below_threshold:
        is_under_val = (rule.min_value_threshold <= 0) or (total_value <= rule.min_value_threshold)
        is_under_qty = (rule.min_quantity_threshold <= 0) or (total_qty <= rule.min_quantity_threshold)
        if is_under_val and is_under_qty and not rule.requires_hq_approval:
            return {
                'total_estimated_value': total_value,
                'total_quantity': total_qty,
                'requires_approval': False,
                'auto_approved': True,
                'rule_applied': rule.name,
            }

    return {
        'total_estimated_value': total_value,
        'total_quantity': total_qty,
        'requires_approval': True,
        'auto_approved': False,
        'rule_applied': rule.name,
    }


# ---------------------------------------------------------------------------
# BranchStockService
# ---------------------------------------------------------------------------

class BranchStockService:

    @staticmethod
    def get_or_create(branch, product):
        """Get or create a BranchStock record (quantity=0, cost=product.cost_price for new)."""
        cost = getattr(product, 'cost_price', Decimal('0.00')) or Decimal('0.00')
        reorder = getattr(product, 'low_stock_threshold', Decimal('10.000')) or Decimal('10.000')
        stock, _ = BranchStock.objects.get_or_create(
            branch=branch, product=product,
            defaults={
                'quantity': Decimal('0'),
                'average_cost': cost,
                'reorder_level': reorder,
            },
        )
        return stock

    @staticmethod
    def deduct(branch, product, qty, movement_type='sale', reference_obj=None, user=None, note='', unit_cost=None):
        """
        Deduct qty from branch stock atomically with append-only ledger logging.
        Does not hard-block negative stock; records resulted_in_negative_stock.
        """
        if not branch.is_active:
            raise BranchInactiveError(f"Branch '{branch.name}' is inactive.")
        stock = BranchStockService.get_or_create(branch, product)
        return stock.deduct(
            qty=qty, movement_type=movement_type, reference_obj=reference_obj,
            user=user, note=note, unit_cost=unit_cost
        )[0]

    @staticmethod
    def add(branch, product, qty, unit_cost=None, movement_type='purchase_in', reference_obj=None, user=None, note=''):
        """Add qty to branch stock atomically with moving-average recalculation."""
        stock = BranchStockService.get_or_create(branch, product)
        cost = unit_cost if unit_cost is not None else stock.average_cost
        return stock.receive(
            qty=qty, unit_cost=cost, movement_type=movement_type,
            reference_obj=reference_obj, user=user, note=note
        )[0]

    @staticmethod
    def adjust(branch, product, qty_change, reason, adjustment_type, user=None):
        """Create a stock adjustment and update BranchStock and StockMovement."""
        stock = BranchStockService.get_or_create(branch, product)
        qty_change = Decimal(str(qty_change))
        if qty_change > 0:
            stock.receive(
                qty=qty_change, unit_cost=stock.average_cost,
                movement_type='manual_adjustment', user=user, note=f"{adjustment_type}: {reason}"
            )
        elif qty_change < 0:
            m_type = 'damage_writeoff' if adjustment_type == 'damaged' else ('expiry_writeoff' if adjustment_type == 'expired' else 'manual_adjustment')
            stock.deduct(
                qty=abs(qty_change), movement_type=m_type,
                user=user, note=f"{adjustment_type}: {reason}"
            )
        return stock

    @staticmethod
    def get_low_stock_for_branch(branch):
        """Return BranchStock records at or below their reorder_level."""
        return BranchStock.objects.filter(
            branch=branch,
            quantity__lte=F('reorder_level')
        ).select_related('product', 'product__category').order_by('product__name')

    @staticmethod
    def aggregated_stock(business, product):
        """Sum of BranchStock.quantity across all branches for a product."""
        result = BranchStock.objects.filter(
            branch__business=business, product=product
        ).aggregate(total=Sum('quantity'))['total']
        return result or Decimal('0')

    @staticmethod
    def get_effective_price(branch, product):
        """Return BranchPriceOverride price if set, else product.unit_price."""
        try:
            override = BranchPriceOverride.objects.get(branch=branch, product=product)
            return override.price
        except BranchPriceOverride.DoesNotExist:
            return product.unit_price


# ---------------------------------------------------------------------------
# DistributionService (HQ Requisitions & Inter-Branch Transfers)
# ---------------------------------------------------------------------------

class DistributionService:

    @staticmethod
    @transaction.atomic
    def create_requisition(business, requesting_branch, items_data, user, notes=''):
        """
        Create a stock requisition from requesting_branch to HQ.
        items_data: list of dicts [{'product_id': ..., 'quantity': ...}]
        """
        requisition = StockRequisition.objects.create(
            business=business,
            requesting_branch=requesting_branch,
            requested_by=user,
            notes=notes,
            status='pending',
        )
        for item in items_data:
            p_val = item.get('product_id') if 'product_id' in item else item.get('product')
            p_id = p_val.id if hasattr(p_val, 'id') else int(p_val)
            q_val = item.get('quantity') if 'quantity' in item else item.get('requested_quantity', 0)
            qty = Decimal(str(q_val))
            if qty > 0:
                StockRequisitionItem.objects.create(
                    requisition=requisition,
                    product_id=p_id,
                    requested_quantity=qty,
                    notes=item.get('notes', ''),
                )

        log_transfer_event(
            business=business,
            parent_obj=requisition,
            from_status='',
            to_status='pending',
            event_type='created',
            user=user,
            notes=f"Requisition {requisition.reference_number} raised by {user.username if user else 'System'}.",
        )
        return requisition

    @staticmethod
    @transaction.atomic
    def approve_requisition(requisition=None, approved_items_data=None, user=None, approved_items_map=None):
        """Approve requisition by HQ Admin with optional quantity adjustments."""
        approved_items_data = approved_items_data if approved_items_data is not None else (approved_items_map or {})
        requisition = StockRequisition.objects.select_for_update().get(pk=requisition.pk)

        if requisition.status not in ('pending', 'approved'):
            raise ValidationError(f"Cannot approve requisition in status '{requisition.status}'.")

        old_status = requisition.status
        for item in requisition.items.all():
            if item.id in approved_items_data:
                appr_qty = Decimal(str(approved_items_data[item.id]))
                item.approved_quantity = appr_qty
                item.save(update_fields=['approved_quantity'])
            elif item.approved_quantity is None:
                item.approved_quantity = item.requested_quantity
                item.save(update_fields=['approved_quantity'])

        requisition.status = 'approved'
        requisition.approved_by = user
        requisition.approved_at = timezone.now()
        requisition.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        log_transfer_event(
            business=requisition.business,
            parent_obj=requisition,
            from_status=old_status,
            to_status='approved',
            event_type='approved',
            user=user,
            notes=f"Requisition approved by {user.username if user else 'HQ Admin'}.",
        )
        return requisition

    @staticmethod
    @transaction.atomic
    def reject_requisition(requisition, user, reason=''):
        """Reject a requisition."""
        requisition = StockRequisition.objects.select_for_update().get(pk=requisition.pk)
        if requisition.status not in ('pending', 'approved'):
            raise ValidationError(f"Cannot reject requisition in status '{requisition.status}'.")

        old_status = requisition.status
        requisition.status = 'rejected'
        requisition.rejection_reason = reason
        requisition.save(update_fields=['status', 'rejection_reason', 'updated_at'])

        log_transfer_event(
            business=requisition.business,
            parent_obj=requisition,
            from_status=old_status,
            to_status='rejected',
            event_type='rejected',
            user=user,
            notes=f"Requisition rejected: {reason}",
        )
        return requisition

    @staticmethod
    @transaction.atomic
    def create_transfer_request(business, source_branch, dest_branch, items_data, user, reason='', draft=False):
        """
        Create an inter-branch transfer request with approval rule evaluation and cost snapshots.
        """
        if source_branch.pk == dest_branch.pk:
            raise ValidationError("Source and destination branch must be different.")

        eval_res = evaluate_transfer_approval_rules(business, source_branch, dest_branch, items_data, user)
        auto_appr = eval_res['auto_approved'] and not draft

        if draft:
            initial_status = 'draft'
            event_type = 'created'
        elif auto_appr:
            initial_status = 'approved'
            event_type = 'auto_approved'
        else:
            initial_status = 'pending'
            event_type = 'submitted'

        transfer_req = StockTransferRequest.objects.create(
            business=business,
            source_branch=source_branch,
            destination_branch=dest_branch,
            requested_by=user,
            approved_by=user if auto_appr else None,
            approved_at=timezone.now() if auto_appr else None,
            reason=reason,
            status=initial_status,
            total_estimated_value=eval_res['total_estimated_value'],
            requires_approval=eval_res['requires_approval'],
            auto_approved=auto_appr,
        )

        for item in items_data:
            p_val = item.get('product_id') if 'product_id' in item else item.get('product')
            p_id = p_val.id if hasattr(p_val, 'id') else int(p_val)
            q_val = item.get('quantity') if 'quantity' in item else item.get('requested_quantity', 0)
            qty = Decimal(str(q_val))
            if qty > 0:
                # Capture current source moving average cost snapshot
                src_stock = BranchStock.objects.filter(branch=source_branch, product_id=p_id).first()
                cost_snap = src_stock.average_cost if src_stock else Decimal('0.00')

                StockTransferItem.objects.create(
                    transfer_request=transfer_req,
                    product_id=p_id,
                    requested_quantity=qty,
                    approved_quantity=qty if auto_appr else None,
                    unit_cost_at_dispatch=cost_snap,
                    notes=item.get('notes', ''),
                )

        note_text = f"Transfer request {transfer_req.reference_number} created"
        if auto_appr:
            note_text += f" (Auto-approved via rule: {eval_res.get('rule_applied', 'Policy')})"

        log_transfer_event(
            business=business,
            parent_obj=transfer_req,
            from_status='',
            to_status=initial_status,
            event_type=event_type,
            user=user,
            notes=note_text,
            metadata={'estimated_value': float(eval_res['total_estimated_value'])},
        )
        return transfer_req

    @staticmethod
    @transaction.atomic
    def approve_transfer_request(transfer_req=None, approved_items_data=None, user=None, transfer_request=None, approved_items_map=None):
        """Approve transfer request by source branch manager or HQ admin with row-level locking."""
        transfer_req = transfer_req or transfer_request
        approved_items_data = approved_items_data if approved_items_data is not None else (approved_items_map or {})
        transfer_req = StockTransferRequest.objects.select_for_update().get(pk=transfer_req.pk)

        if transfer_req.status not in ('pending', 'pending_approval', 'approved', 'draft'):
            raise ValidationError(f"Cannot approve transfer request in status '{transfer_req.status}'.")

        old_status = transfer_req.status
        for item in transfer_req.items.all():
            if item.id in approved_items_data:
                appr_qty = Decimal(str(approved_items_data[item.id]))
                item.approved_quantity = appr_qty
                item.save(update_fields=['approved_quantity'])
            elif item.approved_quantity is None:
                item.approved_quantity = item.requested_quantity
                item.save(update_fields=['approved_quantity'])

        transfer_req.status = 'approved'
        transfer_req.approved_by = user
        transfer_req.approved_at = timezone.now()
        transfer_req.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        log_transfer_event(
            business=transfer_req.business,
            parent_obj=transfer_req,
            from_status=old_status,
            to_status='approved',
            event_type='approved',
            user=user,
            notes=f"Transfer request approved by {user.username if user else 'Authorizer'}.",
        )
        return transfer_req

    @staticmethod
    @transaction.atomic
    def reject_transfer_request(transfer_req, user, reason=''):
        """Reject a transfer request."""
        transfer_req = StockTransferRequest.objects.select_for_update().get(pk=transfer_req.pk)
        if transfer_req.status not in ('pending', 'pending_approval', 'approved', 'draft'):
            raise ValidationError(f"Cannot reject transfer request in status '{transfer_req.status}'.")

        old_status = transfer_req.status
        transfer_req.status = 'rejected'
        transfer_req.rejection_reason = reason
        transfer_req.save(update_fields=['status', 'rejection_reason', 'updated_at'])

        log_transfer_event(
            business=transfer_req.business,
            parent_obj=transfer_req,
            from_status=old_status,
            to_status='rejected',
            event_type='rejected',
            user=user,
            notes=f"Transfer request rejected: {reason}",
        )
        return transfer_req

    @staticmethod
    @transaction.atomic
    def dispatch(parent_obj=None, items_data=None, user=None, notes='', source_doc=None):
        """
        Dispatch stock for an approved Requisition or Transfer Request with deadlock-free sorted locking.
        Deducts from source branch with in_transit ledger recording.
        """
        parent_obj = parent_obj or source_doc
        items_data = items_data or []
        is_requisition = isinstance(parent_obj, StockRequisition)
        is_transfer = isinstance(parent_obj, StockTransferRequest)

        if not is_requisition and not is_transfer:
            raise ValidationError("Dispatch must be tied to a StockRequisition or StockTransferRequest.")

        # Lock parent row
        if is_requisition:
            parent_obj = StockRequisition.objects.select_for_update().get(pk=parent_obj.pk)
        else:
            parent_obj = StockTransferRequest.objects.select_for_update().get(pk=parent_obj.pk)

        # STRICT MODEL-LAYER GUARD
        if parent_obj.status != 'approved':
            raise ValidationError(
                f"Cannot dispatch: {parent_obj.__class__.__name__} '{parent_obj.reference_number}' "
                f"must be approved before dispatch (current status: '{parent_obj.status}')."
            )

        business = parent_obj.business
        if is_requisition:
            hq_branch = Branch.objects.filter(business=business, is_hq=True, is_active=True).first()
            if not hq_branch:
                hq_branch = Branch.objects.filter(business=business, is_active=True).first()
            source_branch = hq_branch
            dest_branch = parent_obj.requesting_branch
            dispatch_rec = Dispatch.objects.create(
                business=business,
                source_branch=source_branch,
                destination_branch=dest_branch,
                requisition=parent_obj,
                dispatched_by=user,
                notes=notes,
                status='in_transit',
            )
            movement_type = 'hq_dispatch_out'
        else:
            source_branch = parent_obj.source_branch
            dest_branch = parent_obj.destination_branch
            dispatch_rec = Dispatch.objects.create(
                business=business,
                source_branch=source_branch,
                destination_branch=dest_branch,
                transfer_request=parent_obj,
                dispatched_by=user,
                notes=notes,
                status='in_transit',
            )
            movement_type = 'in_transit_out'

        # Sort items deterministically by product_id to avoid DB deadlocks on concurrent transfers
        sorted_items = sorted(
            items_data,
            key=lambda x: int(x.get('product_id') or getattr(parent_obj.items.filter(pk=x.get('item_id')).first(), 'product_id', 0) or 0)
        )

        for item_data in sorted_items:
            line_item_id = item_data.get('item_id')
            qty_to_dispatch = Decimal(str(item_data.get('quantity', 0)))
            if qty_to_dispatch <= 0:
                continue

            if is_requisition:
                req_item = parent_obj.items.get(pk=line_item_id)
                product = req_item.product
                req_item.dispatched_quantity += qty_to_dispatch
                req_item.save(update_fields=['dispatched_quantity'])
            else:
                trf_item = parent_obj.items.get(pk=line_item_id)
                product = trf_item.product
                trf_item.dispatched_quantity += qty_to_dispatch

            # Lock and fetch source branch stock
            src_stock = BranchStockService.get_or_create(source_branch, product)
            if src_stock.quantity < qty_to_dispatch:
                raise ValidationError(
                    f"Insufficient stock for product '{product.name}' at branch '{source_branch.name}'. "
                    f"Available: {src_stock.quantity}, attempting to dispatch: {qty_to_dispatch}."
                )
            unit_cost = src_stock.average_cost

            if not is_requisition:
                trf_item.unit_cost_at_dispatch = unit_cost
                trf_item.save(update_fields=['dispatched_quantity', 'unit_cost_at_dispatch'])

            # Deduct with ledger movement
            src_stock.deduct(
                qty=qty_to_dispatch,
                movement_type=movement_type,
                reference_obj=dispatch_rec,
                user=user,
                note=f"Dispatched via {dispatch_rec.reference_number}",
            )

            DispatchItem.objects.create(
                dispatch=dispatch_rec,
                product=product,
                dispatched_quantity=qty_to_dispatch,
                unit_cost=unit_cost,
                received_quantity=Decimal('0.000'),
            )

        old_parent_status = parent_obj.status
        parent_obj.status = 'dispatched'
        parent_obj.save(update_fields=['status', 'updated_at'])

        log_transfer_event(
            business=business,
            parent_obj=parent_obj,
            from_status=old_parent_status,
            to_status='dispatched',
            event_type='dispatched',
            user=user,
            notes=f"Shipment {dispatch_rec.reference_number} dispatched from {source_branch.name} to {dest_branch.name}.",
        )
        return dispatch_rec

    @staticmethod
    @transaction.atomic
    def confirm_receipt(dispatch, received_items_data, user):
        """
        Confirm receipt at destination branch (full or partial with discrepancy tracking).
        received_items_data: dict of {dispatch_item_id: {'received_qty': ..., 'discrepancy_reason': ...}}
        """
        dispatch = Dispatch.objects.select_for_update().get(pk=dispatch.pk)
        if dispatch.status not in ('in_transit', 'partially_received', 'receiving'):
            raise ValidationError(f"Cannot confirm receipt for dispatch in status '{dispatch.status}'.")

        is_requisition = bool(dispatch.requisition)
        movement_type = 'branch_receipt_in' if is_requisition else 'transfer_in'
        dest_branch = dispatch.destination_branch
        has_discrepancy = False

        # Deterministic sorting on items
        d_items = list(dispatch.items.select_related('product').order_by('product_id'))

        for d_item in d_items:
            recv_info = received_items_data.get(d_item.id, {})
            if isinstance(recv_info, (int, float, str, Decimal)):
                recv_qty = Decimal(str(recv_info))
                disc_reason = ''
            else:
                recv_qty = Decimal(str(recv_info.get('received_qty', d_item.dispatched_quantity)))
                disc_reason = recv_info.get('discrepancy_reason', '')

            d_item.received_quantity = recv_qty
            if recv_qty < d_item.dispatched_quantity:
                d_item.discrepancy_quantity = d_item.dispatched_quantity - recv_qty
                d_item.discrepancy_reason = disc_reason
                has_discrepancy = True
            else:
                d_item.discrepancy_quantity = Decimal('0.000')

            d_item.save(update_fields=['received_quantity', 'discrepancy_quantity', 'discrepancy_reason'])

            # Update parent line item
            if is_requisition and dispatch.requisition:
                req_item = dispatch.requisition.items.filter(product=d_item.product).first()
                if req_item:
                    req_item.received_quantity += recv_qty
                    req_item.save(update_fields=['received_quantity'])
            elif dispatch.transfer_request:
                trf_item = dispatch.transfer_request.items.filter(product=d_item.product).first()
                if trf_item:
                    trf_item.received_quantity += recv_qty
                    trf_item.discrepancy_quantity = d_item.discrepancy_quantity
                    trf_item.discrepancy_reason = disc_reason
                    trf_item.save(update_fields=['received_quantity', 'discrepancy_quantity', 'discrepancy_reason'])

            # Receive stock into destination branch at shipped unit_cost
            if recv_qty > 0:
                dest_stock = BranchStockService.get_or_create(dest_branch, d_item.product)
                dest_stock.receive(
                    qty=recv_qty,
                    unit_cost=d_item.unit_cost,
                    movement_type=movement_type,
                    reference_obj=dispatch,
                    user=user,
                    note=f"Received via {dispatch.reference_number}",
                )

        dispatch.received_by = user
        dispatch.received_at = timezone.now()
        dispatch.status = 'partially_received' if has_discrepancy else 'received'
        dispatch.save(update_fields=['received_by', 'received_at', 'status'])

        # Update parent document status
        if dispatch.requisition:
            req = StockRequisition.objects.select_for_update().get(pk=dispatch.requisition_id)
            old_status = req.status
            new_status = 'partially_fulfilled' if has_discrepancy else 'fulfilled'
            req.status = new_status
            req.save(update_fields=['status', 'updated_at'])
            event_type = 'received_partial' if has_discrepancy else 'received_full'
            log_transfer_event(
                business=req.business,
                parent_obj=req,
                from_status=old_status,
                to_status=new_status,
                event_type=event_type,
                user=user,
                notes=f"Goods received at {dest_branch.name}. Discrepancy flagged: {has_discrepancy}.",
            )
        elif dispatch.transfer_request:
            trf = StockTransferRequest.objects.select_for_update().get(pk=dispatch.transfer_request_id)
            old_status = trf.status
            new_status = 'discrepancy_flagged' if has_discrepancy else 'completed'
            trf.status = new_status
            trf.save(update_fields=['status', 'updated_at'])
            event_type = 'received_partial' if has_discrepancy else 'received_full'
            log_transfer_event(
                business=trf.business,
                parent_obj=trf,
                from_status=old_status,
                to_status=new_status,
                event_type=event_type,
                user=user,
                notes=f"Receipt confirmed at {dest_branch.name}. Status: {new_status}.",
            )

        return dispatch

    @staticmethod
    @transaction.atomic
    def resolve_discrepancy(transfer_req, resolutions, user, notes='', resolution_notes=None):
        """
        Supervisor resolution of flagged transfer discrepancies.
        resolutions: dict of {item_id: {'resolution': 'writeoff_loss'|'returned_to_source'|'accepted_variance', 'notes': ...}}
        """
        if resolution_notes:
            notes = resolution_notes

        transfer_req = StockTransferRequest.objects.select_for_update().get(pk=transfer_req.pk)
        if transfer_req.status not in ('discrepancy_flagged', 'partially_received'):
            raise ValidationError(f"Cannot resolve discrepancies on transfer with status '{transfer_req.status}'.")

        old_status = transfer_req.status

        for item in transfer_req.items.select_related('product').all():
            res_data = resolutions.get(item.id) or resolutions.get(str(item.id))
            if not res_data:
                continue

            res_type = res_data.get('resolution') if isinstance(res_data, dict) else str(res_data)
            item_notes = res_data.get('notes', '') if isinstance(res_data, dict) else ''

            if res_type not in ('writeoff_loss', 'returned_to_source', 'accepted_variance'):
                continue

            item.discrepancy_resolution = res_type
            item.save(update_fields=['discrepancy_resolution'])

            disc_qty = item.discrepancy_quantity
            if disc_qty > 0:
                cost = item.unit_cost_at_dispatch or item.product.cost_price

                if res_type == 'writeoff_loss':
                    # Record loss/shrinkage write-off movement on the ledger
                    StockMovement.objects.create(
                        business=transfer_req.business,
                        branch=transfer_req.source_branch,
                        product=item.product,
                        quantity_delta=-disc_qty,
                        unit_cost=cost,
                        total_cost=(disc_qty * cost).quantize(Decimal('0.01')),
                        movement_type='transit_loss_writeoff',
                        content_type=None,
                        object_id=str(transfer_req.pk),
                        reference_number=transfer_req.reference_number,
                        balance_after=None,
                        performed_by=user,
                        note=f"Transit Loss Write-off: {disc_qty:g} units lost/damaged. {item_notes}".strip(),
                    )
                elif res_type == 'returned_to_source':
                    # Return missing units back to source branch inventory
                    src_stock = BranchStockService.get_or_create(transfer_req.source_branch, item.product)
                    src_stock.receive(
                        qty=disc_qty,
                        unit_cost=cost,
                        movement_type='transit_return_in',
                        reference_obj=transfer_req,
                        user=user,
                        note=f"Transit Return In: {disc_qty:g} units returned to source. {item_notes}".strip(),
                    )

        transfer_req.status = 'resolved'
        transfer_req.discrepancy_resolved_by = user
        transfer_req.discrepancy_resolved_at = timezone.now()
        transfer_req.discrepancy_resolution_notes = notes
        transfer_req.save(update_fields=[
            'status', 'discrepancy_resolved_by', 'discrepancy_resolved_at',
            'discrepancy_resolution_notes', 'updated_at'
        ])

        log_transfer_event(
            business=transfer_req.business,
            parent_obj=transfer_req,
            from_status=old_status,
            to_status='resolved',
            event_type='discrepancy_resolved',
            user=user,
            notes=f"Discrepancy resolved by supervisor {user.username if user else 'Supervisor'}: {notes}",
        )
        return transfer_req


# ---------------------------------------------------------------------------
# StockTransferService (Direct Stock Movement Engine)
# ---------------------------------------------------------------------------

class StockTransferService:

    @staticmethod
    def create(source, destination, product, qty, note, initiated_by):
        """Direct transfer helper."""
        if source.pk == destination.pk:
            raise ValueError('Source and destination branches must be different.')
        if source.business_id != destination.business_id:
            raise ValueError('Branches must belong to the same business.')
        if not product.is_active:
            raise ValueError('Cannot transfer an inactive product.')

        qty = Decimal(str(qty))
        if qty <= 0:
            raise ValueError('Transfer quantity must be greater than zero.')

        transfer = StockTransfer.objects.create(
            business=source.business,
            source_branch=source,
            destination_branch=destination,
            product=product,
            quantity=qty,
            note=note,
            initiated_by=initiated_by,
            status='pending',
        )
        return transfer

    @staticmethod
    @transaction.atomic
    def confirm(transfer):
        """Atomically move stock from source to destination via BranchStock with row locking."""
        if transfer.status not in ('pending', 'in_transit'):
            raise InvalidTransferStateError(
                f"Cannot confirm a transfer with status '{transfer.status}'."
            )
        transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
        source_stock = BranchStockService.get_or_create(transfer.source_branch, transfer.product)
        unit_cost = source_stock.average_cost

        source_stock.deduct(
            qty=transfer.quantity, movement_type='transfer_out',
            reference_obj=transfer, user=transfer.initiated_by,
            note=f"Direct Transfer {transfer.reference}"
        )
        dest_stock = BranchStockService.get_or_create(transfer.destination_branch, transfer.product)
        dest_stock.receive(
            qty=transfer.quantity, unit_cost=unit_cost,
            movement_type='transfer_in', reference_obj=transfer,
            user=transfer.initiated_by, note=f"Direct Transfer {transfer.reference}"
        )

        transfer.status = 'completed'
        transfer.completed_at = timezone.now()
        transfer.save(update_fields=['status', 'completed_at'])
        return transfer

    @staticmethod
    @transaction.atomic
    def cancel(transfer):
        if transfer.status in ('completed', 'cancelled'):
            raise InvalidTransferStateError(
                f"Cannot cancel a transfer with status '{transfer.status}'."
            )
        transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)
        transfer.status = 'cancelled'
        transfer.cancelled_at = timezone.now()
        transfer.save(update_fields=['status', 'cancelled_at'])
        return transfer


# ---------------------------------------------------------------------------
# ConsolidatedReportService
# ---------------------------------------------------------------------------

class ConsolidatedReportService:

    @staticmethod
    def sales_summary(business, date_from, date_to, branch_ids=None):
        """
        Aggregated sales per branch for the given date range.
        Returns a list of dicts: {branch_id, branch_name, revenue, tx_count, gross_profit}
        """
        qs = Sale.objects.filter(
            business=business,
            date__date__gte=date_from,
            date__date__lte=date_to,
        )
        if branch_ids:
            qs = qs.filter(branch_id__in=branch_ids)

        rows = qs.values('branch_id', 'branch__name').annotate(
            revenue=Sum('total'),
            tx_count=Count('id'),
        ).order_by('branch__name')

        # Gross profit from SaleItems
        profit_qs = SaleItem.objects.filter(
            sale__business=business,
            sale__date__date__gte=date_from,
            sale__date__date__lte=date_to,
        )
        if branch_ids:
            profit_qs = profit_qs.filter(sale__branch_id__in=branch_ids)

        profit_by_branch = {}
        for row in profit_qs.values('sale__branch_id').annotate(
            profit=Sum(
                ExpressionWrapper(
                    F('quantity') * (F('unit_price') - F('product__cost_price')),
                    output_field=DecimalField(),
                )
            )
        ):
            profit_by_branch[row['sale__branch_id']] = float(row['profit'] or 0)

        result = []
        total_revenue = Decimal('0')
        total_profit = Decimal('0')
        for row in rows:
            rev = row['revenue'] or Decimal('0')
            profit = Decimal(str(profit_by_branch.get(row['branch_id'], 0)))
            total_revenue += rev
            total_profit += profit
            result.append({
                'branch_id': row['branch_id'],
                'branch_name': row['branch__name'] or 'HQ',
                'revenue': rev,
                'tx_count': row['tx_count'],
                'gross_profit': profit,
            })

        return {
            'rows': result,
            'total_revenue': total_revenue,
            'total_profit': total_profit,
            'total_transactions': sum(r['tx_count'] for r in result),
        }

    @staticmethod
    def stock_valuation(business, branch_ids=None):
        """Stock value per branch: {branch_name, qty, cost_value, sell_value}"""
        qs = BranchStock.objects.filter(branch__business=business).select_related(
            'branch', 'product'
        )
        if branch_ids:
            qs = qs.filter(branch_id__in=branch_ids)

        rows = qs.values('branch_id', 'branch__name').annotate(
            cost_value=Sum(
                ExpressionWrapper(
                    F('quantity') * F('product__cost_price'),
                    output_field=DecimalField(),
                )
            ),
            sell_value=Sum(
                ExpressionWrapper(
                    F('quantity') * F('product__unit_price'),
                    output_field=DecimalField(),
                )
            ),
        ).order_by('branch__name')

        return [
            {
                'branch_id': r['branch_id'],
                'branch_name': r['branch__name'] or 'HQ',
                'cost_value': r['cost_value'] or Decimal('0'),
                'sell_value': r['sell_value'] or Decimal('0'),
            }
            for r in rows
        ]

    @staticmethod
    def top_products(business, date_from, date_to, branch_ids=None, limit=20):
        """Top products by units sold across branches."""
        qs = SaleItem.objects.filter(
            sale__business=business,
            sale__date__date__gte=date_from,
            sale__date__date__lte=date_to,
        )
        if branch_ids:
            qs = qs.filter(sale__branch_id__in=branch_ids)

        rows = qs.values(
            'product__id', 'product__name', 'product__category__name'
        ).annotate(
            units_sold=Sum('quantity'),
            revenue=Sum(
                ExpressionWrapper(
                    F('quantity') * F('unit_price'), output_field=DecimalField()
                )
            ),
        ).order_by('-units_sold')[:limit]

        return [
            {
                'product_id': r['product__id'],
                'name': r['product__name'],
                'category': r['product__category__name'] or 'Uncategorized',
                'units_sold': float(r['units_sold'] or 0),
                'revenue': float(r['revenue'] or 0),
            }
            for r in rows
        ]
