# User Management Slug Parameter Fix

## Issue
User management views were throwing `TypeError: user_list() got an unexpected keyword argument 'slug'` when accessed via multi-tenant URLs like `/b/david/users/`.

## Root Cause
The user management view functions were not accepting the `slug` parameter that gets passed from the URL pattern. In multi-tenant URLs, all business-specific routes include the business slug as the first parameter.

## Solution
Added `slug` parameter to all user management view functions.

## Changes Made

### File: `posd/pos/views.py`

Updated 4 user management view functions:

#### 1. user_list
```python
# Before
def user_list(request):

# After
def user_list(request, slug):
```

#### 2. user_create
```python
# Before
def user_create(request):

# After
def user_create(request, slug):
```

#### 3. user_edit
```python
# Before
def user_edit(request, pk):

# After
def user_edit(request, slug, pk):
```

#### 4. user_delete
```python
# Before
def user_delete(request, pk):

# After
def user_delete(request, slug, pk):
```

## URL Pattern Structure

Multi-tenant URLs follow this pattern:
```
/b/<slug:slug>/<view-path>/
```

For example:
- `/b/david/users/` → `user_list(request, slug='david')`
- `/b/david/users/create/` → `user_create(request, slug='david')`
- `/b/david/users/5/edit/` → `user_edit(request, slug='david', pk=5)`
- `/b/david/users/5/delete/` → `user_delete(request, slug='david', pk=5)`

## Why Views Need the Slug Parameter

Even though the views don't directly use the `slug` parameter (the `@business_required` decorator sets `request.business` instead), they must accept it because:

1. Django's URL dispatcher passes ALL captured URL parameters to the view
2. The URL pattern captures `slug` as a parameter
3. If the view doesn't accept it, Python raises a TypeError

## Pattern for Multi-Tenant Views

All views under business-specific URLs should follow this pattern:

```python
@login_required
@business_required  # This decorator uses the slug to set request.business
def my_view(request, slug):  # Must accept slug even if not used directly
    # Use request.business instead of slug
    data = MyModel.objects.filter(business=request.business)
    ...
```

For views with additional parameters:
```python
@login_required
@business_required
def my_detail_view(request, slug, pk):  # slug first, then other params
    obj = get_object_or_404(MyModel, pk=pk, business=request.business)
    ...
```

## Related Views Already Fixed

These views already had the correct signature:
- `business_settings(request, slug=None)` ✅
- `activity_log(request, slug=None)` ✅
- `user_profile(request, slug=None)` ✅
- All payment method views ✅

## Testing

To verify the fix:

1. Log in as a business owner
2. Navigate to User Management: `/b/<your-business-slug>/users/`
3. Should load without TypeError ✅
4. Try creating a user: `/b/<your-business-slug>/users/create/`
5. Try editing a user: `/b/<your-business-slug>/users/<id>/edit/`
6. Try deleting a user: `/b/<your-business-slug>/users/<id>/delete/`

## Status
✅ **COMPLETE** - All user management views now accept the slug parameter correctly.
