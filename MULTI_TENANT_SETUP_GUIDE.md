# Multi-Tenant POS System - Setup Guide

## 🎯 Overview

Your POS system is now a **multi-tenant SaaS application**! Each business operates independently with complete data isolation.

## 🚀 Quick Start

### 1. Run Migrations

```bash
cd posd
python manage.py makemigrations
python manage.py migrate
```

This will:
- Create `Business` and `BusinessMembership` models
- Add `business` foreign key to all data models
- Create a default business for existing data
- Set up unique constraints per business

### 2. Access the System

#### For New Users (Registration Flow)
1. Visit: `http://your-domain.com/register/`
2. Fill in business details and create account
3. Get 30-day free trial automatically
4. Start using your POS system at `/b/{your-business-slug}/`

#### For Existing Users
1. Login at: `http://your-domain.com/login/`
2. Select business from: `http://your-domain.com/businesses/`
3. Access dashboard: `/b/{business-slug}/`

### 3. URL Structure

**Before (Single Tenant):**
```
/products/
/pos/
/reports/sales/
```

**After (Multi-Tenant):**
```
/register/                    # New business registration
/businesses/                  # Business selection
/b/{slug}/products/          # Business-specific routes
/b/{slug}/pos/
/b/{slug}/reports/sales/
```

## 📋 Features

### Business Management
- ✅ Self-service registration
- ✅ Business profile management
- ✅ Team member invitations
- ✅ Role-based access control per business
- ✅ 30-day free trial
- ✅ Subscription plans (ready for billing integration)

### Data Isolation
- ✅ Complete separation between businesses
- ✅ Users can belong to multiple businesses
- ✅ Cross-business data access prevention
- ✅ Business-specific settings

### Security
- ✅ Business ownership verification
- ✅ Membership-based access control
- ✅ Role-based permissions
- ✅ Audit logging per business

## 🔧 Configuration

### Enable Multi-Tenancy Middleware

Already configured in `settings.py`:
```python
MIDDLEWARE = [
    ...
    'pos.middleware.TenantMiddleware',  # Detects business from URL
    ...
]
```

### Update Your Views

#### Option 1: Use Decorators (Recommended)
```python
from pos.decorators import business_required, business_permission_required

@business_required
def my_view(request):
    # request.business is automatically available
    products = Product.objects.filter(business=request.business)
    return render(request, 'template.html', {'products': products})

@business_permission_required('edit')
def edit_view(request):
    # Only users with 'edit' permission can access
    pass
```

#### Option 2: Manual Filtering
```python
@login_required
def my_view(request):
    if not hasattr(request, 'business'):
        return redirect('business_list')
    
    products = Product.objects.filter(business=request.business)
    return render(request, 'template.html', {'products': products})
```

### Update Your Templates

Add business slug to URLs:
```django
<!-- Before -->
<a href="{% url 'product_list' %}">Products</a>

<!-- After -->
<a href="{% url 'product_list' slug=request.business.slug %}">Products</a>
```

## 👥 User Roles

Each business has its own role hierarchy:

| Role | Permissions |
|------|------------|
| **Owner** | Full access, cannot be removed |
| **Administrator** | Full access except ownership transfer |
| **Manager** | View, create, edit, reports, user management |
| **Stock Manager** | View, create, edit, stock management |
| **Cashier** | View, create, POS operations |
| **Sales Associate** | View, create, POS operations |
| **Viewer** | Read-only access |

## 🔐 API Changes

### JWT Authentication with Business Context

```python
# Include business in API requests
headers = {
    'Authorization': 'Bearer {token}',
    'X-Business-Slug': 'my-business'
}
```

### API Endpoints

All API endpoints now require business context:
```
POST /api/v1/auth/token/
GET  /api/v1/products/?business=my-business
POST /api/v1/sales/?business=my-business
```

## 📊 Database Schema

### New Models

**Business**
- name, slug, owner
- address, phone, email, tax_id
- is_active, is_trial, trial_ends_at
- subscription_plan
- created_at, updated_at

**BusinessMembership**
- user, business, role
- is_active
- joined_at, updated_at

### Modified Models

All data models now include:
```python
business = models.ForeignKey(Business, on_delete=models.CASCADE)
```

Affected models:
- Category, Product, Sale, SaleItem
- Supplier, Purchase, PurchaseItem
- Customer, PaymentMethod, SalePayment
- Shift, SaleReturn, Promotion
- Expense, LoyaltyTransaction, etc.

## 🧪 Testing

### Create Test Businesses

```python
python manage.py shell

from pos.models import Business, BusinessMembership
from django.contrib.auth.models import User

# Create user
user = User.objects.create_user(
    username='testuser',
    email='test@example.com',
    password='testpass123'
)

# Create business
business = Business.objects.create(
    name='Test Shop',
    slug='test-shop',
    owner=user
)

# Create membership
BusinessMembership.objects.create(
    user=user,
    business=business,
    role='owner'
)
```

### Test Registration Flow

1. Visit `/register/`
2. Create new business
3. Verify redirect to `/b/{slug}/setup/`
4. Complete business setup
5. Access dashboard at `/b/{slug}/`

## 🔄 Migration Path

### For Existing Single-Tenant Installation

1. **Backup your database**
   ```bash
   python manage.py dumpdata > backup.json
   ```

2. **Run migrations**
   ```bash
   python manage.py migrate
   ```
   
   This automatically:
   - Creates default business
   - Assigns all existing data to default business
   - Creates owner membership

3. **Verify data**
   ```bash
   python manage.py shell
   from pos.models import Business, Product
   
   business = Business.objects.first()
   print(f"Business: {business.name}")
   print(f"Products: {Product.objects.filter(business=business).count()}")
   ```

4. **Update your views** (gradually)
   - Start with critical views (POS, products)
   - Add `@business_required` decorator
   - Filter querysets by `request.business`

## 🌐 Domain Configuration

### Option 1: Path-Based (Current)
```
https://yourapp.com/b/shop-a/
https://yourapp.com/b/shop-b/
```

### Option 2: Subdomain-Based (Future)
```
https://shop-a.yourapp.com/
https://shop-b.yourapp.com/
```

To enable subdomains, update `TenantMiddleware` to extract business from subdomain instead of path.

## 💰 Monetization Ready

The system includes subscription infrastructure:

```python
class Business(models.Model):
    subscription_plan = models.CharField(
        choices=[
            ('free', 'Free'),
            ('basic', 'Basic'),
            ('professional', 'Professional'),
            ('enterprise', 'Enterprise'),
        ]
    )
    is_trial = models.BooleanField(default=True)
    trial_ends_at = models.DateTimeField()
```

### Next Steps for Billing:
1. Integrate Stripe/PayPal
2. Create subscription management views
3. Add payment gateway
4. Implement plan limits
5. Add billing history

## 📝 Important Notes

### Data Isolation
- All queries MUST filter by business
- Use decorators to enforce business context
- Never expose cross-business data

### Performance
- Add database indexes: `(business_id, field_name)`
- Use `select_related('business')` in queries
- Cache business settings per request

### Security
- Always verify user has access to business
- Check business membership before operations
- Log all cross-business access attempts

## 🆘 Troubleshooting

### "Business not found" Error
- Check URL has correct slug: `/b/{slug}/`
- Verify business is active
- Ensure user has membership

### "No business context" Error
- Add `@business_required` decorator
- Check middleware is enabled
- Verify URL pattern includes slug

### Data Not Showing
- Ensure queryset filters by business
- Check business membership is active
- Verify migrations ran successfully

## 📚 Additional Resources

- **Migration File**: `pos/migrations/0002_multi_tenancy.py`
- **Middleware**: `pos/middleware.py` (TenantMiddleware)
- **Decorators**: `pos/decorators.py`
- **Views**: `pos/tenant_views.py`
- **URLs**: `pos/urls_multitenant.py`

## 🎉 You're Ready!

Your POS system is now market-ready as a multi-tenant SaaS application. Users can:
1. Register their business
2. Invite team members
3. Manage their own data
4. Operate independently

Share your URL and let businesses sign up! 🚀
