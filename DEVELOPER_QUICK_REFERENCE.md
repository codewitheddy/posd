# Multi-Tenant Development Quick Reference

## 🎯 Essential Patterns

### 1. View with Business Context

```python
from pos.decorators import business_required

@business_required
def my_view(request):
    # request.business is automatically available
    # request.business_membership contains user's role
    
    products = Product.objects.filter(business=request.business)
    return render(request, 'template.html', {'products': products})
```

### 2. View with Permission Check

```python
from pos.decorators import business_permission_required

@business_permission_required('edit')
def edit_product(request, pk):
    product = get_object_or_404(Product, pk=pk, business=request.business)
    # Only users with 'edit' permission can access
    return render(request, 'edit.html', {'product': product})
```

### 3. Creating Objects

```python
@business_required
def create_product(request):
    if request.method == 'POST':
        product = Product.objects.create(
            business=request.business,  # Always set business!
            name=request.POST['name'],
            price=request.POST['price']
        )
        return redirect('product_list', slug=request.business.slug)
```

### 4. Querying Data

```python
# Always filter by business
products = Product.objects.filter(business=request.business)

# With related objects
sales = Sale.objects.filter(
    business=request.business
).select_related('cashier', 'customer')

# Aggregations
total = Sale.objects.filter(
    business=request.business
).aggregate(Sum('total'))
```

### 5. Template URLs

```django
<!-- Always include business slug -->
<a href="{% url 'product_list' slug=request.business.slug %}">Products</a>

<!-- With parameters -->
<a href="{% url 'product_edit' slug=request.business.slug pk=product.id %}">Edit</a>

<!-- Forms -->
<form method="post" action="{% url 'product_create' slug=request.business.slug %}">
    {% csrf_token %}
    ...
</form>
```

## 🔐 Available Decorators

```python
from pos.decorators import (
    business_required,              # Ensures business context exists
    business_permission_required,   # Checks specific permission
    business_owner_required,        # Only business owner
    business_admin_required,        # Owner or admin only
)

# Usage
@business_required
@business_permission_required('create')
@business_owner_required
@business_admin_required
```

## 👥 Permission Levels

```python
# In views, check user's role
if request.business_membership.role == 'owner':
    # Owner-only logic
    pass

# Or check permission
if request.business_membership.has_permission('edit'):
    # User can edit
    pass

# Available permissions:
# 'all', 'view', 'create', 'edit', 'delete', 'reports', 'users', 'stock', 'pos'
```

## 🔄 Common Patterns

### Get or Create with Business

```python
category, created = Category.objects.get_or_create(
    business=request.business,
    name='Electronics'
)
```

### Update with Business Check

```python
product = get_object_or_404(
    Product,
    pk=pk,
    business=request.business  # Ensures user can only access their business data
)
product.name = 'Updated Name'
product.save()
```

### Delete with Business Check

```python
product = get_object_or_404(Product, pk=pk, business=request.business)
product.delete()
```

### Bulk Operations

```python
# Update multiple records
Product.objects.filter(
    business=request.business,
    category=old_category
).update(category=new_category)

# Delete multiple records
Product.objects.filter(
    business=request.business,
    stock_quantity=0
).delete()
```

## 📊 Reporting Queries

```python
from django.db.models import Sum, Count, Avg
from datetime import datetime, timedelta

# Sales report for business
today = datetime.now().date()
sales_today = Sale.objects.filter(
    business=request.business,
    date__date=today
).aggregate(
    total=Sum('total'),
    count=Count('id'),
    average=Avg('total')
)

# Top products
top_products = Product.objects.filter(
    business=request.business
).annotate(
    total_sold=Sum('saleitem__quantity')
).order_by('-total_sold')[:10]
```

## 🔧 Helper Functions

```python
from pos.decorators import get_business_queryset

# Get filtered queryset
products = get_business_queryset(request, Product)
categories = get_business_queryset(request, Category)
```

## ⚠️ Common Mistakes to Avoid

### ❌ DON'T: Query without business filter
```python
products = Product.objects.all()  # Exposes all businesses!
```

### ✅ DO: Always filter by business
```python
products = Product.objects.filter(business=request.business)
```

### ❌ DON'T: Forget business in create
```python
product = Product.objects.create(name='Test')  # Missing business!
```

### ✅ DO: Always set business
```python
product = Product.objects.create(
    business=request.business,
    name='Test'
)
```

### ❌ DON'T: Hard-code URLs
```python
return redirect('/products/')  # Missing business slug!
```

### ✅ DO: Use reverse with slug
```python
return redirect('product_list', slug=request.business.slug)
```

## 🧪 Testing

```python
from django.test import TestCase
from pos.models import Business, BusinessMembership
from django.contrib.auth.models import User

class ProductTestCase(TestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        
        # Create test business
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            owner=self.user
        )
        
        # Create membership
        self.membership = BusinessMembership.objects.create(
            user=self.user,
            business=self.business,
            role='owner'
        )
        
        # Login
        self.client.login(username='testuser', password='testpass')
    
    def test_product_list(self):
        response = self.client.get(f'/b/{self.business.slug}/products/')
        self.assertEqual(response.status_code, 200)
```

## 📝 Checklist for New Views

- [ ] Add `@business_required` decorator
- [ ] Filter all queries by `business=request.business`
- [ ] Set `business=request.business` when creating objects
- [ ] Include `slug=request.business.slug` in redirects
- [ ] Update template URLs with business slug
- [ ] Add permission checks if needed
- [ ] Test with multiple businesses
- [ ] Verify data isolation

## 🚀 Quick Commands

```bash
# Setup multi-tenancy
python manage.py setup_multitenant

# Create migrations
python manage.py makemigrations

# Run migrations
python manage.py migrate

# Create test business
python manage.py shell
>>> from pos.models import Business
>>> Business.objects.create(name='Test', slug='test', owner_id=1)
```

## 📚 Key Files

- **Models**: `pos/models.py` (Business, BusinessMembership)
- **Middleware**: `pos/middleware.py` (TenantMiddleware)
- **Decorators**: `pos/decorators.py`
- **Views**: `pos/tenant_views.py`
- **URLs**: `pos/urls_multitenant.py`
- **Migration**: `pos/migrations/0002_multi_tenancy.py`

## 💡 Pro Tips

1. **Always use decorators** - They handle business context automatically
2. **Test data isolation** - Create multiple businesses and verify separation
3. **Use select_related** - Include business in queries for performance
4. **Cache business settings** - Avoid repeated database queries
5. **Log access attempts** - Track cross-business access for security

## 🆘 Need Help?

Check these files:
- `MULTI_TENANT_SETUP_GUIDE.md` - Complete setup guide
- `MULTI_TENANCY_IMPLEMENTATION.md` - Architecture overview
- `pos/decorators.py` - Available decorators and helpers
