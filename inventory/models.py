"""
Inventory & Append-Only Stock Ledger Models
Provides multi-warehouse management, perpetual weighted-average and FIFO valuation,
and immutable append-only stock movement ledgers.
"""
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from core.models.base import CompanyScopedModel, AuditedModel, SoftDeleteModel, TimeStampedModel


class Warehouse(CompanyScopedModel, AuditedModel, SoftDeleteModel, TimeStampedModel):
    """
    Physical or logical storage location / warehouse for stocking goods.
    """
    TYPE_MAIN = 'main'
    TYPE_STORE = 'store'
    TYPE_TRANSIT = 'transit'
    TYPE_QUARANTINE = 'quarantine'
    TYPE_SCRAP = 'scrap'

    TYPE_CHOICES = [
        (TYPE_MAIN, 'Main Warehouse / Bulk Storage'),
        (TYPE_STORE, 'Retail Store / Front Shelf'),
        (TYPE_TRANSIT, 'In-Transit Location'),
        (TYPE_QUARANTINE, 'Quarantine / Damaged Holding'),
        (TYPE_SCRAP, 'Scrap / Write-off'),
    ]

    branch = models.ForeignKey(
        'core.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='warehouses',
        help_text="Branch this warehouse is physically located in",
    )
    code = models.CharField(max_length=50, db_index=True, help_text="Unique Warehouse Code e.g. WH-HQ, WH-CBD")
    name = models.CharField(max_length=150, db_index=True)
    warehouse_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MAIN)
    is_primary = models.BooleanField(default=False, help_text="Primary default warehouse for branch/company")
    is_active = models.BooleanField(default=True, db_index=True)
    address = models.TextField(blank=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses',
    )

    class Meta:
        verbose_name = 'Warehouse'
        verbose_name_plural = 'Warehouses'
        ordering = ['-is_primary', 'name']
        unique_together = [['company', 'code']]

    def __str__(self):
        branch_str = f" ({self.branch.code})" if self.branch else ""
        return f"{self.name} [{self.code}]{branch_str}"


class StockItemSettings(CompanyScopedModel, TimeStampedModel):
    """
    Product-specific inventory management settings and valuation policies.
    """
    VALUATION_WEIGHTED_AVERAGE = 'weighted_average'
    VALUATION_FIFO = 'fifo'
    VALUATION_STANDARD = 'standard'

    VALUATION_CHOICES = [
        (VALUATION_WEIGHTED_AVERAGE, 'Moving Weighted Average Cost'),
        (VALUATION_FIFO, 'First-In, First-Out (FIFO)'),
        (VALUATION_STANDARD, 'Standard Costing'),
    ]

    product = models.ForeignKey(
        'pos.Product',
        on_delete=models.CASCADE,
        related_name='inventory_settings',
    )
    valuation_method = models.CharField(
        max_length=20,
        choices=VALUATION_CHOICES,
        default=VALUATION_WEIGHTED_AVERAGE,
    )
    allow_negative_stock = models.BooleanField(
        default=False,
        help_text="If False, sales/dispatches that drive balance below 0 will be rejected",
    )
    reorder_level = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Stock level triggering reorder warnings",
    )
    reorder_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Standard batch purchase order quantity",
    )
    default_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_product_settings',
    )

    class Meta:
        verbose_name = 'Stock Item Setting'
        verbose_name_plural = 'Stock Item Settings'
        unique_together = [['company', 'product']]

    def __str__(self):
        return f"Inventory Settings: {self.product.name} ({self.get_valuation_method_display()})"


class StockLedgerEntry(CompanyScopedModel):
    """
    IMMUTABLE APPEND-ONLY STOCK LEDGER.
    Every inventory movement (Purchase, Sale, Transfer, Adjustment, Return) appends a new row.
    Entries are NEVER updated or deleted. Corrections are posted via reversing entries.
    """
    VOUCHER_PURCHASE_RECEIPT = 'purchase_receipt'
    VOUCHER_PURCHASE_RETURN = 'purchase_return'
    VOUCHER_SALES_DELIVERY = 'sales_delivery'
    VOUCHER_SALES_RETURN = 'sales_return'
    VOUCHER_POS_SALE = 'pos_sale'
    VOUCHER_TRANSFER_OUT = 'stock_transfer_out'
    VOUCHER_TRANSFER_IN = 'stock_transfer_in'
    VOUCHER_ADJUSTMENT = 'stock_adjustment'
    VOUCHER_OPENING_BALANCE = 'opening_balance'
    VOUCHER_REVERSAL = 'reversal'

    VOUCHER_TYPE_CHOICES = [
        (VOUCHER_PURCHASE_RECEIPT, 'Goods Received Note (GRN)'),
        (VOUCHER_PURCHASE_RETURN, 'Goods Returned Note (Purchase Return)'),
        (VOUCHER_SALES_DELIVERY, 'Delivery Note / Sales Dispatch'),
        (VOUCHER_SALES_RETURN, 'Customer Return / Credit Note'),
        (VOUCHER_POS_SALE, 'POS Cashier Sale'),
        (VOUCHER_TRANSFER_OUT, 'Inter-Warehouse Transfer Out'),
        (VOUCHER_TRANSFER_IN, 'Inter-Warehouse Transfer In'),
        (VOUCHER_ADJUSTMENT, 'Physical Count Adjustment / Write-Off'),
        (VOUCHER_OPENING_BALANCE, 'Opening Stock Balance'),
        (VOUCHER_REVERSAL, 'Reversal Entry'),
    ]

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='stock_ledger_entries',
        db_index=True,
    )
    product = models.ForeignKey(
        'pos.Product',
        on_delete=models.PROTECT,
        related_name='stock_ledger_entries',
        db_index=True,
    )
    posting_date = models.DateField(default=timezone.now, db_index=True)
    posting_time = models.DateTimeField(default=timezone.now, db_index=True)
    
    voucher_type = models.CharField(max_length=30, choices=VOUCHER_TYPE_CHOICES, db_index=True)
    voucher_no = models.CharField(max_length=100, db_index=True, help_text="Document reference (e.g. GRN-0001, INV-0001)")
    voucher_line_id = models.CharField(max_length=50, blank=True)
    
    # Movement Quantities (+ for incoming, - for outgoing)
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        help_text="Net stock quantity delta. Positive for incoming, negative for outgoing.",
    )
    unit_cost = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal('0.0000'),
        validators=[MinValueValidator(Decimal('0.0000'))],
        help_text="Cost per unit at the time of movement",
    )
    total_cost = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Net cost value delta (quantity * unit_cost)",
    )
    
    # Running Stock & Valuation Snapshot after this entry
    valuation_rate = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Running perpetual weighted average cost after this entry",
    )
    balance_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal('0.0000'),
        help_text="Running on-hand stock balance quantity after this entry",
    )
    balance_value = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Running inventory valuation total value after this entry",
    )

    # Batch / Serial / Expiry Tracking
    batch_number = models.CharField(max_length=100, blank=True, db_index=True)
    serial_number = models.CharField(max_length=100, blank=True, db_index=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)

    # Reversal Tracking
    is_reversal = models.BooleanField(default=False, db_index=True)
    reversed_entry = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reversals',
    )
    
    narration = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_ledger_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Stock Ledger Entry'
        verbose_name_plural = 'Stock Ledger Entries'
        ordering = ['posting_time', 'id']
        indexes = [
            models.Index(fields=['company', 'warehouse', 'product', 'posting_time']),
            models.Index(fields=['company', 'voucher_type', 'voucher_no']),
            models.Index(fields=['company', 'product', 'posting_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(quantity=0),
                name='inventory_stock_ledger_quantity_non_zero',
            ),
            models.CheckConstraint(
                check=models.Q(unit_cost__gte=0),
                name='inventory_stock_ledger_unit_cost_non_negative',
            ),
        ]

    def __str__(self):
        sign = "+" if self.quantity > 0 else ""
        return f"[{self.posting_date}] {self.product.name} @ {self.warehouse.code}: {sign}{self.quantity} ({self.voucher_no})"


class ValuationLayer(CompanyScopedModel, TimeStampedModel):
    """
    FIFO Inventory Valuation Layer.
    Maintains open stock purchase batches and remaining quantities for FIFO cost exhaustion.
    """
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='valuation_layers')
    product = models.ForeignKey('pos.Product', on_delete=models.CASCADE, related_name='valuation_layers')
    stock_ledger_entry = models.ForeignKey(
        StockLedgerEntry,
        on_delete=models.CASCADE,
        related_name='valuation_layers',
    )
    batch_number = models.CharField(max_length=100, blank=True)
    original_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    remaining_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0000'))],
    )
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    received_date = models.DateField(default=timezone.now)
    is_exhausted = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name = 'Valuation Layer'
        verbose_name_plural = 'Valuation Layers'
        ordering = ['received_date', 'created_at']
        indexes = [
            models.Index(fields=['company', 'warehouse', 'product', 'is_exhausted', 'received_date']),
        ]

    def __str__(self):
        return f"{self.product.name} @ {self.warehouse.code} [Layer: {self.remaining_quantity}/{self.original_quantity} @ KES {self.unit_cost}]"


class StockAdjustmentDocument(CompanyScopedModel, AuditedModel, SoftDeleteModel, TimeStampedModel):
    """
    Document for stock count reconciliations, shrinkage write-offs, and damage adjustments.
    """
    STATUS_DRAFT = 'draft'
    STATUS_APPROVED = 'approved'
    STATUS_POSTED = 'posted'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_POSTED, 'Posted to Ledger'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    REASON_PHYSICAL_COUNT = 'physical_count'
    REASON_DAMAGE = 'damage'
    REASON_EXPIRY = 'expiry'
    REASON_THEFT = 'theft_loss'
    REASON_CORRECTION = 'correction'

    REASON_CHOICES = [
        (REASON_PHYSICAL_COUNT, 'Physical Stock Count Reconciliation'),
        (REASON_DAMAGE, 'Damaged / Broken Goods'),
        (REASON_EXPIRY, 'Expired Stock Disposal'),
        (REASON_THEFT, 'Theft / Shrinkage Loss'),
        (REASON_CORRECTION, 'Data Correction'),
    ]

    adjustment_number = models.CharField(max_length=50, unique=True, db_index=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='stock_adjustments')
    adjustment_date = models.DateField(default=timezone.now, db_index=True)
    reason = models.CharField(max_length=30, choices=REASON_CHOICES, default=REASON_PHYSICAL_COUNT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    notes = models.TextField(blank=True)
    total_variance_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Stock Adjustment Document'
        verbose_name_plural = 'Stock Adjustment Documents'
        ordering = ['-adjustment_date', '-created_at']

    def __str__(self):
        return f"{self.adjustment_number} ({self.warehouse.code}) [{self.get_status_display()}]"


class StockAdjustmentLine(models.Model):
    """
    Line item for a stock adjustment document.
    """
    document = models.ForeignKey(StockAdjustmentDocument, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey('pos.Product', on_delete=models.PROTECT)
    system_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    variance_quantity = models.DecimalField(max_digits=14, decimal_places=4, help_text="counted_quantity - system_quantity")
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    total_variance_cost = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    batch_number = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'Stock Adjustment Line'
        verbose_name_plural = 'Stock Adjustment Lines'

    def __str__(self):
        return f"{self.product.name}: Counted {self.counted_quantity} (Var: {self.variance_quantity:+f})"
