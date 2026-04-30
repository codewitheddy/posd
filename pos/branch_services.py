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
    InvalidTransferStateError,
)


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------

def is_owner_or_admin(user, business):
    """Return True if user is owner/admin of the business or a superuser."""
    if user.is_superuser:
        return True
    return BusinessMembership.objects.filter(
        user=user, business=business, is_active=True,
        role__in=['owner', 'admin'],
    ).exists()


def get_user_branches(user, business):
    """Return branches the user can access (all for owner/admin, assigned for others)."""
    if is_owner_or_admin(user, business):
        return Branch.objects.filter(business=business, is_active=True)
    return Branch.objects.filter(
        business=business,
        is_active=True,
        memberships__user=user,
        memberships__is_active=True,
    ).distinct()


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
# BranchStockService
# ---------------------------------------------------------------------------

class BranchStockService:

    @staticmethod
    def get_or_create(branch, product):
        """Get or create a BranchStock record (quantity=0 for new)."""
        stock, _ = BranchStock.objects.get_or_create(
            branch=branch, product=product,
            defaults={'quantity': Decimal('0')},
        )
        return stock

    @staticmethod
    @transaction.atomic
    def deduct(branch, product, qty):
        """
        Deduct qty from branch stock atomically.
        Raises InsufficientStockError if qty > on_hand.
        Raises BranchInactiveError if branch is inactive.
        """
        if not branch.is_active:
            raise BranchInactiveError(f"Branch '{branch.name}' is inactive.")

        stock = BranchStockService.get_or_create(branch, product)
        # Re-fetch with select_for_update to prevent race conditions
        stock = BranchStock.objects.select_for_update().get(pk=stock.pk)

        if stock.quantity < qty:
            raise InsufficientStockError(
                branch=branch, product=product,
                available=stock.quantity, requested=qty,
            )
        stock.quantity -= Decimal(str(qty))
        stock.save(update_fields=['quantity', 'updated_at'])
        return stock

    @staticmethod
    @transaction.atomic
    def add(branch, product, qty):
        """Add qty to branch stock atomically."""
        stock = BranchStockService.get_or_create(branch, product)
        stock = BranchStock.objects.select_for_update().get(pk=stock.pk)
        stock.quantity += Decimal(str(qty))
        stock.save(update_fields=['quantity', 'updated_at'])
        return stock

    @staticmethod
    def adjust(branch, product, qty_change, reason, adjustment_type):
        """Create a StockAdjustment and update BranchStock."""
        from .models import StockAdjustment
        stock = BranchStockService.get_or_create(branch, product)
        prev = stock.quantity
        with transaction.atomic():
            stock = BranchStock.objects.select_for_update().get(pk=stock.pk)
            stock.quantity += Decimal(str(qty_change))
            stock.save(update_fields=['quantity', 'updated_at'])
            StockAdjustment.objects.create(
                business=branch.business,
                branch=branch,
                product=product,
                adjustment_type=adjustment_type,
                quantity_change=int(qty_change),
                previous_quantity=int(prev),
                new_quantity=int(stock.quantity),
                reason=reason,
            )
        return stock

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
# StockTransferService
# ---------------------------------------------------------------------------

class StockTransferService:

    @staticmethod
    def create(source, destination, product, qty, note, initiated_by):
        """
        Validate and create a StockTransfer in 'pending' status.
        Does NOT move stock yet — call confirm() to do that.
        """
        if source.pk == destination.pk:
            raise ValueError('Source and destination branches must be different.')
        if source.business_id != destination.business_id:
            raise ValueError('Branches must belong to the same business.')
        if not product.is_active:
            raise ValueError('Cannot transfer an inactive product.')

        qty = Decimal(str(qty))
        if qty <= 0:
            raise ValueError('Transfer quantity must be greater than zero.')

        # Validate source has enough stock
        stock = BranchStockService.get_or_create(source, product)
        if stock.quantity < qty:
            raise InsufficientStockError(
                branch=source, product=product,
                available=stock.quantity, requested=qty,
            )

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
        """
        Atomically move stock from source to destination.
        Sets status='completed'.
        """
        if transfer.status not in ('pending', 'in_transit'):
            raise InvalidTransferStateError(
                f"Cannot confirm a transfer with status '{transfer.status}'."
            )
        transfer = StockTransfer.objects.select_for_update().get(pk=transfer.pk)

        BranchStockService.deduct(transfer.source_branch, transfer.product, transfer.quantity)
        BranchStockService.add(transfer.destination_branch, transfer.product, transfer.quantity)

        transfer.status = 'completed'
        transfer.completed_at = timezone.now()
        transfer.save(update_fields=['status', 'completed_at'])
        return transfer

    @staticmethod
    @transaction.atomic
    def cancel(transfer):
        """
        Cancel a pending/in_transit transfer.
        Raises InvalidTransferStateError if already completed or cancelled.
        """
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
