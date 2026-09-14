# VAT Code Module - Real-World Usage Scenarios

## Scenario 1: Grocery Retail Store (Kenya)

### Business Context
A grocery store in Nairobi selling various food items with different tax treatments.

### VAT Code Setup

#### 1. Basic Foodstuffs (Zero-Rated)
```json
{
  "code": "FOOD-BASIC",
  "name": "Basic Foodstuffs (0%)",
  "vat_rate": 0.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "hs_code_chapter": "04",
  "description": "Unprocessed food items - maize, beans, wheat flour",
  "is_active": true
}
```

**Products:** Maize, beans, rice, wheat flour, salt, sugar

#### 2. Processed Foods (Standard Rate)
```json
{
  "code": "FOOD-PROCESSED",
  "name": "Processed Foods (16%)",
  "vat_rate": 16.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "hs_code_chapter": "19",
  "description": "Processed and packaged food items",
  "is_active": true
}
```

**Products:** Bread, biscuits, canned goods, milk powder

#### 3. Beverages (Excisable)
```json
{
  "code": "BVGE-EXCISE",
  "name": "Beverages with Excise (36%)",
  "vat_rate": 16.00,
  "excise_rate": 20.00,
  "import_duty": 0.00,
  "is_excisable": true,
  "hs_code_chapter": "22",
  "description": "Alcoholic and sugary beverages subject to excise",
  "is_active": true
}
```

**Products:** Beer, soda, wine, spirits

#### 4. Vegetables & Fruits (Zero-Rated)
```json
{
  "code": "PRODUCE-ZERO",
  "name": "Fresh Produce (0%)",
  "vat_rate": 0.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "hs_code_chapter": "07",
  "description": "Fresh vegetables and fruits",
  "is_active": true
}
```

**Products:** Tomatoes, onions, potatoes, bananas, mangoes

### Sales Transaction Example

**Customer Purchase:**
1. Maize (10kg @ 50 KES) - Zero-Rated → 500 KES (0% tax)
2. Bread (1 loaf @ 60 KES) - Processed → 60 KES + 9.6 KES VAT = 69.6 KES
3. Beer (6-pack @ 300 KES) - Excisable → 300 KES + 108 KES tax = 408 KES

**Receipt:**
```
=== GROCERY STORE ===
Date: 2026-08-11 14:30

Item                  Qty    Rate      Total    Tax      Total+Tax
Maize (10kg)          1      500.00    500.00   0%       500.00
Bread                 1      60.00     60.00    16%      69.60
Beer 6-Pack           1      300.00    300.00   36%      408.00

                                Subtotal: 860.00
                               Total Tax: 117.60
                                  TOTAL: 977.60

Tax Breakdown:
  VAT (16%):    60.00
  VAT (0%):     0.00
  Excise (20%): 60.00
  Duty (0%):    0.00
```

---

## Scenario 2: Pharmacy/Chemist (Kenya)

### Business Context
A pharmacy selling medicines and health products with varying tax treatments.

### VAT Code Setup

#### 1. Essential Medicines (Exempt)
```json
{
  "code": "MED-EXEMPT",
  "name": "Essential Medicines (0%)",
  "vat_rate": 0.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "hs_code_chapter": "30",
  "description": "Essential medicines exempt from VAT",
  "is_active": true
}
```

**Products:** Antibiotics, painkillers, insulin, antiretrovirals

#### 2. Over-the-Counter Drugs (Standard Rate)
```json
{
  "code": "OTC-STANDARD",
  "name": "OTC Medicines (16%)",
  "vat_rate": 16.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "hs_code_chapter": "30",
  "description": "Over-the-counter non-essential medicines",
  "is_active": true
}
```

**Products:** Vitamins, supplements, cough syrup

#### 3. Medical Devices (Standard Rate)
```json
{
  "code": "DEVICE-STD",
  "name": "Medical Devices (16%)",
  "vat_rate": 16.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "hs_code_chapter": "90",
  "description": "Bandages, syringes, thermometers, etc.",
  "is_active": true
}
```

**Products:** Bandages, syringes, thermometers, glucometers

### API Usage Example

**Creating Essential Medicines VAT Code:**
```bash
curl -X POST http://localhost:8000/api/vat-codes/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "MED-EXEMPT",
    "name": "Essential Medicines (0%)",
    "vat_rate": 0.00,
    "description": "Essential medicines exempt from VAT",
    "is_active": true
  }'
```

**Assigning to Product:**
```bash
curl -X PATCH http://localhost:8000/api/products/123/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "vat_code": 1
  }'
```

**Getting All Medicines with 0% Tax:**
```bash
curl http://localhost:8000/api/vat-codes/by_rate/?rate=0.00 \
  -H "Authorization: Bearer <TOKEN>"
```

---

## Scenario 3: Liquor Store (Kenya)

### Business Context
A bottle store selling various alcoholic beverages with strict excise regulations.

### VAT Code Setup

#### 1. Beer & Spirits (High Excise)
```json
{
  "code": "ALCOHOL-HIGH",
  "name": "Alcohol - High Excise (36%)",
  "vat_rate": 16.00,
  "excise_rate": 20.00,
  "import_duty": 0.00,
  "is_excisable": true,
  "hs_code_chapter": "22",
  "description": "Beer, spirits, whiskey - subject to 20% excise",
  "is_active": true
}
```

#### 2. Wine (Standard Excise)
```json
{
  "code": "ALCOHOL-WINE",
  "name": "Wine - Standard Excise (20%)",
  "vat_rate": 16.00,
  "excise_rate": 4.00,
  "import_duty": 0.00,
  "is_excisable": true,
  "hs_code_chapter": "22",
  "description": "Wine and fortified wines - lower excise rate",
  "is_active": true
}
```

#### 3. Non-Alcoholic (Standard)
```json
{
  "code": "BEVERAGE-NA",
  "name": "Non-Alcoholic Beverages (16%)",
  "vat_rate": 16.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "hs_code_chapter": "22",
  "description": "Soft drinks, juices (some subject to excise)",
  "is_active": true
}
```

### Compliance Tracking

**Monthly Excise Report:**
```python
from django.db.models import Sum, F
from decimal import Decimal

# Get all excisable sales this month
excisable_vat_codes = VATCode.objects.filter(
    is_excisable=True,
    business=my_business
)

for code in excisable_vat_codes:
    sales = Sale.objects.filter(
        saleitem__product__vat_code=code,
        date__month=8,
        date__year=2026
    )
    
    total_excise = sales.aggregate(
        total_excise=Sum(
            F('saleitem__quantity') * 
            F('saleitem__product__vat_code__excise_rate')
        )
    )
    
    print(f"{code.name}: {total_excise['total_excise']} KES excise")
```

---

## Scenario 4: Restaurant (Kenya)

### Business Context
A restaurant with different tax treatments for dine-in, takeaway, and catering.

### VAT Code Setup

#### 1. Food Service (Standard)
```json
{
  "code": "REST-FOOD",
  "name": "Restaurant Food (16%)",
  "vat_rate": 16.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "description": "Prepared food - dine in or takeaway",
  "is_active": true
}
```

#### 2. Alcoholic Beverages (Excisable)
```json
{
  "code": "REST-ALCOHOL",
  "name": "Alcohol - Excisable (36%)",
  "vat_rate": 16.00,
  "excise_rate": 20.00,
  "import_duty": 0.00,
  "is_excisable": true,
  "description": "Beer, wine, spirits - subject to excise",
  "is_active": true
}
```

#### 3. Soft Drinks (Standard)
```json
{
  "code": "REST-BEVERAGE",
  "name": "Beverages - Non-Alcoholic (16%)",
  "vat_rate": 16.00,
  "excise_rate": 0.00,
  "import_duty": 0.00,
  "is_excisable": false,
  "description": "Soft drinks, juices, water",
  "is_active": true
}
```

### Sample Receipt

**Customer: Table 5**
```
=== RESTAURANT NAME ===
Date: 2026-08-11 19:45

Item                          Qty    Price     Tax%    Total+Tax
Ugali & Sukuma Wiki           2      200.00    16%     464.00
Nyama Choma (250g)            1      400.00    16%     464.00
Beers - Tusker                2      150.00    36%     408.00
Sodas - Fanta                 2      80.00     16%     185.60

                                    Subtotal: 830.00
                                  Total Tax: 222.60
                                     TOTAL: 1,052.60

Service Charge (10%):                  105.26
FINAL TOTAL:                         1,157.86

Tax Breakdown:
  VAT (16%):    113.60
  Excise (20%):  60.00
```

---

## Scenario 5: E-Commerce Platform (Multiple Businesses)

### Multi-Tenancy Example

**Business A - Electronics Store:**
```json
{
  "business": "Electronics Store",
  "vat_codes": [
    {"code": "ELEC-STD", "name": "Electronics (16%)", "rate": 16.00},
    {"code": "ELEC-REDUCED", "name": "Accessories (14%)", "rate": 14.00}
  ]
}
```

**Business B - Fashion Store:**
```json
{
  "business": "Fashion Store",
  "vat_codes": [
    {"code": "FASH-STD", "name": "Clothing (16%)", "rate": 16.00},
    {"code": "FASH-ZERO", "name": "Uniforms (0%)", "rate": 0.00}
  ]
}
```

**Business C - Pharmacy:**
```json
{
  "business": "Pharmacy Chain",
  "vat_codes": [
    {"code": "MED-EXEMPT", "name": "Medicines (0%)", "rate": 0.00},
    {"code": "MED-STD", "name": "Supplements (16%)", "rate": 16.00}
  ]
}
```

### API Query to Get Business-Specific VAT Codes

```bash
# Only returns VAT codes for current business (via JWT token)
curl http://localhost:8000/api/vat-codes/ \
  -H "Authorization: Bearer <BUSINESS_A_TOKEN>"

# Response only includes Business A's VAT codes
# Other businesses' codes are automatically filtered out
```

---

## Scenario 6: Quarter-End Tax Compliance Report

### Generating Tax Report

```python
from django.db.models import Sum, F, Q
from decimal import Decimal
from datetime import date

business = Business.objects.get(slug='my-grocery')

# Generate quarterly VAT report
start_date = date(2026, 7, 1)
end_date = date(2026, 9, 30)

vat_report = {}

# Get all VAT codes
vat_codes = business.vat_codes.filter(is_active=True)

for code in vat_codes:
    sales = Sale.objects.filter(
        business=business,
        date__date__gte=start_date,
        date__date__lte=end_date,
        saleitem__product__vat_code=code
    )
    
    total_revenue = sales.aggregate(
        total=Sum('total')
    )['total'] or 0
    
    total_vat = sales.aggregate(
        total=Sum('vat_amount')
    )['total'] or 0
    
    vat_report[code.code] = {
        'name': code.name,
        'rate': code.vat_rate,
        'revenue': total_revenue,
        'vat_collected': total_vat
    }

# Print report
print("=== QUARTERLY VAT REPORT ===")
print(f"Period: {start_date} to {end_date}\n")

total_revenue = 0
total_vat = 0

for code, data in vat_report.items():
    print(f"{code}: {data['name']}")
    print(f"  Revenue: {data['revenue']:,.2f} KES")
    print(f"  VAT ({data['rate']}%): {data['vat_collected']:,.2f} KES")
    print()
    
    total_revenue += data['revenue']
    total_vat += data['vat_collected']

print(f"TOTAL REVENUE: {total_revenue:,.2f} KES")
print(f"TOTAL VAT: {total_vat:,.2f} KES")
```

---

## Scenario 7: Product Category Migration

### Migrating Existing Products to VAT Codes

```python
from pos.models import Product, VATCode

# Before: Products using tax_class field
products = Product.objects.filter(
    business=my_business,
    vat_code__isnull=True  # No VAT code assigned yet
)

# Create VAT codes based on tax_class
vat_standard = VATCode.objects.get(
    business=my_business,
    code='VAT-STD'
)

vat_zero = VATCode.objects.get(
    business=my_business,
    code='VAT-ZERO'
)

# Migrate products
for product in products:
    if product.tax_class == 'standard':
        product.vat_code = vat_standard
    elif product.tax_class in ['zero_rated', 'exempt']:
        product.vat_code = vat_zero
    
    product.save()

print(f"Migrated {products.count()} products to VAT codes")
```

---

## Success Metrics

### For Grocery Store
- ✅ Tax calculations accurate to KES 0.00
- ✅ Excisable products correctly identified
- ✅ Zero-rated items properly handled
- ✅ Tax reports match KRA requirements
- ✅ Customer confusion about charges reduced

### For Pharmacy
- ✅ Essential medicines flagged as exempt
- ✅ Compliance with health sector regulations
- ✅ Pricing clearly displayed to customers
- ✅ Audit trail for regulatory inspection
- ✅ Bulk pricing easier to manage

### For Restaurant
- ✅ Excisable beverages properly taxed
- ✅ Food service VAT correctly applied
- ✅ Multi-currency support if needed
- ✅ Receipt clarity for customers
- ✅ Simplified reconciliation process

---

**Module:** VAT Code Management System
**Version:** 1.0
**Last Updated:** August 11, 2026
