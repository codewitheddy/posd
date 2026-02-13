# View Migration Checklist

## 🎯 Purpose
This checklist helps you systematically update all views to support multi-tenancy.

## 📋 View Update Pattern

### Before (Single Tenant)
```python
@login_required
def product_list(request):
    products = Product.objects.all()
    return render(request, 'products.html', {'products': products})
```

### After (Multi-Tenant)
```python
from pos.decorators import business_required

@business_required
def product_list(request):
    products = Product.objects.filter(business=request.business)
    return render(request, 'products.html', {'products': products})
```

## ✅ Views to Update

### Priority 1: Critical (Update First)

#### Dashboard & POS
- [ ] `dashboard` - Filter all stats by business
- [ ] `pos_screen` - Filter products by business
- [ ] `complete_sale` - Set business on sale creation
- [ ] `search_product_by_code` - Filter by business

#### Products
- [ ] `product_list` - Filter by business
- [ ] `product_create` - Set business on creation
- [ ] `product_edit` - Filter by business
- [ ] `product_delete` - Filter by business
- [ ] `product_bulk_upload` - Set business on bulk create

#### Sales & Invoices
- [ ] `invoice_view` - Filter by business
- [ ] `invoice_pdf` - Filter by business
- [ ] `thermal_receipt` - Filter by business

### Priority 2: Important (Update Soon)

#### Stock Management
- [ ] `stock_list` - Filter by business
- [ ] `stock_adjust` - Filter by business
- [ ] `stock_history` - Filter by business
- [ ] `low_stock_alert` - Filter by business
- [ ] `expiry_alert` - Filter by business
- [ ] `update_expiry` - Filter by business

#### Suppliers
- [ ] `supplier_list` - Filter by business
- [ ] `supplier_create` - Set business on creation
- [ ] `supplier_edit` - Filter by business
- [ ] `supplier_delete` - Filter by business
- [ ] `supplier_payments` - Filter by business
- [ ] `supplier_statement` - Filter by business

#### Purchases
- [ ] `purchase_list` - Filter by business
- [ ] `purchase_create` - Set business on creation
- [ ] `purchase_detail` - Filter by business
- [ ] `purchase_receive` - Filter by business
- [ ] `purchase_cancel` - Filter by business

### Priority 3: Standard (Update When Possible)

#### Reports
- [ ] `sales_report` - Filter by business
- [ ] `cashier_report` - Filter by business
- [ ] `writeoff_report` - Filter by business
- [ ] `z_report` - Filter by business
- [ ] `z_report_pdf` - Filter by business
- [ ] `payment_transactions_report` - Filter by business
- [ ] `analytics_api` - Filter by business

#### Customers
- [ ] `customer_list` - Filter by business
- [ ] `customer_create` - Set business on creation
- [ ] `customer_edit` - Filter by business
- [ ] `customer_detail` - Filter by business

#### Categories
- [ ] `category_list` - Filter by business
- [ ] `category_create` - Set business on creation

#### Users
- [ ] `user_list` - Filter by business membership
- [ ] `user_create` - Create business membership
- [ ] `user_edit` - Update business membership
- [ ] `user_delete` - Remove business membership
- [ ] `user_profile` - Show business context

#### Settings
- [ ] `business_settings` - Filter by business
- [ ] `activity_log` - Filter by business

## 🔧 Update Steps for Each View

### Step 1: Add Decorator
```python
from pos.decorators import business_required

@business_required  # Add this
def my_view(request):
    ...
```

### Step 2: Filter Queries
```python
# Before
products = Product.objects.all()

# After
products = Product.objects.filter(business=request.business)
```

### Step 3: Set Business on Create
```python
# Before
product = Product.objects.create(
    name=request.POST['name'],
    price=request.POST['price']
)

# After
product = Product.objects.create(
    business=request.business,  # Add this
    name=request.POST['name'],
    price=request.POST['price']
)
```

### Step 4: Update Redirects
```python
# Before
return redirect('product_list')

# After
return redirect('product_list', slug=request.business.slug)
```

### Step 5: Update get_object_or_404
```python
# Before
product = get_object_or_404(Product, pk=pk)

# After
product = get_object_or_404(Product, pk=pk, business=request.business)
```

## 📝 Template Updates

### Update All URLs
```django
<!-- Before -->
<a href="{% url 'product_list' %}">Products</a>
<a href="{% url 'product_edit' pk=product.id %}">Edit</a>

<!-- After -->
<a href="{% url 'product_list' slug=request.business.slug %}">Products</a>
<a href="{% url 'product_edit' slug=request.business.slug pk=product.id %}">Edit</a>
```

### Update Forms
```django
<!-- Before -->
<form method="post" action="{% url 'product_create' %}">

<!-- After -->
<form method="post" action="{% url 'product_create' slug=request.business.slug %}">
```

## 🧪 Testing Each View

### Test Checklist
- [ ] View loads without errors
- [ ] Data is filtered by business
- [ ] Create operations set business
- [ ] Update operations check business
- [ ] Delete operations check business
- [ ] Redirects include business slug
- [ ] No cross-business data visible
- [ ] Permissions work correctly

### Test Script
```python
# Test data isolation
from pos.models import Business, Product
from django.contrib.auth.models import User

# Create two businesses
user1 = User.objects.create_user('user1', 'u1@test.com', 'pass')
user2 = User.objects.create_user('user2', 'u2@test.com', 'pass')

b1 = Business.objects.create(name='B1', slug='b1', owner=user1)
b2 = Business.objects.create(name='B2', slug='b2', owner=user2)

# Create products
Product.objects.create(business=b1, name='P1', product_code='P1', unit_price=10)
Product.objects.create(business=b2, name='P2', product_code='P2', unit_price=20)

# Test isolation
assert Product.objects.filter(business=b1).count() == 1
assert Product.objects.filter(business=b2).count() == 1

# Login as user1 and verify only sees P1
# Login as user2 and verify only sees P2
```

## 📊 Progress Tracking

### Overall Progress
- Total Views: ~50
- Updated: 0
- Remaining: 50
- Progress: 0%

### By Category
- [ ] Dashboard & POS (0/4)
- [ ] Products (0/5)
- [ ] Sales & Invoices (0/3)
- [ ] Stock Management (0/6)
- [ ] Suppliers (0/6)
- [ ] Purchases (0/5)
- [ ] Reports (0/7)
- [ ] Customers (0/4)
- [ ] Categories (0/2)
- [ ] Users (0/5)
- [ ] Settings (0/2)

## 🚨 Common Mistakes

### ❌ Mistake 1: Forgetting to Filter
```python
# Wrong
products = Product.objects.all()

# Right
products = Product.objects.filter(business=request.business)
```

### ❌ Mistake 2: Not Setting Business on Create
```python
# Wrong
product = Product.objects.create(name='Test')

# Right
product = Product.objects.create(business=request.business, name='Test')
```

### ❌ Mistake 3: Missing Slug in Redirect
```python
# Wrong
return redirect('product_list')

# Right
return redirect('product_list', slug=request.business.slug)
```

### ❌ Mistake 4: Not Checking Business in get_object_or_404
```python
# Wrong
product = get_object_or_404(Product, pk=pk)

# Right
product = get_object_or_404(Product, pk=pk, business=request.business)
```

## 💡 Pro Tips

1. **Update in Batches**
   - Start with critical views
   - Test thoroughly after each batch
   - Don't rush

2. **Use Find & Replace**
   - Find: `Product.objects.all()`
   - Replace: `Product.objects.filter(business=request.business)`

3. **Test Immediately**
   - Test each view after updating
   - Verify data isolation
   - Check permissions

4. **Keep Notes**
   - Document any issues
   - Note special cases
   - Track progress

5. **Backup First**
   - Commit before starting
   - Create backup branch
   - Test in development

## 🎯 Quick Reference

### Import Statement
```python
from pos.decorators import business_required, business_permission_required
```

### Basic Pattern
```python
@business_required
def my_view(request):
    # request.business is available
    # request.business_membership has user's role
    items = Model.objects.filter(business=request.business)
    return render(request, 'template.html', {'items': items})
```

### With Permission
```python
@business_permission_required('edit')
def edit_view(request, pk):
    item = get_object_or_404(Model, pk=pk, business=request.business)
    # Only users with 'edit' permission can access
    return render(request, 'edit.html', {'item': item})
```

### Create Pattern
```python
@business_required
def create_view(request):
    if request.method == 'POST':
        item = Model.objects.create(
            business=request.business,  # Always set this
            name=request.POST['name']
        )
        return redirect('list_view', slug=request.business.slug)
    return render(request, 'create.html')
```

## ✅ Completion

When all views are updated:
- [ ] All views have business decorators
- [ ] All queries filter by business
- [ ] All creates set business
- [ ] All redirects include slug
- [ ] All templates updated
- [ ] All tests passing
- [ ] Data isolation verified
- [ ] Ready for production!

## 🎉 Done!

Once complete, your application will be fully multi-tenant with:
- Complete data isolation
- Proper access control
- Business-specific operations
- Market-ready SaaS platform

Good luck with the migration! 🚀
