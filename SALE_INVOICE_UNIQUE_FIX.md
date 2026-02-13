# Sale Invoice Number Unique Constraint Fix

## Issue
Error: "UNIQUE constraint failed: pos_sale.invoice_number"

## Root Cause
The Sale model had a global unique constraint on the `invoice_number` field from the initial migration, but the current model definition only specifies `unique_together = [['business', 'invoice_number']]`.

This caused issues in multi-tenant setup where:
- Different businesses should be able to have the same invoice numbers
- Invoice numbers should only be unique within each business
- The global unique constraint prevented this

## Problem Details

### Initial Migration (0001_initial.py)
```python
('invoice_number', models.CharField(editable=False, max_length=20, unique=True))
```
This created a database-level UNIQUE constraint on the invoice_number column.

### Current Model (models.py)
```python
class Sale(models.Model):
    invoice_number = models.CharField(max_length=20, editable=False)
    
    class Meta:
        unique_together = [['business', 'invoice_number']]
```
The model expects invoice_number to be unique per business, not globally.

## Solution

Created migration `0018_fix_sale_invoice_unique.py` to remove the global unique constraint:

```python
operations = [
    migrations.AlterField(
        model_name='sale',
        name='invoice_number',
        field=models.CharField(editable=False, max_length=20),
    ),
]
```

This removes `unique=True` from the field while keeping the `unique_together` constraint at the model level.

## Multi-Tenancy Compliance

Now invoice numbers work correctly for multi-tenant setup:
- Business A can have invoice INV-20260213-0001
- Business B can also have invoice INV-20260213-0001
- Each business has its own invoice number sequence
- Invoice numbers are unique within each business (via unique_together)

## Invoice Number Generation

The Sale model's save() method generates invoice numbers:
```python
def save(self, *args, **kwargs):
    if not self.invoice_number:
        today = timezone.now()
        date_str = today.strftime('%Y%m%d')
        last_sale = Sale.objects.filter(
            business=self.business, 
            invoice_number__startswith=f'INV-{date_str}'
        ).order_by('-invoice_number').first()
        if last_sale:
            last_num = int(last_sale.invoice_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1
        self.invoice_number = f'INV-{date_str}-{new_num:04d}'
    super().save(*args, **kwargs)
```

Format: `INV-YYYYMMDD-XXXX`
- INV = Invoice prefix
- YYYYMMDD = Date (e.g., 20260213)
- XXXX = Sequential number (0001, 0002, etc.)

The query filters by business, so each business gets its own sequence.

## Migration Applied

```bash
python manage.py migrate pos
```

Output:
```
Applying pos.0018_fix_sale_invoice_unique... OK
```

## Testing

Sales can now be completed successfully:
1. Add items to cart
2. Click "Complete Sale"
3. Add payment methods
4. Confirm payment
5. Sale is created with business-specific invoice number
6. No more UNIQUE constraint errors

## Related Fixes

This is part of a series of multi-tenancy unique constraint fixes:
- 0003_fix_paymentmethod_unique.py - Fixed PaymentMethod code
- 0015_fix_paymentmethod_name_unique.py - Fixed PaymentMethod name
- 0016_fix_category_unique.py - Fixed Category name
- 0017_fix_purchase_unique.py - Fixed Purchase purchase_number
- 0018_fix_sale_invoice_unique.py - Fixed Sale invoice_number (this fix)

All models now properly support multi-tenancy with per-business unique constraints.

## Files Created

- `posd/pos/migrations/0018_fix_sale_invoice_unique.py` - Migration to remove global unique constraint

## Verification

To verify the fix works:
1. Create a sale in Business A
2. Create a sale in Business B
3. Both can have the same invoice number format
4. No UNIQUE constraint errors

The complete sale functionality should now work end-to-end!
