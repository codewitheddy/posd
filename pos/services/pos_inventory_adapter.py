"""
POS to ERP Inventory Ledger Strangler Adapter
Seamlessly synchronizes live POS transactions (Sales, Returns, Purchase Receipts, Stock Adjustments)
with the append-only Inventory Stock Ledger without disrupting active POS registers.
"""
import logging
from decimal import Decimal
from typing import Optional, List
from django.db import transaction
from django.utils import timezone
from core.models.organization import Company, Branch
from inventory.models import Warehouse, StockLedgerEntry, StockItemSettings
from inventory.services.stock_ledger_service import post_stock_movement

logger = logging.getLogger(__name__)


def get_or_create_default_warehouse(company: Company, branch: Optional[Branch] = None) -> Warehouse:
    """
    Retrieve or provision the primary warehouse for the given Company/Branch.
    """
    qs = Warehouse.objects.filter(company=company, is_active=True)
    if branch:
        wh = qs.filter(branch=branch, is_primary=True).first() or qs.filter(branch=branch).first()
        if wh:
            return wh

    primary_wh = qs.filter(is_primary=True).first() or qs.first()
    if primary_wh:
        return primary_wh

    # Provision default warehouse if none exists
    branch_code = branch.code if branch else "HQ"
    code = f"WH-{branch_code}"
    # Ensure unique code
    counter = 1
    orig_code = code
    while Warehouse.objects.filter(company=company, code=code).exists():
        code = f"{orig_code}-{counter}"
        counter += 1

    return Warehouse.objects.create(
        company=company,
        branch=branch,
        code=code,
        name=f"Main Store ({branch.name if branch else 'Primary'})",
        warehouse_type=Warehouse.TYPE_MAIN,
        is_primary=True,
    )


def _get_core_company_and_branch(pos_business, pos_branch=None):
    try:
        from pos.models import _get_or_create_core_company_and_branch
        return _get_or_create_core_company_and_branch(pos_business, pos_branch)
    except Exception as e:
        logger.warning("Could not resolve core Company/Branch: %s", e)
        return None, None


class POSInventoryAdapter:
    """
    Strangler adapter translating POS events into immutable Stock Ledger entries.
    """

    @classmethod
    def sync_sale(cls, sale, user=None) -> List[StockLedgerEntry]:
        """
        Record outbound stock movements for all items in a completed POS Sale.
        """
        entries = []
        try:
            business = getattr(sale, 'business', None)
            branch = getattr(sale, 'branch', None)
            company, core_branch = _get_core_company_and_branch(business, branch)
            if not company:
                return entries

            warehouse = get_or_create_default_warehouse(company, core_branch)
            cashier = user or getattr(sale, 'cashier', None)

            # Prevent duplicate postings for same sale
            existing = StockLedgerEntry.objects.filter(
                company=company,
                voucher_type=StockLedgerEntry.VOUCHER_POS_SALE,
                voucher_no=sale.invoice_number,
            ).exists()
            if existing:
                return entries

            for item in sale.items.select_related('product'):
                qty = Decimal(str(item.quantity))
                if qty <= 0:
                    continue

                entry = post_stock_movement(
                    company=company,
                    warehouse=warehouse,
                    product=item.product,
                    voucher_type=StockLedgerEntry.VOUCHER_POS_SALE,
                    voucher_no=sale.invoice_number,
                    voucher_line_id=str(item.id),
                    quantity=-qty,
                    narration=f"POS Sale #{sale.invoice_number}",
                    created_by=cashier,
                )
                entries.append(entry)
        except Exception as e:
            logger.error("POS Inventory Adapter failed to sync sale %s: %s", getattr(sale, 'invoice_number', ''), e)
        return entries

    @classmethod
    def sync_sale_return(cls, sale_return, user=None) -> List[StockLedgerEntry]:
        """
        Record inbound stock replenishment for items returned in a POS Sale Return.
        """
        entries = []
        try:
            sale = getattr(sale_return, 'original_sale', None)
            business = getattr(sale_return, 'business', None) or (getattr(sale, 'business', None) if sale else None)
            branch = getattr(sale, 'branch', None) if sale else None
            company, core_branch = _get_core_company_and_branch(business, branch)
            if not company:
                return entries

            warehouse = get_or_create_default_warehouse(company, core_branch)

            # Prevent duplicate postings
            existing = StockLedgerEntry.objects.filter(
                company=company,
                voucher_type=StockLedgerEntry.VOUCHER_SALES_RETURN,
                voucher_no=sale_return.return_number,
            ).exists()
            if existing:
                return entries

            items_qs = getattr(sale_return, 'items', None)
            if items_qs:
                for r_item in items_qs.select_related('product'):
                    qty = Decimal(str(r_item.quantity))
                    if qty <= 0:
                        continue
                    entry = post_stock_movement(
                        company=company,
                        warehouse=warehouse,
                        product=r_item.product,
                        voucher_type=StockLedgerEntry.VOUCHER_SALES_RETURN,
                        voucher_no=sale_return.return_number,
                        voucher_line_id=str(r_item.id),
                        quantity=qty,
                        unit_cost=Decimal(str(getattr(r_item.product, 'cost_price', '0.00'))),
                        narration=f"POS Return #{sale_return.return_number} (Ref: {getattr(sale, 'invoice_number', '')})",
                        created_by=user,
                    )
                    entries.append(entry)
        except Exception as e:
            logger.error("POS Inventory Adapter failed to sync return %s: %s", getattr(sale_return, 'return_number', ''), e)
        return entries

    @classmethod
    def sync_purchase_receipt(cls, purchase, user=None) -> List[StockLedgerEntry]:
        """
        Record inbound stock receipts when a Purchase order is marked received.
        """
        entries = []
        try:
            business = getattr(purchase, 'business', None)
            branch = getattr(purchase, 'branch', None)
            company, core_branch = _get_core_company_and_branch(business, branch)
            if not company:
                return entries

            warehouse = get_or_create_default_warehouse(company, core_branch)

            # Prevent duplicate postings
            existing = StockLedgerEntry.objects.filter(
                company=company,
                voucher_type=StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT,
                voucher_no=purchase.purchase_number,
            ).exists()
            if existing:
                return entries

            for p_item in purchase.items.select_related('product'):
                qty = Decimal(str(p_item.quantity_received if hasattr(p_item, 'quantity_received') and p_item.quantity_received else p_item.quantity))
                if qty <= 0:
                    continue
                unit_cost = Decimal(str(p_item.unit_cost if hasattr(p_item, 'unit_cost') else getattr(p_item.product, 'cost_price', '0.00')))
                entry = post_stock_movement(
                    company=company,
                    warehouse=warehouse,
                    product=p_item.product,
                    voucher_type=StockLedgerEntry.VOUCHER_PURCHASE_RECEIPT,
                    voucher_no=purchase.purchase_number,
                    voucher_line_id=str(p_item.id),
                    quantity=qty,
                    unit_cost=unit_cost,
                    narration=f"Purchase Receipt #{purchase.purchase_number}",
                    created_by=user,
                )
                entries.append(entry)
        except Exception as e:
            logger.error("POS Inventory Adapter failed to sync purchase %s: %s", getattr(purchase, 'purchase_number', ''), e)
        return entries
