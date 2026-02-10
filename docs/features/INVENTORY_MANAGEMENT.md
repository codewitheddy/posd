# Inventory Management Feature

## Overview

The POS system now includes comprehensive inventory management to track stock levels, prevent overselling, and manage stock adjustments. The system automatically deducts stock when sales are made and provides alerts for low or out-of-stock items.

## Features

### 1. Stock Tracking
- **Stock Quantity**: Track current stock for each product
- **Low Stock Threshold**: Set custom alert levels per product
- **Stock Status**: Visual indicators (In Stock, Low Stock, Out of Stock)
- **Automatic Deduction**: Stock automatically reduced on sales
- **Stock History**: Complete audit trail of all stock changes

### 2. Stock Adjustments
- **Restock**: Add new inventory
- **Damage/Loss**: Remove damaged or lost items
- **Customer Returns**: Add returned items back to stock
- **Stock Correction**: Fix inventory discrepancies
- **Reason Tracking**: Add notes for each adjustment

### 3. Stock Alerts
- **Low Stock Warnings**: Dashboard alerts for products below threshold
- **Out of Stock Alerts**: Immediate notification for zero stock
- **POS Warnings**: Visual indicators on POS screen
- **Stock Validation**: Prevents selling more than available

### 4. Stock Reports
- **Stock List**: View all products with current stock levels
- **Stock History**: Detailed adjustment history per product
- **Low Stock Report**: Dedicated page for stock alerts
- **Filter Options**: Filter by stock status

## Usage Guide

### Adding Products with Stock

#### When Creating New Products
1. Go to **Products** → **Add Product**
2. Fill in product details
3. Enter **Stock Quantity** (initial stock)
4. Set **Low Stock Alert Threshold** (default: 10)
5. Save product

The system creates an initial stock adjustment record automatically.

#### Stock Fields
- **Stock Quantity**: Current number of units in stock
- **Low Stock Threshold**: Alert when stock reaches this level
  - Default: 10 units
  - Customize per product based on sales velocity

### Managing Stock

#### View Stock Levels
1. Go to **Stock** from main menu
2. View all products with current stock
3. Filter by status:
   - All Products
   - Low Stock Only
   - Out of Stock Only

#### Adjust Stock
1. Go to **Stock** → Click **Adjust** on product
2. Select adjustment type:
   - **Restock**: Adding new inventory
   - **Damage/Loss**: Removing damaged items
   - **Customer Return**: Adding returned items
   - **Stock Correction**: Fixing errors
3. Enter quantity change
4. Add reason/notes (optional)
5. Click **Adjust Stock**

#### View Stock History
1. Go to **Stock** → Click **History** on product
2. See complete adjustment history:
   - Date and time
   - Adjustment type
   - Quantity change
   - Previous and new quantities
   - Reason/notes

### Stock Alerts

#### Dashboard Alerts
- Dashboard shows count of low/out of stock products
- Click "View Stock Alerts" to see details

#### Low Stock Alert Page
1. Go to **Stock** → **Stock Alerts**
2. View two sections:
   - **Out of Stock**: Products with zero stock
   - **Low Stock**: Products at or below threshold
3. Click **Restock** to adjust stock immediately

#### POS Screen Indicators
- Products show stock status badges:
  - 🟢 **In Stock**: Green badge with quantity
  - 🟡 **Low Stock**: Yellow badge with quantity
  - 🔴 **Out of Stock**: Red badge, cannot add to cart

### Sales and Stock

#### Automatic Stock Deduction
When a sale is completed:
1. System checks stock availability for all items
2. If insufficient stock, sale is rejected with error message
3. If stock is sufficient:
   - Stock is deducted for each item
   - Stock adjustment record is created
   - Sale proceeds normally

#### Stock Validation
- Cannot add more items to cart than available stock
- POS screen shows real-time stock levels
- Barcode scanner checks stock before adding
- Error messages if stock insufficient

## Technical Details

### Database Schema

#### Product Model (Updated)
```python
class Product(models.Model):
    name = models.CharField(max_length=200)
    product_code = models.CharField(max_length=50, unique=True, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold
    
    def is_out_of_stock(self):
        return self.stock_quantity <= 0
    
    def has_sufficient_stock(self, quantity):
        return self.stock_quantity >= quantity
```

#### StockAdjustment Model (New)
```python
class StockAdjustment(models.Model):
    ADJUSTMENT_TYPES = [
        ('restock', 'Restock'),
        ('damage', 'Damage/Loss'),
        ('return', 'Customer Return'),
        ('correction', 'Stock Correction'),
        ('sale', 'Sale'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)
    quantity_change = models.IntegerField()  # Positive or negative
    previous_quantity = models.IntegerField()
    new_quantity = models.IntegerField()
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### API Updates

#### Product Search API (Updated)
```
GET /api/product/search/?code=BEV001
```

**Response:**
```json
{
    "success": true,
    "product": {
        "id": 1,
        "name": "Coca Cola 500ml",
        "product_code": "BEV001",
        "price": 80.0,
        "category": "Beverages",
        "stock_quantity": 50,
        "in_stock": true
    }
}
```

### New Views

1. **stock_list**: View all products with stock information
2. **stock_adjust**: Adjust stock for a product
3. **stock_history**: View adjustment history
4. **low_stock_alert**: View low/out of stock products

### URL Routes

```python
# Stock Management
path('stock/', views.stock_list, name='stock_list'),
path('stock/<int:pk>/adjust/', views.stock_adjust, name='stock_adjust'),
path('stock/<int:pk>/history/', views.stock_history, name='stock_history'),
path('stock/alerts/', views.low_stock_alert, name='low_stock_alert'),
```

## Sample Data

All 20 sample products now include stock quantities:

| Product | Code | Stock | Threshold |
|---------|------|-------|-----------|
| Coca Cola 500ml | BEV001 | 50 | 10 |
| Fanta Orange 500ml | BEV002 | 45 | 10 |
| Sprite 500ml | BEV003 | 40 | 10 |
| Bottled Water 500ml | BEV004 | 100 | 10 |
| Milk 1L | BEV005 | 30 | 10 |
| Bread | GRO001 | 25 | 10 |
| Sugar 1kg | GRO002 | 20 | 10 |
| Rice 2kg | GRO003 | 15 | 10 |
| Cooking Oil 1L | GRO004 | 12 | 10 |
| Tea Leaves 250g | GRO005 | 18 | 10 |
| Crisps | SNK001 | 60 | 10 |
| Biscuits | SNK002 | 55 | 10 |
| Chocolate Bar | SNK003 | 35 | 10 |
| Peanuts 100g | SNK004 | 40 | 10 |
| Soap Bar | PER001 | 30 | 10 |
| Toothpaste | PER002 | 25 | 10 |
| Shampoo 200ml | PER003 | 20 | 10 |
| Tissue Paper | HOU001 | 35 | 10 |
| Detergent 500g | HOU002 | 22 | 10 |
| Matchbox | HOU003 | 50 | 10 |

## Best Practices

### 1. Regular Stock Checks
- Review stock levels daily
- Check low stock alerts before opening
- Plan restocking based on sales velocity

### 2. Accurate Adjustments
- Always add reason/notes for adjustments
- Use correct adjustment type
- Double-check quantities before saving

### 3. Threshold Settings
- Set thresholds based on:
  - Lead time for restocking
  - Sales velocity
  - Storage capacity
- Review and adjust thresholds regularly

### 4. Stock Audits
- Perform physical stock counts periodically
- Use "Stock Correction" for discrepancies
- Document reasons for corrections

### 5. Prevent Stockouts
- Monitor low stock alerts daily
- Set up reorder points
- Maintain safety stock for fast-moving items

## Troubleshooting

### Sale Rejected - Insufficient Stock
**Problem**: Cannot complete sale due to stock shortage

**Solution**:
1. Check current stock: Go to Stock → Find product
2. If stock is actually available, use Stock Correction
3. If truly out of stock, remove item from cart or restock

### Stock Count Incorrect
**Problem**: Physical count doesn't match system

**Solution**:
1. Go to Stock → Click Adjust on product
2. Select "Stock Correction"
3. Enter difference (positive or negative)
4. Add reason explaining discrepancy
5. Save adjustment

### Low Stock Alerts Not Showing
**Problem**: Product is low but no alert

**Solution**:
1. Check product's low stock threshold
2. Adjust threshold if needed
3. Threshold might be set too low

### Cannot Add Product to Cart
**Problem**: Product won't add at POS

**Solution**:
1. Check if product is out of stock (red badge)
2. Restock the product
3. Refresh POS screen

## Workflow Examples

### Daily Opening Routine
1. Check dashboard for stock alerts
2. Review low stock products
3. Plan restocking for the day
4. Adjust stock for any overnight changes

### Receiving New Stock
1. Go to Stock → Find product
2. Click Adjust
3. Select "Restock"
4. Enter quantity received
5. Add supplier/invoice reference in notes
6. Save

### Handling Damaged Goods
1. Go to Stock → Find product
2. Click Adjust
3. Select "Damage/Loss"
4. Enter quantity damaged
5. Add reason (e.g., "Broken during transport")
6. Save

### Processing Returns
1. Go to Stock → Find product
2. Click Adjust
3. Select "Customer Return"
4. Enter quantity returned
5. Add reason/customer reference
6. Save

### End of Day Stock Check
1. Review today's sales
2. Check stock levels for fast-moving items
3. Note items needing restock
4. Plan tomorrow's orders

## Reports and Analytics

### Stock Value
Calculate total inventory value:
```python
from pos.models import Product
from django.db.models import Sum, F

total_value = Product.objects.aggregate(
    total=Sum(F('stock_quantity') * F('unit_price'))
)['total']
```

### Fast-Moving Items
Identify products with frequent stock changes:
```python
from pos.models import StockAdjustment
from django.db.models import Count

fast_movers = StockAdjustment.objects.values(
    'product__name'
).annotate(
    adjustment_count=Count('id')
).order_by('-adjustment_count')[:10]
```

### Stock Turnover
Track how quickly stock is sold:
- Monitor stock adjustment history
- Compare restock frequency
- Identify slow-moving items

## Future Enhancements

### Potential Additions
- **Automatic Reordering**: Auto-generate purchase orders
- **Supplier Management**: Track suppliers and costs
- **Batch/Lot Tracking**: Track product batches
- **Expiry Date Management**: Alert for expiring products
- **Multi-location Stock**: Track stock across locations
- **Stock Transfers**: Move stock between locations
- **Stock Forecasting**: Predict future stock needs
- **Barcode Printing**: Print stock labels
- **Stock Import/Export**: Bulk stock updates via CSV

## Summary

The inventory management system provides:
- ✅ Real-time stock tracking
- ✅ Automatic stock deduction on sales
- ✅ Low stock and out-of-stock alerts
- ✅ Complete stock adjustment history
- ✅ Stock validation at POS
- ✅ Easy stock management interface
- ✅ Detailed audit trail

The system prevents overselling, helps maintain optimal stock levels, and provides complete visibility into inventory movements.

---

**Version**: 1.2.0  
**Added**: February 6, 2026  
**Status**: ✅ Active
