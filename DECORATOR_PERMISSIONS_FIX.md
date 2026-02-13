# Decorator Permissions Fix - Business Owner Access

## Issue
Business owners were getting "You do not have permission to access this page" errors when trying to access:
- Business Settings
- User Management
- Activity Log
- Product Management
- Purchase Management

## Root Cause
The legacy decorators in `posd/pos/views.py` were only checking for:
1. Superuser status
2. Django groups (old system: 'Manager', 'Stock Manager', etc.)
3. Django permissions

They were NOT checking for business membership roles (the new multi-tenant system), so business owners with `role='owner'` in `BusinessMembership` were being denied access.

## Solution
Updated all legacy decorators to check for business membership roles before falling back to Django groups.

## Files Modified

### `posd/pos/views.py`

Updated 3 legacy decorators:

#### 1. `manager_required` Decorator
**Used by:**
- `business_settings()` - Line 1861
- `user_list()` - Line 1550
- `activity_log()` - Line 1950

**Changes:**
```python
# Before: Only checked Django groups
if request.user.is_superuser or request.user.groups.filter(name='Manager').exists():

# After: Checks business membership first
if request.user.is_superuser:
    return view_func(request, *args, **kwargs)

# Check business membership role (multi-tenant)
if hasattr(request, 'business_membership') and request.business_membership:
    role = request.business_membership.role
    if role in ['owner', 'admin', 'manager']:
        return view_func(request, *args, **kwargs)

# Fallback to Django groups (legacy)
if request.user.groups.filter(name__in=['Administrator', 'Manager']).exists():
    return view_func(request, *args, **kwargs)
```

#### 2. `can_manage_products` Decorator
**Used by:**
- Product CRUD views

**Changes:**
Now checks for business membership roles: `['owner', 'admin', 'manager', 'stock_manager']`

#### 3. `can_manage_purchases` Decorator
**Used by:**
- Purchase CRUD views

**Changes:**
Now checks for business membership roles: `['owner', 'admin', 'manager', 'stock_manager']`

## Permission Hierarchy

### Business Membership Roles (Multi-Tenant System)
1. **owner** - Full access (business creator)
2. **admin** - Full administrative access
3. **manager** - Management access
4. **stock_manager** - Stock and inventory management
5. **cashier** - POS operations
6. **sales** - Sales operations
7. **viewer** - Read-only

### Decorator Access Levels

| Decorator | Roles Allowed |
|-----------|---------------|
| `manager_required` | owner, admin, manager |
| `can_manage_products` | owner, admin, manager, stock_manager |
| `can_manage_purchases` | owner, admin, manager, stock_manager |

## How It Works

1. **Request comes in** → Middleware sets `request.business_membership`
2. **Decorator checks:**
   - First: Is user superuser? → Allow
   - Second: Does user have business membership with appropriate role? → Allow
   - Third: Does user have legacy Django group? → Allow (backward compatibility)
   - Otherwise: Deny with error message

3. **Business membership is set by middleware:**
   ```python
   # In middleware.py
   membership = BusinessMembership.objects.get(
       user=request.user,
       business=business,
       is_active=True
   )
   request.business_membership = membership
   ```

## Testing

To verify the fix works:

1. **As Business Owner:**
   - Log in with the account that created the business
   - Navigate to Business Settings → Should work ✅
   - Navigate to User Management → Should work ✅
   - Navigate to Activity Log → Should work ✅

2. **As Regular User (non-owner):**
   - Log in with a cashier/sales account
   - Try to access Business Settings → Should be denied ❌
   - Try to access User Management → Should be denied ❌

3. **Check Business Membership:**
   ```python
   # In Django shell
   from pos.models import BusinessMembership
   
   # Check your membership
   membership = BusinessMembership.objects.get(
       user__username='your_username',
       business__slug='your-business-slug'
   )
   print(f"Role: {membership.role}")  # Should be 'owner' for business creator
   ```

## Backward Compatibility

The decorators still support the old Django groups system:
- Users with 'Administrator' or 'Manager' groups will still have access
- This ensures existing setups continue to work
- New multi-tenant businesses use the BusinessMembership roles

## Related Changes

This fix complements the earlier permission system update in:
- `posd/pos/permissions.py` - Context processor permissions
- `BUSINESS_OWNER_PERMISSIONS_FIX.md` - Template permission checks

Together, these ensure business owners have full access to their business management features.

## Status
✅ **COMPLETE** - Business owners can now access all management features without permission errors.
