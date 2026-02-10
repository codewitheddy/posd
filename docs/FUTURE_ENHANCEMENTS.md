# Future Enhancements Guide

Ideas and implementation guides for extending the POS system.

## 1. Stock/Inventory Management

### Implementation
Add stock tracking to products:

```python
# models.py
class Product(models.Model):
    # ... existing fields ...
    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=10)
    
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold
    
    def has_stock(self, quantity):
        return self.stock_quantity >= quantity
```

Update sale processing:
```python
# views.py - in complete_sale
for item in sale_items:
    product = item['product']
    if not product.has_stock(item['quantity']):
        messages.error(request, f'{product.name} is out of stock!')
        return redirect('pos_screen')
    product.stock_quantity -= item['quantity']
    product.save()
```

Add stock management views:
- Stock adjustment form
- Stock history log
- Low stock alerts dashboard
- Reorder reports

## 2. User Management & Permissions

### Implementation

```python
# models.py
from django.contrib.auth.models import User

class Sale(models.Model):
    # ... existing fields ...
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
```

Create user roles:
```python
# Create groups
from django.contrib.auth.models import Group, Permission

# Cashier: Can make sales only
cashier_group = Group.objects.create(name='Cashier')
cashier_group.permissions.add(
    Permission.objects.get(codename='add_sale'),
    Permission.objects.get(codename='view_product'),
)

# Manager: Full access
manager_group = Group.objects.create(name='Manager')
# Add all permissions
```

Add login requirement:
```python
# views.py
from django.contrib.auth.decorators import login_required, permission_required

@login_required
@permission_required('pos.add_sale')
def pos_screen(request):
    # ... existing code ...
```

## 3. M-PESA Integration

### Implementation

Install Daraja SDK:
```bash
pip install python-mpesa
```

Add payment fields:
```python
# models.py
class Sale(models.Model):
    # ... existing fields ...
    payment_method = models.CharField(
        max_length=20,
        choices=[('cash', 'Cash'), ('mpesa', 'M-PESA')],
        default='cash'
    )
    mpesa_receipt = models.CharField(max_length=50, blank=True)
    payment_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed')],
        default='completed'
    )
```

Implement M-PESA STK Push:
```python
# views.py
from mpesa import MpesaClient

def initiate_mpesa_payment(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    
    client = MpesaClient()
    phone = request.POST.get('phone')
    amount = int(sale.total)
    
    response = client.stk_push(
        phone_number=phone,
        amount=amount,
        account_reference=sale.invoice_number,
        transaction_desc=f'Payment for {sale.invoice_number}'
    )
    
    if response['ResponseCode'] == '0':
        sale.payment_status = 'pending'
        sale.save()
        # Poll for payment status
    
    return redirect('invoice_view', pk=sale.pk)
```

## 4. Customer Management

### Implementation

```python
# models.py
class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    loyalty_points = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} - {self.phone}"

class Sale(models.Model):
    # ... existing fields ...
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
```

Features to add:
- Customer registration form
- Customer search on POS screen
- Purchase history per customer
- Loyalty points system
- SMS notifications for promotions

## 5. Barcode Support

### Implementation

Install barcode library:
```bash
pip install python-barcode pillow
```

Add barcode field:
```python
# models.py
class Product(models.Model):
    # ... existing fields ...
    barcode = models.CharField(max_length=50, unique=True, blank=True)
    
    def generate_barcode(self):
        if not self.barcode:
            # Generate EAN13 barcode
            from barcode import EAN13
            from barcode.writer import ImageWriter
            
            code = EAN13(str(self.id).zfill(12), writer=ImageWriter())
            self.barcode = str(self.id).zfill(12)
            self.save()
```

Add barcode scanner to POS:
```javascript
// pos_screen.html
let barcodeBuffer = '';

document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        // Search product by barcode
        fetch(`/api/product/barcode/${barcodeBuffer}/`)
            .then(r => r.json())
            .then(product => addToCart(product.id, product.name, product.price));
        barcodeBuffer = '';
    } else {
        barcodeBuffer += e.key;
    }
});
```

## 6. Advanced Reporting

### Implementation

Add report types:
- Profit margin analysis
- Best-selling products
- Sales by category
- Hourly sales patterns
- Monthly/yearly comparisons
- Tax reports for KRA

```python
# views.py
def profit_report(request):
    products = Product.objects.annotate(
        total_sold=Sum('saleitem__quantity'),
        revenue=Sum('saleitem__total_price')
    ).order_by('-revenue')
    
    return render(request, 'pos/profit_report.html', {'products': products})
```

Add charts using Chart.js:
```html
<canvas id="salesChart"></canvas>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
new Chart(document.getElementById('salesChart'), {
    type: 'line',
    data: {
        labels: {{ dates|safe }},
        datasets: [{
            label: 'Daily Sales',
            data: {{ sales|safe }}
        }]
    }
});
</script>
```

## 7. Multi-Store Support

### Implementation

```python
# models.py
class Store(models.Model):
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return self.name

class Product(models.Model):
    # ... existing fields ...
    store = models.ForeignKey(Store, on_delete=models.CASCADE)

class Sale(models.Model):
    # ... existing fields ...
    store = models.ForeignKey(Store, on_delete=models.CASCADE)
```

Features:
- Store selection on login
- Store-specific inventory
- Inter-store transfers
- Consolidated reports across stores

## 8. REST API

### Implementation

Install Django REST Framework:
```bash
pip install djangorestframework
```

Create serializers:
```python
# serializers.py
from rest_framework import serializers

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Sale
        fields = '__all__'
```

Create API views:
```python
# api_views.py
from rest_framework import viewsets

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
```

Add API URLs:
```python
# urls.py
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('products', ProductViewSet)
router.register('sales', SaleViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]
```

## 9. Mobile App Integration

### Options

1. **Progressive Web App (PWA)**
   - Add service worker
   - Enable offline mode
   - Add to home screen

2. **React Native App**
   - Use REST API
   - Native mobile experience
   - Barcode scanner integration

3. **Flutter App**
   - Cross-platform
   - Fast performance
   - Beautiful UI

## 10. Advanced Features

### Email Receipts
```python
from django.core.mail import send_mail

def send_receipt_email(sale, customer_email):
    subject = f'Receipt - {sale.invoice_number}'
    message = f'Thank you for your purchase!\n\nTotal: KES {sale.total}'
    send_mail(subject, message, 'noreply@shop.com', [customer_email])
```

### SMS Notifications
```python
import requests

def send_sms(phone, message):
    # Using Africa's Talking API
    url = 'https://api.africastalking.com/version1/messaging'
    data = {
        'username': 'your_username',
        'to': phone,
        'message': message
    }
    requests.post(url, data=data)
```

### Promotions & Discounts
```python
class Promotion(models.Model):
    name = models.CharField(max_length=200)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    products = models.ManyToManyField(Product)
    
    def is_active(self):
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date
```

### Expense Tracking
```python
class Expense(models.Model):
    CATEGORIES = [
        ('rent', 'Rent'),
        ('utilities', 'Utilities'),
        ('supplies', 'Supplies'),
        ('salaries', 'Salaries'),
        ('other', 'Other'),
    ]
    
    category = models.CharField(max_length=20, choices=CATEGORIES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    date = models.DateField()
    receipt = models.FileField(upload_to='receipts/', blank=True)
```

## Implementation Priority

### Phase 1 (Essential)
1. Stock Management
2. User Authentication
3. Basic Reports

### Phase 2 (Important)
4. Customer Management
5. M-PESA Integration
6. Barcode Support

### Phase 3 (Nice to Have)
7. Multi-Store
8. REST API
9. Mobile App

### Phase 4 (Advanced)
10. Advanced Analytics
11. AI-powered insights
12. Integration with accounting software

## Testing Recommendations

```python
# tests.py
from django.test import TestCase

class ProductTestCase(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name='Test')
        self.product = Product.objects.create(
            name='Test Product',
            category=self.category,
            unit_price=100
        )
    
    def test_product_creation(self):
        self.assertEqual(self.product.name, 'Test Product')
        self.assertEqual(self.product.unit_price, 100)
    
    def test_stock_deduction(self):
        self.product.stock_quantity = 10
        self.product.stock_quantity -= 3
        self.assertEqual(self.product.stock_quantity, 7)
```

Run tests:
```bash
python manage.py test
```

## Performance Optimization

### Database Indexing
```python
class Product(models.Model):
    # ... fields ...
    
    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['category', 'name']),
        ]
```

### Caching
```python
from django.views.decorators.cache import cache_page

@cache_page(60 * 15)  # Cache for 15 minutes
def product_list(request):
    # ... view code ...
```

### Query Optimization
```python
# Bad: N+1 queries
products = Product.objects.all()
for product in products:
    print(product.category.name)  # Extra query per product

# Good: Single query with join
products = Product.objects.select_related('category').all()
for product in products:
    print(product.category.name)  # No extra query
```

---

**Remember**: Implement features incrementally. Test thoroughly before deploying to production.
