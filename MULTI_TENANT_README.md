# 🏢 Multi-Tenant POS System

## Transform Your POS into a SaaS Platform

Your POS system is now a **fully multi-tenant SaaS application** where multiple businesses can register, operate independently, and manage their own data with complete isolation.

## ✨ What's New?

### For Business Owners
- 🎯 **Self-Service Registration** - Create your business account in minutes
- 👥 **Team Management** - Invite staff with role-based access
- 🔒 **Data Privacy** - Your data is completely isolated from other businesses
- 📊 **Independent Operations** - Manage your business without interference
- 💰 **Free Trial** - 30 days to explore all features
- 🚀 **Instant Setup** - No technical knowledge required

### For Developers
- 🏗️ **Clean Architecture** - Business model with proper relationships
- 🔐 **Automatic Isolation** - Middleware handles tenant detection
- 🎨 **Decorator-Based** - Simple decorators for business context
- 📝 **Well Documented** - Comprehensive guides and examples
- 🧪 **Test Ready** - Easy to test with multiple tenants
- ⚡ **Performance Optimized** - Efficient queries with proper indexing

## 🚀 Quick Start

### For End Users

#### 1. Register Your Business
Visit: `https://your-domain.com/register/`

Fill in:
- Business name
- Your name
- Email address
- Password

Click "Create My Business" and you're done!

#### 2. Access Your Dashboard
After registration, you'll be at: `/b/your-business-slug/`

This is your unique business URL. Bookmark it!

#### 3. Invite Your Team
1. Go to Settings → Team Members
2. Enter team member's email
3. Select their role (Manager, Cashier, etc.)
4. They'll get access to your business

### For Developers

#### 1. Install & Migrate
```bash
cd posd
python manage.py makemigrations
python manage.py migrate
python manage.py setup_multitenant
```

#### 2. Update Your Views
```python
from pos.decorators import business_required

@business_required
def my_view(request):
    # request.business is automatically available
    products = Product.objects.filter(business=request.business)
    return render(request, 'template.html', {'products': products})
```

#### 3. Update Templates
```django
<a href="{% url 'product_list' slug=request.business.slug %}">Products</a>
```

## 📋 Features

### Business Management
- ✅ Self-service registration with email verification
- ✅ Business profile with logo, address, contact info
- ✅ Custom business slug for branded URLs
- ✅ Business settings and preferences
- ✅ Trial period management
- ✅ Subscription plan selection

### Team Collaboration
- ✅ Invite unlimited team members
- ✅ 7 role levels (Owner, Admin, Manager, etc.)
- ✅ Granular permissions per role
- ✅ Active/inactive member management
- ✅ Role-based dashboard views
- ✅ Activity logging per user

### Data Isolation
- ✅ Complete database-level separation
- ✅ No cross-business data leakage
- ✅ Business-specific reports
- ✅ Independent inventory
- ✅ Separate customer databases
- ✅ Isolated sales records

### Security
- ✅ Business ownership verification
- ✅ Membership-based access control
- ✅ Permission checks on every request
- ✅ Audit trail per business
- ✅ Secure business switching
- ✅ Cross-tenant access prevention

## 🎯 Use Cases

### 1. SaaS Platform
Launch a POS platform where businesses can sign up and start selling immediately.

**Example**: "CloudPOS - Your Business, Your Way"
- Businesses register at yourapp.com/register
- Each gets their own space: yourapp.com/b/their-shop
- You manage the platform, they manage their business

### 2. Franchise Management
Manage multiple franchise locations with centralized oversight.

**Example**: "Coffee Chain with 50 Locations"
- Each location is a separate business
- Franchisees manage their own staff
- Corporate can view all locations (superuser)

### 3. Multi-Store Retail
Run multiple stores under one account with separate operations.

**Example**: "Retail Group with 3 Brands"
- Electronics Store: /b/tech-world
- Clothing Store: /b/fashion-hub
- Grocery Store: /b/fresh-mart

### 4. White-Label Solution
Offer branded POS systems to different clients.

**Example**: "POS Provider for Small Businesses"
- Client A: clienta.yourapp.com
- Client B: clientb.yourapp.com
- Each thinks it's their own system

## 🔐 Security Model

### Access Levels

```
Superuser (Platform Admin)
    └── Can access all businesses
    └── Manages platform settings

Business Owner
    └── Full control of their business
    └── Cannot access other businesses
    └── Can invite/remove members

Business Admin
    └── Almost full control
    └── Cannot transfer ownership
    └── Can manage team

Manager
    └── Operations & reports
    └── Can manage inventory
    └── Can view analytics

Cashier/Sales
    └── POS operations only
    └── Limited reporting
    └── No settings access

Viewer
    └── Read-only access
    └── Can view reports
    └── Cannot modify data
```

### Data Isolation

Every query is automatically filtered:
```python
# Before (Single Tenant)
products = Product.objects.all()

# After (Multi-Tenant)
products = Product.objects.filter(business=request.business)
```

The middleware ensures `request.business` is always set correctly.

## 📊 Database Schema

### Core Multi-Tenant Models

**Business**
```python
- id (PK)
- name
- slug (unique)
- owner (FK to User)
- address, phone, email
- is_active
- subscription_plan
- trial_ends_at
```

**BusinessMembership**
```python
- id (PK)
- user (FK to User)
- business (FK to Business)
- role (owner/admin/manager/etc.)
- is_active
- joined_at
```

### Modified Models

All data models now include:
```python
business = ForeignKey(Business, on_delete=CASCADE)
```

This includes:
- Products, Categories
- Sales, Customers
- Suppliers, Purchases
- Inventory, Stock
- Reports, Analytics
- Everything!

## 🌐 URL Structure

### Public URLs (No Business Context)
```
/register/          - New business registration
/login/             - User login
/logout/            - User logout
/businesses/        - Business selection
```

### Business URLs (Require Business Context)
```
/b/{slug}/                  - Dashboard
/b/{slug}/products/         - Product management
/b/{slug}/pos/              - Point of sale
/b/{slug}/reports/sales/    - Sales reports
/b/{slug}/settings/         - Business settings
/b/{slug}/members/          - Team management
```

### API URLs
```
/api/v1/auth/token/                     - Get JWT token
/api/v1/products/?business={slug}       - List products
/api/v1/sales/?business={slug}          - List sales
```

## 💰 Monetization

### Built-in Subscription Support

```python
class Business(models.Model):
    subscription_plan = models.CharField(
        choices=[
            ('free', 'Free'),           # Limited features
            ('basic', 'Basic'),         # $29/month
            ('professional', 'Professional'),  # $79/month
            ('enterprise', 'Enterprise'),      # $199/month
        ]
    )
    is_trial = models.BooleanField(default=True)
    trial_ends_at = models.DateTimeField()
```

### Ready for Integration

- Stripe
- PayPal
- Paddle
- Chargebee
- Custom billing

### Plan Limits (Example)

| Feature | Free | Basic | Pro | Enterprise |
|---------|------|-------|-----|------------|
| Products | 100 | 1,000 | 10,000 | Unlimited |
| Users | 2 | 5 | 20 | Unlimited |
| Locations | 1 | 1 | 5 | Unlimited |
| Support | Email | Email | Priority | Dedicated |

## 📈 Scaling

### Performance Optimization

1. **Database Indexing**
   ```python
   class Meta:
       indexes = [
           models.Index(fields=['business', 'created_at']),
           models.Index(fields=['business', 'name']),
       ]
   ```

2. **Query Optimization**
   ```python
   products = Product.objects.filter(
       business=request.business
   ).select_related('category', 'business')
   ```

3. **Caching**
   ```python
   from django.core.cache import cache
   
   business_settings = cache.get(f'business_settings_{business.id}')
   if not business_settings:
       business_settings = BusinessSettings.get_settings(business)
       cache.set(f'business_settings_{business.id}', business_settings, 3600)
   ```

### Horizontal Scaling

- Each business is independent
- Can shard by business_id
- Easy to distribute across servers
- No cross-business transactions

## 🧪 Testing

### Create Test Businesses

```python
from pos.models import Business, BusinessMembership
from django.contrib.auth.models import User

# Create users
user1 = User.objects.create_user('user1', 'user1@test.com', 'pass')
user2 = User.objects.create_user('user2', 'user2@test.com', 'pass')

# Create businesses
business1 = Business.objects.create(name='Shop A', slug='shop-a', owner=user1)
business2 = Business.objects.create(name='Shop B', slug='shop-b', owner=user2)

# Create memberships
BusinessMembership.objects.create(user=user1, business=business1, role='owner')
BusinessMembership.objects.create(user=user2, business=business2, role='owner')
```

### Test Data Isolation

```python
# Create products for each business
Product.objects.create(business=business1, name='Product A1')
Product.objects.create(business=business2, name='Product B1')

# Verify isolation
assert Product.objects.filter(business=business1).count() == 1
assert Product.objects.filter(business=business2).count() == 1
```

## 📚 Documentation

- **Setup Guide**: `MULTI_TENANT_SETUP_GUIDE.md`
- **Developer Reference**: `DEVELOPER_QUICK_REFERENCE.md`
- **Implementation Details**: `MULTI_TENANCY_IMPLEMENTATION.md`
- **API Documentation**: `/api/v1/docs/`

## 🆘 Support

### Common Issues

**Q: Can't access business after registration**
A: Check that you're using the correct URL: `/b/{your-slug}/`

**Q: Data from other businesses showing up**
A: Ensure all queries filter by `business=request.business`

**Q: Permission denied errors**
A: Verify user has active membership in the business

**Q: Migration errors**
A: Backup database first, then run migrations step by step

### Getting Help

1. Check documentation files
2. Review example code in `tenant_views.py`
3. Test with `setup_multitenant` command
4. Check middleware configuration

## 🎉 Success Stories

### Before Multi-Tenancy
- Single business only
- Manual setup for each client
- Separate deployments
- High maintenance cost

### After Multi-Tenancy
- Unlimited businesses
- Self-service registration
- Single deployment
- Scalable SaaS model

## 🚀 Next Steps

1. **Run migrations** to enable multi-tenancy
2. **Test registration** flow at `/register/`
3. **Update your views** with business decorators
4. **Configure billing** (optional)
5. **Launch your SaaS** platform!

## 📞 Ready to Launch?

Your POS system is now market-ready! Share your registration URL and let businesses sign up.

**Registration URL**: `https://your-domain.com/register/`

Welcome to the world of SaaS! 🎊
