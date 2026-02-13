# SupplierPayment payment_number Unique Constraint Fix

## Issue
Error when creating supplier payments: `UNIQUE constraint failed: pos_supplierpayment.payment_number`

## Root Cause
The `payment_number` field in the SupplierPayment model had a global `unique=True` constraint from the initial migration (0011), which conflicts with multi-tenancy requirements. Each business should be able to have its own payment number sequence.

## Solution
Created migration `0021_fix_supplierpayment_payment_number_unique.py` that:
1. Removes the global `unique=True` constraint from the `payment_number` field
2. Keeps the `unique_together = [['business', 'payment_number']]` constraint (already added in migration 0019)

## Changes Made

### Migration: 0021_fix_supplierpayment_payment_number_unique.py
- Altered `payment_number` field to remove global unique constraint
- Payment numbers are now unique only within each business

## Result
- Each business can now have its own payment number sequence
- Payment numbers like PAY-20260213-0001 can exist in multiple businesses
- Multi-tenancy data isolation is maintained

## Testing
After applying this migration:
1. ✅ Create payment in Business A with payment_number PAY-20260213-0001
2. ✅ Create payment in Business B with payment_number PAY-20260213-0001 (should work)
3. ✅ Try to create duplicate payment_number in same business (should fail)

## Related Fixes
This is the same pattern we used for:
- PaymentMethod (migrations 0003, 0015)
- Category (migration 0016)
- Purchase (migration 0017)
- Sale (migration 0018)
- SupplierPayment (migrations 0019, 0021)

## Files Modified
- `posd/pos/migrations/0021_fix_supplierpayment_payment_number_unique.py` (created)

## Migration Applied
```bash
python manage.py migrate
# Applying pos.0021_fix_supplierpayment_payment_number_unique... OK
```

## Status
✅ FIXED - Supplier payments can now be created without unique constraint errors
