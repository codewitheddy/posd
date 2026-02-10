# Barcode / Product Code Feature

## Overview

The POS system now supports product codes (barcodes) for faster checkout. You can scan barcodes or manually enter product codes at the POS screen to quickly add items to the cart.

## Features

### 1. Product Code Field
- Each product can have a unique product code/barcode
- Optional field (products can exist without codes)
- Displayed in product list with badge
- Searchable in admin panel

### 2. POS Barcode Scanner
- Dedicated barcode input field at top of POS screen
- Auto-focused on page load for immediate scanning
- Press Enter or click Search to find product
- Automatically adds product to cart when found
- Shows success/error notifications
- Clears input after successful scan

### 3. Product Code Format
Sample codes included:
- **BEV001-005**: Beverages
- **GRO001-005**: Groceries
- **SNK001-004**: Snacks
- **PER001-003**: Personal Care
- **HOU001-003**: Household

You can use any format you prefer (EAN-13, UPC, custom codes, etc.)

## Usage Guide

### Adding Product Codes

#### When Creating Products
1. Go to **Products** → **Add Product**
2. Fill in product details
3. Enter product code in "Product Code / Barcode" field
4. Save product

#### When Editing Products
1. Go to **Products** → Click **Edit** on product
2. Update the "Product Code / Barcode" field
3. Save changes

### Using Barcode Scanner at POS

#### With Physical Barcode Scanner
1. Open POS screen
2. Barcode input field is auto-focused
3. Scan product barcode
4. Product automatically added to cart
5. Scanner ready for next item

#### Manual Entry
1. Open POS screen
2. Type product code in barcode input field
3. Press Enter or click Search button
4. Product added to cart if found

### Tips for Best Performance

1. **Keep Scanner Focused**: The barcode input stays focused for continuous scanning
2. **Quick Scanning**: Scan multiple items rapidly - each adds to cart automatically
3. **Error Handling**: If product not found, you'll see an error message
4. **Fallback**: Can still click products manually if scanner unavailable

## Technical Details

### Database Schema
```python
class Product(models.Model):
    name = models.CharField(max_length=200)
    product_code = models.CharField(
        max_length=50, 
        unique=True, 
        blank=True, 
        null=True,
        help_text="Barcode or product code for scanning"
    )
    # ... other fields
```

### API Endpoint
```
GET /api/product/search/?code=BEV001
```

**Response (Success):**
```json
{
    "success": true,
    "product": {
        "id": 1,
        "name": "Coca Cola 500ml",
        "product_code": "BEV001",
        "price": 80.0,
        "category": "Beverages"
    }
}
```

**Response (Not Found):**
```json
{
    "success": false,
    "error": "Product with code 'INVALID' not found"
}
```

### JavaScript Integration
```javascript
// Search by barcode
function searchByBarcode() {
    const code = document.getElementById('barcode-input').value;
    
    fetch(`/api/product/search/?code=${code}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                addToCart(data.product.id, data.product.name, data.product.price);
            }
        });
}

// Auto-submit on Enter key
document.getElementById('barcode-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        searchByBarcode();
    }
});
```

## Barcode Scanner Hardware

### Compatible Scanners
The system works with any USB barcode scanner that acts as a keyboard input device (HID). Most common scanners work out of the box.

### Recommended Scanners
- **USB Handheld Scanners**: Plug and play, no drivers needed
- **Wireless Bluetooth Scanners**: For mobility
- **2D Scanners**: Can read QR codes and various barcode formats

### Scanner Configuration
Most scanners need no configuration. They should:
1. Send barcode data as keyboard input
2. Automatically press Enter after scanning
3. Work in any text input field

### Testing Your Scanner
1. Open Notepad or any text editor
2. Scan a barcode
3. If text appears followed by new line, scanner is ready
4. Use in POS system immediately

## Product Code Best Practices

### 1. Consistent Format
Choose a format and stick to it:
- **Category Prefix**: BEV001, GRO001, SNK001
- **EAN-13**: 5901234123457
- **UPC**: 012345678905
- **Custom**: SHOP-001, PROD-001

### 2. Unique Codes
- Each product must have a unique code
- System enforces uniqueness at database level
- Duplicate codes will cause errors

### 3. Printable Labels
If generating your own barcodes:
- Use standard formats (EAN-13, Code 128, etc.)
- Print clear, high-contrast labels
- Test scannability before mass printing

### 4. Backup Manual Entry
- Not all products need codes
- Manual product selection still available
- Mix scanning and clicking as needed

## Troubleshooting

### Scanner Not Working
1. **Check USB Connection**: Ensure scanner is plugged in
2. **Test in Notepad**: Verify scanner sends keyboard input
3. **Check Focus**: Barcode input should be focused
4. **Try Manual Entry**: Type code and press Enter

### Product Not Found
1. **Verify Code**: Check product code in product list
2. **Check Spelling**: Codes are case-sensitive
3. **Update Product**: Add/correct code in product edit form

### Duplicate Code Error
1. **Check Existing Products**: Search for duplicate code
2. **Use Unique Codes**: Each product needs unique identifier
3. **Update Conflicting Product**: Change one of the codes

### Scanner Adds Extra Characters
1. **Scanner Configuration**: Check scanner settings
2. **Suffix Settings**: Disable any suffix characters
3. **Prefix Settings**: Disable any prefix characters

## Migration from Non-Barcode System

### Step 1: Add Codes to Existing Products
```python
# In Django shell
from pos.models import Product

# Update products one by one
product = Product.objects.get(name='Coca Cola 500ml')
product.product_code = 'BEV001'
product.save()

# Or bulk update
products = Product.objects.filter(category__name='Beverages')
for i, product in enumerate(products, 1):
    product.product_code = f'BEV{i:03d}'
    product.save()
```

### Step 2: Print Barcode Labels
1. Export product codes from admin panel
2. Use barcode label software to generate labels
3. Print and apply to products

### Step 3: Train Staff
1. Show barcode input field
2. Demonstrate scanning
3. Explain fallback to manual selection

## Future Enhancements

### Potential Additions
- **Barcode Generation**: Auto-generate codes for new products
- **Label Printing**: Print barcode labels from system
- **Batch Import**: Import products with codes from CSV
- **QR Codes**: Support for QR code scanning
- **Mobile Scanning**: Use phone camera as scanner
- **Inventory Integration**: Link to stock management

### Implementation Ideas
See [FUTURE_ENHANCEMENTS.md](FUTURE_ENHANCEMENTS.md) for detailed guides on:
- Barcode generation libraries
- Label printing integration
- Advanced scanning features

## Sample Product Codes

Current sample data includes:

| Product | Code | Category |
|---------|------|----------|
| Coca Cola 500ml | BEV001 | Beverages |
| Fanta Orange 500ml | BEV002 | Beverages |
| Sprite 500ml | BEV003 | Beverages |
| Bottled Water 500ml | BEV004 | Beverages |
| Milk 1L | BEV005 | Beverages |
| Bread | GRO001 | Groceries |
| Sugar 1kg | GRO002 | Groceries |
| Rice 2kg | GRO003 | Groceries |
| Cooking Oil 1L | GRO004 | Groceries |
| Tea Leaves 250g | GRO005 | Groceries |
| Crisps | SNK001 | Snacks |
| Biscuits | SNK002 | Snacks |
| Chocolate Bar | SNK003 | Snacks |
| Peanuts 100g | SNK004 | Snacks |
| Soap Bar | PER001 | Personal Care |
| Toothpaste | PER002 | Personal Care |
| Shampoo 200ml | PER003 | Personal Care |
| Tissue Paper | HOU001 | Household |
| Detergent 500g | HOU002 | Household |
| Matchbox | HOU003 | Household |

## Testing the Feature

### Test Barcode Scanning
1. Start server: `python manage.py runserver`
2. Go to POS screen: http://127.0.0.1:8000/pos/
3. Type `BEV001` in barcode input
4. Press Enter
5. Coca Cola should be added to cart

### Test API Directly
```bash
# Using curl
curl "http://127.0.0.1:8000/api/product/search/?code=BEV001"

# Using browser
http://127.0.0.1:8000/api/product/search/?code=BEV001
```

## Summary

The barcode feature makes checkout faster and reduces errors. It's:
- ✅ Easy to use
- ✅ Works with standard scanners
- ✅ Optional (products work without codes)
- ✅ Fast and responsive
- ✅ Production-ready

Start using it today by adding product codes to your products!

---

**Version**: 1.1.0  
**Added**: February 6, 2026  
**Status**: ✅ Active
