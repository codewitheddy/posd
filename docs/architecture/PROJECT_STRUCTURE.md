# Project Structure

Complete overview of the POS system architecture and file organization.

## Directory Tree

```
pos_system/
├── pos/                              # Main POS application
│   ├── migrations/                   # Database migrations
│   │   └── 0001_initial.py          # Initial models migration
│   ├── management/                   # Custom management commands
│   │   └── commands/
│   │       ├── seed_data.py         # Sample data seeder
│   │       └── reset_admin.py       # Admin password reset
│   ├── templates/pos/                # HTML templates
│   │   ├── base.html                # Base template with navbar
│   │   ├── dashboard.html           # Main dashboard
│   │   ├── pos_screen.html          # POS sales interface
│   │   ├── invoice.html             # Invoice display
│   │   ├── product_list.html        # Product listing
│   │   ├── product_form.html        # Product create/edit
│   │   ├── product_confirm_delete.html
│   │   ├── category_list.html       # Category listing
│   │   ├── category_form.html       # Category create
│   │   └── sales_report.html        # Daily sales report
│   ├── __init__.py
│   ├── admin.py                      # Django admin configuration
│   ├── apps.py                       # App configuration
│   ├── models.py                     # Database models
│   ├── urls.py                       # URL routing
│   ├── views.py                      # Business logic & views
│   └── tests.py                      # Unit tests (placeholder)
│
├── pos_system/                       # Project configuration
│   ├── __init__.py
│   ├── asgi.py                       # ASGI configuration
│   ├── settings.py                   # Django settings
│   ├── urls.py                       # Main URL configuration
│   └── wsgi.py                       # WSGI configuration
│
├── manage.py                         # Django management script
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment variables template
├── .gitignore                        # Git ignore rules
├── setup.bat                         # Windows setup script
├── setup.sh                          # Linux/Mac setup script
├── README.md                         # Main documentation
├── QUICKSTART.md                     # Quick start guide
├── DEPLOYMENT.md                     # Deployment guide
└── PROJECT_STRUCTURE.md              # This file
```

## Core Components

### Models (pos/models.py)

#### Category
```python
- id: AutoField (Primary Key)
- name: CharField(100) [Unique]
- created_at: DateTimeField
```

#### Product
```python
- id: AutoField (Primary Key)
- name: CharField(200)
- category: ForeignKey(Category) [Nullable]
- unit_price: DecimalField(10, 2)
- created_at: DateTimeField
- updated_at: DateTimeField
```

#### Sale
```python
- id: AutoField (Primary Key)
- invoice_number: CharField(20) [Unique, Auto-generated]
- date: DateTimeField
- subtotal: DecimalField(10, 2)
- vat_rate: DecimalField(5, 2)
- vat_amount: DecimalField(10, 2)
- discount_type: CharField(10) [percentage/fixed]
- discount_value: DecimalField(10, 2)
- discount_amount: DecimalField(10, 2)
- total: DecimalField(10, 2)
- created_at: DateTimeField
```

#### SaleItem
```python
- id: AutoField (Primary Key)
- sale: ForeignKey(Sale)
- product: ForeignKey(Product)
- quantity: PositiveIntegerField
- unit_price: DecimalField(10, 2)
- total_price: DecimalField(10, 2)
```

### Views (pos/views.py)

| View | URL | Method | Description |
|------|-----|--------|-------------|
| dashboard | / | GET | Main dashboard with stats |
| product_list | /products/ | GET | List all products |
| product_create | /products/create/ | GET/POST | Create new product |
| product_edit | /products/<id>/edit/ | GET/POST | Edit product |
| product_delete | /products/<id>/delete/ | GET/POST | Delete product |
| category_list | /categories/ | GET | List all categories |
| category_create | /categories/create/ | GET/POST | Create category |
| pos_screen | /pos/ | GET | POS sales interface |
| complete_sale | /pos/complete/ | POST | Process sale |
| invoice_view | /invoice/<id>/ | GET | View invoice |
| invoice_pdf | /invoice/<id>/pdf/ | GET | Download PDF |
| sales_report | /reports/sales/ | GET | Daily sales report |

### Templates

#### Base Template (base.html)
- Bootstrap 5 navbar
- Message display system
- Responsive layout
- Common CSS/JS includes

#### Dashboard (dashboard.html)
- Quick stats cards
- Today's sales summary
- Quick action buttons

#### POS Screen (pos_screen.html)
- Product grid with search/filter
- Shopping cart with live updates
- Discount calculator
- VAT calculation
- Complete sale button

#### Invoice (invoice.html)
- Shop header
- Invoice details
- Item list table
- Totals breakdown
- Print/PDF buttons

#### Reports (sales_report.html)
- Date filter
- Summary cards
- Transaction table
- Invoice links

## Data Flow

### Making a Sale

```
1. User clicks products on POS screen
   ↓
2. JavaScript adds items to cart
   ↓
3. Cart calculates subtotal, discount, VAT, total
   ↓
4. User clicks "Complete Sale"
   ↓
5. Form submits to complete_sale view
   ↓
6. View creates Sale and SaleItem records
   ↓
7. Auto-generates invoice number
   ↓
8. Redirects to invoice view
   ↓
9. User can print/download PDF
```

### Invoice Number Generation

Format: `INV-YYYYMMDD-XXXX`

Example: `INV-20260206-0001`

Logic:
1. Get current date (YYYYMMDD)
2. Find last invoice for today
3. Increment counter (XXXX)
4. Generate unique invoice number

### VAT Calculation

```
Subtotal = Sum of (quantity × unit_price)
Discount = Subtotal × (discount_value / 100)  [if percentage]
         OR discount_value                     [if fixed]
After Discount = Subtotal - Discount
VAT = After Discount × (vat_rate / 100)
Total = After Discount + VAT
```

## Configuration

### Settings (pos_system/settings.py)

Key configurations:
```python
# POS specific
VAT_RATE = 16              # Kenya VAT rate
SHOP_NAME = 'My Retail Shop'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Timezone
TIME_ZONE = 'Africa/Nairobi'

# Installed apps
INSTALLED_APPS = [
    ...
    'pos',  # POS application
]
```

### URL Configuration

```python
# pos_system/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('pos.urls')),  # All POS routes
]

# pos/urls.py
urlpatterns = [
    path('', views.dashboard),
    path('products/', ...),
    path('pos/', ...),
    path('reports/', ...),
]
```

## Dependencies

### Python Packages (requirements.txt)

```
Django>=5.0,<5.1          # Web framework
psycopg2-binary>=2.9.9    # PostgreSQL adapter
reportlab>=4.0.0          # PDF generation
python-decouple>=3.8      # Environment variables
```

### Frontend Libraries (CDN)

```
Bootstrap 5.3.0           # UI framework
Bootstrap Icons 1.11.0    # Icon library
```

## Database Schema

```sql
-- Categories
CREATE TABLE pos_category (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) UNIQUE,
    created_at DATETIME
);

-- Products
CREATE TABLE pos_product (
    id INTEGER PRIMARY KEY,
    name VARCHAR(200),
    category_id INTEGER REFERENCES pos_category(id),
    unit_price DECIMAL(10, 2),
    created_at DATETIME,
    updated_at DATETIME
);

-- Sales
CREATE TABLE pos_sale (
    id INTEGER PRIMARY KEY,
    invoice_number VARCHAR(20) UNIQUE,
    date DATETIME,
    subtotal DECIMAL(10, 2),
    vat_rate DECIMAL(5, 2),
    vat_amount DECIMAL(10, 2),
    discount_type VARCHAR(10),
    discount_value DECIMAL(10, 2),
    discount_amount DECIMAL(10, 2),
    total DECIMAL(10, 2),
    created_at DATETIME
);

-- Sale Items
CREATE TABLE pos_saleitem (
    id INTEGER PRIMARY KEY,
    sale_id INTEGER REFERENCES pos_sale(id),
    product_id INTEGER REFERENCES pos_product(id),
    quantity INTEGER,
    unit_price DECIMAL(10, 2),
    total_price DECIMAL(10, 2)
);
```

## Extension Points

### Easy to Add

1. **Stock Management**
   - Add `stock_quantity` field to Product
   - Deduct stock on sale
   - Low stock alerts

2. **User Authentication**
   - Add User foreign key to Sale
   - Track who made each sale
   - User-specific reports

3. **Customer Management**
   - Create Customer model
   - Link sales to customers
   - Customer purchase history

4. **M-PESA Integration**
   - Add payment_method field
   - Integrate Daraja API
   - Track payment status

5. **Barcode Support**
   - Add barcode field to Product
   - Implement barcode scanner
   - Quick product lookup

6. **Multi-store**
   - Create Store model
   - Link products and sales to stores
   - Store-specific reports

## Best Practices

### Code Organization
- Models: Data structure only
- Views: Business logic
- Templates: Presentation
- Static files: CSS/JS/Images

### Security
- CSRF protection enabled
- SQL injection prevention (ORM)
- XSS protection (template escaping)
- Admin panel authentication

### Performance
- Database indexes on foreign keys
- Select_related for joins
- Prefetch_related for reverse relations
- Minimal queries per page

### Maintainability
- Clear naming conventions
- Comprehensive comments
- Modular design
- Easy to extend

---

**Last Updated**: February 2026
