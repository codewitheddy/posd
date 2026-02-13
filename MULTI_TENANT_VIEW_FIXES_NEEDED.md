# Multi-Tenant View Fixes Required

## Issue
Many views in `posd/pos/views.py` are missing the `@business_required` decorator and don't filter queries by `request.business`. This causes errors in the multi-tenant setup.

## Views Fixed So Far
- ✅ `pos_screen` - Added @business_required and business filtering
- ✅ `complete_sale` - Added @business_required and business filtering  
- ✅ `analytics_api` - Added @business_required and business filtering
- ✅ `analytics_export_pdf` - Added @business_required and business filtering
- ✅ `product_create` - Added @business_required and business filtering

## Critical Views Still Needing Fixes (Quick Actions)
These are the views linked from dashboard quick action buttons:

### 1. `purchase_create` (Line ~994)
- Add `@business_required` decorator
- Filter `Supplier.objects` by `business=request.business`
- Filter `Product.objects` by `business=request.business`
- Add `business=request.business` when creating Purchase
- Update redirects to include `slug=request.business.slug`

### 2. `stock_list` (Line ~786)
- Add `@business_required` decorator
- Filter `Product.objects` by `business=request.business`
- Filter `Category.objects` by `business=request.business`

### 3. `sales_report` (Line ~720)
- Add `@business_required` decorator
- Filter `Sale.objects` by `business=request.business`

### 4. `low_stock_alert` (Line ~863)
- Add `@business_required` decorator
- Filter `Product.objects` by `business=request.business`

### 5. `expiry_alert` (Line ~1121)
- Add `@business_required` decorator
- Filter `Product.objects` by `business=request.business`

### 6. `stock_adjust` (Line ~806)
- Add `@business_required` decorator
- Filter `get_object_or_404(Product, pk=pk, business=request.business)`
- Update redirects to include `slug=request.business.slug`

### 7. `payment_transactions_report` (Line ~2826)
- Add `@business_required` decorator
- Filter all queries by `business=request.business`

## Pattern for Fixing Each View

```python
# 1. Change decorator
@login_required  # OLD
@business_required  # NEW

# 2. Filter all queries
Model.objects.all()  # OLD
Model.objects.filter(business=request.business).all()  # NEW

# 3. Filter get_object_or_404
get_object_or_404(Model, pk=pk)  # OLD
get_object_or_404(Model, pk=pk, business=request.business)  # NEW

# 4. Add business when creating objects
Model.objects.create(field=value)  # OLD
Model.objects.create(business=request.business, field=value)  # NEW

# 5. Update redirects
return redirect('view_name')  # OLD
return redirect('view_name', slug=request.business.slug)  # NEW
```

## Additional Views Needing Fixes (Lower Priority)
- `product_list`, `product_edit`, `product_delete`
- `category_list`, `category_create`
- `supplier_list`, `supplier_create`, `supplier_edit`, `supplier_delete`
- `purchase_list`, `purchase_detail`, `purchase_receive`, `purchase_cancel`
- `customer_list`, `customer_create`, `customer_edit`, `customer_detail`
- `invoice_view`, `thermal_receipt`, `invoice_pdf`
- `search_product_by_code`
- `stock_history`, `update_expiry`
- `writeoff_report`
- `payment_transactions_export`, `payment_transactions_csv`
- `user_profile`

## Import Required
Make sure this import is at the top of views.py:
```python
from .decorators import business_required, business_permission_required
```

## Testing Checklist
After fixing each view:
1. Test the view loads without errors
2. Test it only shows data for the current business
3. Test it can't access data from other businesses
4. Test all redirects work correctly with slug parameter
