# Payment Method Unique Constraint Fix

## Issue
When creating payment methods, users were getting:
```
IntegrityError: UNIQUE constraint failed: pos_paymentmethod.code
IntegrityError: UNIQUE constraint failed: pos_paymentmethod.name
```

This occurred when trying to create a payment method with a name or code (like "Cash" or "CASH") that already existed in another business.

## Root Cause
The PaymentMethod model had unique constraints on both the `name` and `code` fields, making them globally unique across all businesses. This violated multi-tenancy principles where each business should be able to have their own payment methods with common names and codes.

## Solution
Created two migrations to fix the unique constraints to be per-business instead of global:
1. Fixed `code` field - now unique per business via `unique_together`
2. Fixed `name` field - removed global unique constraint

## Changes Made

### Migration 1: `0003_fix_paymentmethod_unique.py`

Fixed the `code` field unique constraint:

```python
operations = [
    # Remove old unique constraint on code field
    migrations.AlterField(
        model_name='paymentmethod',
        name='code',
        field=models.CharField(max_length=20),  # No unique=True
    ),
    # Ensure unique_together is properly set
    migrations.AlterUniqueTogether(
        name='paymentmethod',
        unique_together={('business', 'code')},  # Unique per business
    ),
]
```

### Migration 2: `0015_fix_paymentmethod_name_unique.py`

Fixed the `name` field unique constraint:

```python
operations = [
    # Remove unique constraint on name field
    migrations.AlterField(
        model_name='paymentmethod',
        name='name',
        field=models.CharField(max_length=100),  # No unique=True
    ),
]
```

### Model Definition (Already Correct)

```python
class PaymentMethod(models.Model):
    business = models.ForeignKey('Business', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)  # Not globally unique
    is_active = models.BooleanField(default=True)
    requires_reference = models.BooleanField(default=False)
    icon = models.CharField(max_length=50, blank=True)
    
    class Meta:
        ordering = ['name']
        unique_together = [['business', 'code']]  # ✅ Unique per business
```

## What This Means

### Before Fix
- ❌ Only ONE business could have a payment method with code "CASH"
- ❌ Only ONE business could have a payment method named "Cash"
- ❌ If Business A created "MPESA", Business B couldn't create "MPESA"
- ❌ Global uniqueness violated multi-tenancy

### After Fix
- ✅ Each business can have its own "Cash" payment method
- ✅ Each business can have its own "CASH" code
- ✅ Multiple businesses can have "M-Pesa" with different settings
- ✅ Code is unique within a business (can't have two "CASH" methods in same business)
- ✅ Names can be duplicated across businesses
- ✅ Proper multi-tenancy isolation

## Example Scenarios

### Scenario 1: Multiple Businesses with Same Codes
```
Business A:
  - CASH (Cash Payment)
  - MPESA (M-Pesa Mobile Money)
  - CARD (Credit/Debit Card)

Business B:
  - CASH (Cash Payment)  ✅ Allowed (different business)
  - MPESA (M-Pesa)       ✅ Allowed (different business)
  - BANK (Bank Transfer) ✅ Allowed (unique code in Business B)
```

### Scenario 2: Duplicate Within Same Business
```
Business A:
  - CASH (Cash Payment)
  - CASH (Cash on Delivery)  ❌ Not allowed (same business, same code)
```

## Migration Process

1. Created migration file: `0003_fix_paymentmethod_unique.py`
2. Merged with existing migrations: `0014_merge_20260213_0012.py`
3. Applied migrations: `python manage.py migrate`
4. Database schema updated successfully

## Testing

To verify the fix:

1. **Test 1: Create payment method in Business A**
   - Go to Business A
   - Create payment method with code "CASH"
   - Should succeed ✅

2. **Test 2: Create same code in Business B**
   - Go to Business B
   - Create payment method with code "CASH"
   - Should succeed ✅ (different business)

3. **Test 3: Try duplicate in same business**
   - Stay in Business B
   - Try to create another payment method with code "CASH"
   - Should fail with validation error ❌ (same business)

## Validation in Views

The view already checks for duplicates within the business:

```python
# In payment_method_create view
if PaymentMethod.objects.filter(business=request.business, code=code).exists():
    messages.error(request, f'Payment method with code "{code}" already exists.')
    return redirect('payment_method_create', slug=request.business.slug)
```

This provides a user-friendly error message before the database constraint is hit.

## Common Payment Method Codes

Each business can now independently use these common codes:

- **CASH** - Cash payments
- **MPESA** - M-Pesa mobile money
- **CARD** - Credit/Debit cards
- **BANK** - Bank transfers
- **AIRTEL** - Airtel Money
- **CHEQUE** - Cheque payments
- **CREDIT** - Credit/Account payments

## Status
✅ **COMPLETE** - Payment method codes are now unique per business, allowing proper multi-tenancy.
