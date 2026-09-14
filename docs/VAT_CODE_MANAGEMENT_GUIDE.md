# VAT Code Management Module - Complete Guide

## Overview

The VAT Code Management Module provides a comprehensive system for managing tax treatment of products in the Marid POS system. It allows businesses to define custom VAT codes that control how products are taxed, including standard VAT, zero-rated products, exemptions, and special tax rates.

## Features

### 1. **Multi-Tenancy Support**
- Each business can define its own VAT codes
- VAT codes are isolated per business
- No cross-business data leakage

### 2. **Flexible Tax Configuration**
- Standard VAT Rate (typically 16%)
- Zero-Rated Products (0% VAT)
- Exempt Products (0% VAT)
- Custom Tax Rates (8%, 14%, 20%, etc.)
- Excise Duty Support
- Import Duty Support

### 3. **HS Code Integration**
- Link VAT codes to Harmonized System (HS) Code chapters
- Useful for product classification and regulatory compliance
- Kenya Revenue Authority (KRA) compliant

### 4. **Comprehensive API**
- RESTful API endpoints for CRUD operations
- Custom filtering by tax rate and excisable status
- Product listing by VAT code
- Full search and ordering capabilities

### 5. **Admin Interface**
- User-friendly Django admin dashboard
- Advanced filtering and search
- Organized fieldsets for configuration
- Audit trail with creation/update timestamps

---

## Data Model

### VATCode Model

The core `VATCode` model represents a unique tax treatment category.

**Key Fields:**

```python
class VATCode(models.Model):
    business              # ForeignKey to Business (multi-tenancy)
    code                  # Unique code identifier (e.g., "VAT-STD", "VAT-ZERO")
    name                  # Descriptive name (e.g., "Standard Rated (16%)")
    vat_rate              # VAT percentage (0.00 - 100.00)
    description           # Additional details about when to use
    hs_code_chapter       # HS Code chapter (optional, for classification)
    excise_rate           # Excise duty percentage (0.00 - 100.00)
    is_excisable          # Boolean: subject to excise duty?
    import_duty           # Import duty percentage (0.00 - 100.00)
    is_active             # Boolean: can be assigned to new products?
    created_at            # Audit timestamp
    updated_at            # Audit timestamp
```

### Product Model Updates

Products now include a link to VATCode:

```python
class Product(models.Model):
    ...
    vat_code = ForeignKey('VATCode', null=True, blank=True)
    # If vat_code is not set, uses tax_class field for backward compatibility
    ...
```

---

## API Reference

### Base URL
```
/api/vat-codes/
```

### Endpoints

#### 1. **List All VAT Codes**
```http
GET /api/vat-codes/
```

**Query Parameters:**
- `search` - Search by code, name, or description
- `ordering` - Order by: `code`, `vat_rate`, `created_at`
- `active` - Filter by status: `true` or `false`

**Example:**
```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/vat-codes/?search=standard&active=true"
```

**Response:**
```json
[
  {
    "id": 1,
    "code": "VAT-STD",
    "name": "Standard Rated (16%)",
    "vat_rate": "16.00",
    "excise_rate": "0.00",
    "import_duty": "0.00",
    "total_tax_rate": 16.0,
    "is_excisable": false,
    "hs_code_chapter": null,
    "description": "Standard VAT rate for regular products",
    "is_active": true,
    "product_count": 45,
    "business_name": "My Business",
    "created_at": "2026-08-11T10:30:00Z",
    "updated_at": "2026-08-11T10:30:00Z"
  }
]
```

#### 2. **Create VAT Code**
```http
POST /api/vat-codes/
```

**Request Body:**
```json
{
  "code": "VAT-ZERO",
  "name": "Zero Rated (0%)",
  "vat_rate": "0.00",
  "excise_rate": "0.00",
  "import_duty": "0.00",
  "is_excisable": false,
  "hs_code_chapter": "04",
  "description": "Zero-rated products like unprocessed foods",
  "is_active": true
}
```

**Response:** Returns the created VAT code object (HTTP 201)

#### 3. **Retrieve Specific VAT Code**
```http
GET /api/vat-codes/{id}/
```

**Response:** Returns VAT code details

#### 4. **Update VAT Code**
```http
PUT /api/vat-codes/{id}/
PATCH /api/vat-codes/{id}/
```

**Request Body:** Same as create (PUT) or partial fields (PATCH)

#### 5. **Delete VAT Code**
```http
DELETE /api/vat-codes/{id}/
```

**Note:** A VAT code can only be deleted if no products are using it.

---

### Custom Actions

#### 6. **Filter by Tax Rate**
```http
GET /api/vat-codes/by_rate/?rate=16.00
```

**Response:** Returns all VAT codes with the specified rate

**Example:**
```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/vat-codes/by_rate/?rate=0.00"
```

#### 7. **Get Excisable VAT Codes**
```http
GET /api/vat-codes/excisable/
```

**Response:** Returns only VAT codes marked as excisable

**Example:**
```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/vat-codes/excisable/"
```

#### 8. **Get Products by VAT Code**
```http
GET /api/vat-codes/{id}/products/
```

**Response:** Returns all active products using this VAT code

**Example:**
```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/vat-codes/1/products/"
```

---

## Admin Interface Usage

### Accessing VAT Codes Admin

1. Go to Django Admin: `http://localhost:8000/admin/`
2. Navigate to **POS > VAT Codes**

### Managing VAT Codes

#### Create New VAT Code

1. Click **"Add VAT Code"** button
2. Fill in the form:
   - **Code** - Unique identifier (e.g., "VAT-STD")
   - **Name** - Display name (e.g., "Standard Rated (16%)")
   - **VAT Rate** - Percentage (0-100)
   - **Excise Rate** - Additional excise percentage (0-100)
   - **Import Duty** - Additional import duty (0-100)
   - **Is Excisable** - Check if subject to excise duty
   - **HS Code Chapter** - Optional classification (e.g., "09")
   - **Description** - When/where to use this code
   - **Is Active** - Deactivate to prevent new assignments

3. Click **"Save"**

#### Filter VAT Codes

Use the sidebar filters:
- **Active Status** - Show active/inactive codes
- **VAT Rate** - Filter by rate (0%, 8%, 14%, 16%, 20%)
- **Excisable** - Show excisable products only
- **Business** - Filter by business (multi-tenant)
- **Created At** - Filter by date range

#### Search VAT Codes

Use the search box to find by:
- Code (e.g., "VAT-STD")
- Name (e.g., "Standard")
- Description (e.g., "regular products")

---

## Practical Examples

### Example 1: Create Standard VAT Code

**Admin:**
```
Code: VAT-STD
Name: Standard Rated (16%)
VAT Rate: 16.00
Description: Regular products taxed at standard rate
```

**API:**
```bash
curl -X POST http://localhost:8000/api/vat-codes/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "VAT-STD",
    "name": "Standard Rated (16%)",
    "vat_rate": "16.00",
    "description": "Regular products taxed at standard rate",
    "is_active": true
  }'
```

### Example 2: Create Zero-Rated VAT Code

**Admin:**
```
Code: VAT-ZERO
Name: Zero Rated (0%)
VAT Rate: 0.00
Description: Unprocessed food items, essential supplies
HS Code Chapter: 04
```

**API:**
```bash
curl -X POST http://localhost:8000/api/vat-codes/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "VAT-ZERO",
    "name": "Zero Rated (0%)",
    "vat_rate": "0.00",
    "hs_code_chapter": "04",
    "description": "Unprocessed food items, essential supplies",
    "is_active": true
  }'
```

### Example 3: Create Excisable VAT Code

**Admin:**
```
Code: VAT-EXCISE
Name: Excisable Products
VAT Rate: 16.00
Excise Rate: 20.00
Import Duty: 0.00
Is Excisable: ✓ (checked)
Description: Products subject to both VAT and excise duty
```

**API:**
```bash
curl -X POST http://localhost:8000/api/vat-codes/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "VAT-EXCISE",
    "name": "Excisable Products",
    "vat_rate": "16.00",
    "excise_rate": "20.00",
    "import_duty": "0.00",
    "is_excisable": true,
    "description": "Products subject to both VAT and excise duty",
    "is_active": true
  }'
```

---

## Assigning VAT Codes to Products

### Via Admin Interface

1. Go to **Products** in Django Admin
2. Click on a product to edit
3. In the **Tax Settings** section, select a **VAT Code** from dropdown
4. Click **"Save"**

### Via API

```bash
curl -X PATCH http://localhost:8000/api/products/{product_id}/ \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "vat_code": 1
  }'
```

---

## Tax Calculation Logic

### Product Tax Rate Resolution

When calculating tax for a product:

```
1. If product has vat_code assigned:
   - Use vat_code.vat_rate for VAT
   - Add vat_code.excise_rate if is_excisable
   - Add vat_code.import_duty

2. If product has NO vat_code:
   - Use tax_class field (backward compatibility)
   - tax_class values: 'standard' (16%), 'zero_rated' (0%), 'exempt' (0%)

3. Business-level default:
   - BusinessSettings.vat_rate (typically 16%)
```

### Example Calculation

**Product: Beer Bottle (750ml)**
- VAT Code: VAT-EXCISE
  - VAT Rate: 16%
  - Excise Rate: 20%
  - Import Duty: 0%
- Total Tax Rate: 36% (16 + 20 + 0)

**Sale Calculation:**
- Product Price: 500 KES
- Total Tax (36%): 180 KES
- Price with Tax: 680 KES

---

## Backward Compatibility

### Legacy Products Without VAT Code

Products created before this module that don't have a VAT code assigned will continue to work using the `tax_class` field:

```python
# Legacy tax_class options
'standard'    → 16% VAT
'zero_rated'  → 0% VAT
'exempt'      → 0% VAT
```

### Migration Path

To migrate legacy products to the new VAT code system:

1. Create VAT codes matching your business needs
2. Assign VAT codes to products through admin or API
3. Legacy `tax_class` field acts as fallback if no VAT code exists

---

## Best Practices

### 1. **Code Naming Convention**
Use consistent prefixes:
```
VAT-STD      → Standard rate
VAT-ZERO     → Zero rated
VAT-EXEMPT   → Exempt
VAT-SPECIAL  → Special rates
VAT-EXCISE   → Excisable products
```

### 2. **Description Field**
Always provide detailed descriptions:
```
"Standard VAT rate for regular products and services"
"Zero-rated unprocessed food items per KRA guidelines"
"Excisable products: alcohol, tobacco, sugary drinks"
```

### 3. **HS Code Mapping**
Link to HS chapters for regulatory compliance:
```
HS Chapter 04 → Zero-rated food products
HS Chapter 22 → Excisable beverages
HS Chapter 24 → Excisable tobacco
```

### 4. **Excisable Products**
Always mark excisable products correctly:
- Check "Is Excisable" flag
- Set appropriate excise rate
- Document in description field

### 5. **Regular Audits**
- Review VAT codes quarterly
- Verify all products have correct codes
- Update rates when tax laws change

---

## Common Issues & Solutions

### Issue 1: "VAT code already exists"
**Cause:** Code is not unique within business
**Solution:** Use different code or edit existing one

### Issue 2: "Cannot delete VAT code - products exist"
**Cause:** Products are still using this VAT code
**Solution:** 
1. Reassign products to different VAT code
2. Or deactivate the VAT code (set `is_active` = false)

### Issue 3: Tax rate not updating on products
**Cause:** Product still using old `tax_class` instead of `vat_code`
**Solution:** Assign `vat_code` to product to override legacy setting

---

## Database Schema

### VATCode Table

```sql
CREATE TABLE pos_vatcode (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  business_id BIGINT NOT NULL,
  code VARCHAR(20) NOT NULL,
  name VARCHAR(100) NOT NULL,
  vat_rate DECIMAL(5,2) DEFAULT 16.00,
  excise_rate DECIMAL(5,2) DEFAULT 0.00,
  import_duty DECIMAL(5,2) DEFAULT 0.00,
  is_excisable BOOLEAN DEFAULT FALSE,
  hs_code_chapter VARCHAR(2) NULL,
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at DATETIME AUTO_NOW_ADD,
  updated_at DATETIME AUTO_NOW,
  UNIQUE KEY (business_id, code),
  INDEX (business_id, is_active),
  INDEX (business_id, vat_rate),
  INDEX (business_id, hs_code_chapter),
  FOREIGN KEY (business_id) REFERENCES pos_business(id)
);
```

### Product Table (New Field)

```sql
ALTER TABLE pos_product ADD COLUMN vat_code_id BIGINT NULL;
ALTER TABLE pos_product ADD FOREIGN KEY (vat_code_id) REFERENCES pos_vatcode(id);
```

---

## Related Documentation

- [Tax & VAT Configuration](https://docs.marid.co.ke/tax-configuration)
- [KRA Compliance Guide](https://docs.marid.co.ke/kra-compliance)
- [Product Management](https://docs.marid.co.ke/product-management)
- [API Reference](https://docs.marid.co.ke/api-reference)

---

## Support & Questions

For issues or questions about VAT Code Management:
1. Check this documentation first
2. Review the API examples
3. Check Django Admin interface for data
4. Contact support: support@marid.co.ke

---

**Last Updated:** August 11, 2026
**Version:** 1.0
**Module:** VAT Code Management System
