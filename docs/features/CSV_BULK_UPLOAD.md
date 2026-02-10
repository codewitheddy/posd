# CSV Bulk Upload Feature

## Overview

The POS system now supports bulk product upload via CSV files. This feature allows you to quickly add or update multiple products at once, saving time when setting up your inventory or making bulk changes.

## Features

### 1. Bulk Upload
- Upload multiple products from a single CSV file
- Create new products automatically
- Update existing products (matched by name or product_code)
- Auto-create categories if they don't exist
- Automatic stock adjustment records

### 2. CSV Export
- Export all existing products to CSV
- Use as template for bulk updates
- Backup your product data
- Share product list

### 3. Template Download
- Download pre-formatted CSV template
- Includes sample data
- Shows correct format
- Ready to fill in

## How to Use

### Method 1: Using Template

1. **Download Template**
   - Go to **Products** → **Bulk Upload**
   - Click "Download Template"
   - Opens CSV with sample data

2. **Fill in Your Products**
   - Open CSV in Excel or Google Sheets
   - Replace sample data with your products
   - Follow the format exactly

3. **Upload**
   - Go to **Products** → **Bulk Upload**
   - Select your CSV file
   - Click "Upload & Process"

4. **Review Results**
   - See success/error messages
   - Check product list
   - Fix any errors and re-upload if needed

### Method 2: Export & Modify

1. **Export Existing Products**
   - Go to **Products** → **Export CSV**
   - Downloads all current products

2. **Modify CSV**
   - Add new products
   - Update existing products
   - Delete rows you don't want to change

3. **Upload**
   - Go to **Products** → **Bulk Upload**
   - Upload modified CSV
   - System updates matching products

## CSV Format

### Required Columns

Your CSV file must have these columns in this exact order:

```
name,product_code,category,unit_price,stock_quantity,low_stock_threshold
```

### Column Details

| Column | Required | Type | Description | Example |
|--------|----------|------|-------------|---------|
| `name` | ✅ Yes | Text | Product name | Coca Cola 500ml |
| `product_code` | ❌ No | Text | Barcode/SKU (unique) | BEV001 |
| `category` | ❌ No | Text | Category name | Beverages |
| `unit_price` | ✅ Yes | Decimal | Price in KES | 80.00 |
| `stock_quantity` | ❌ No | Integer | Initial stock | 50 |
| `low_stock_threshold` | ❌ No | Integer | Alert level | 10 |

### Field Rules

**name**
- Required field
- Used to match existing products
- Can contain any characters
- Example: `Coca Cola 500ml`

**product_code**
- Optional but recommended
- Must be unique across all products
- Used for barcode scanning
- Leave empty if not using
- Example: `BEV001` or leave blank

**category**
- Optional
- Category will be created if it doesn't exist
- Case-sensitive
- Example: `Beverages`, `Groceries`

**unit_price**
- Required field
- Must be a number
- Use decimal point (.), not comma
- No currency symbols
- Example: `80.00`, `1500.50`

**stock_quantity**
- Optional (default: 0)
- Must be a whole number
- Cannot be negative
- Example: `50`, `100`

**low_stock_threshold**
- Optional (default: 10)
- Must be a whole number
- Alert level for low stock
- Example: `10`, `20`

## Example CSV Files

### Example 1: Basic Products
```csv
name,product_code,category,unit_price,stock_quantity,low_stock_threshold
Coca Cola 500ml,BEV001,Beverages,80.00,50,10
Bread,GRO001,Groceries,55.00,25,15
Soap Bar,PER001,Personal Care,45.00,30,10
```

### Example 2: Without Product Codes
```csv
name,product_code,category,unit_price,stock_quantity,low_stock_threshold
Fresh Milk 1L,,Dairy,120.00,30,10
White Bread,,Bakery,55.00,40,15
Hand Soap,,Personal Care,85.00,25,8
```

### Example 3: Mixed Categories
```csv
name,product_code,category,unit_price,stock_quantity,low_stock_threshold
Laptop,ELEC001,Electronics,45000.00,10,3
Notebook,STAT001,Stationery,150.00,200,30
Coffee,BEV006,Beverages,1500.00,25,8
Detergent,HOU004,Household,220.00,45,12
```

## Update vs Create Logic

### Creating New Products
A product is created if:
- No existing product has the same `product_code` (if provided)
- AND no existing product has the same `name`

### Updating Existing Products
A product is updated if:
- An existing product has the same `product_code`
- OR an existing product has the same `name`

**Update Behavior:**
- All fields are updated with CSV values
- Stock changes create adjustment records
- Product code can be added/changed
- Category can be changed

## Stock Adjustments

### Automatic Stock Records
When uploading CSV:

**For New Products:**
- If `stock_quantity > 0`, creates "Restock" adjustment
- Records initial stock

**For Existing Products:**
- If stock quantity changes, creates "Stock Correction" adjustment
- Records previous and new quantities
- Includes row number in reason

### Adjustment Details
- **Type**: Restock (new) or Correction (update)
- **Reason**: "CSV bulk upload - Row X"
- **Quantity Change**: Calculated automatically
- **Previous/New Quantity**: Tracked

## Error Handling

### Common Errors

**1. Missing Required Fields**
```
Error: Row 5: 'name' field is required
```
**Solution**: Add product name

**2. Invalid Price Format**
```
Error: Row 3: invalid literal for Decimal: 'abc'
```
**Solution**: Use numbers only (e.g., 80.00)

**3. Duplicate Product Code**
```
Error: Row 8: Product with code 'BEV001' already exists
```
**Solution**: Use unique codes or leave empty

**4. Invalid Stock Quantity**
```
Error: Row 6: invalid literal for int(): 'fifty'
```
**Solution**: Use numbers only (e.g., 50)

### Error Messages
- Shows up to 10 errors at once
- Indicates row number
- Describes the problem
- Successful rows are still processed

## Best Practices

### 1. Prepare Your CSV

**Use Proper Software:**
- Microsoft Excel
- Google Sheets
- LibreOffice Calc

**Save Correctly:**
- File → Save As
- Choose "CSV (Comma delimited)"
- Not "CSV UTF-8" or other variants

### 2. Data Entry Tips

**Product Names:**
- Be consistent with naming
- Include size/variant in name
- Example: "Coca Cola 500ml" not just "Coca Cola"

**Product Codes:**
- Use consistent format
- Consider category prefixes (BEV, GRO, etc.)
- Keep them short and memorable

**Prices:**
- Always use decimal point
- Include cents even if zero (80.00)
- No commas in numbers

**Stock Quantities:**
- Count accurately before entering
- Consider starting with lower numbers
- Adjust later if needed

### 3. Testing

**Start Small:**
- Test with 5-10 products first
- Verify results
- Then upload full list

**Backup First:**
- Export existing products before bulk upload
- Keep backup of CSV file
- Can restore if needed

### 4. Validation

**Before Upload:**
- Check all required fields filled
- Verify prices are correct
- Confirm stock quantities
- Review product codes for duplicates

**After Upload:**
- Check success message
- Review product list
- Verify stock levels
- Test a few products at POS

## Workflow Examples

### Initial Setup (New Shop)

1. Download template
2. Fill in all your products
3. Include product codes if using scanners
4. Set realistic stock quantities
5. Upload CSV
6. Verify all products created
7. Print barcode labels if needed

### Adding New Products

1. Export existing products
2. Add new rows at bottom
3. Fill in new product details
4. Upload CSV
5. Only new products are created
6. Existing products unchanged

### Updating Prices

1. Export existing products
2. Update unit_price column
3. Don't change other fields
4. Upload CSV
5. Prices updated
6. Stock unchanged

### Stock Correction

1. Export existing products
2. Update stock_quantity column
3. Upload CSV
4. Stock adjusted
5. Adjustment records created

### Reorganizing Categories

1. Export existing products
2. Change category column
3. Upload CSV
4. Products moved to new categories
5. Categories created if needed

## Technical Details

### File Processing

**Upload Process:**
1. Validate file extension (.csv)
2. Read and parse CSV
3. Process each row
4. Match existing products
5. Create or update products
6. Create stock adjustments
7. Return results

**Performance:**
- Processes ~100 products per second
- No limit on file size
- Handles thousands of products

### Database Operations

**For Each Row:**
```python
1. Get or create category
2. Check for existing product (by code or name)
3. If exists:
   - Update all fields
   - Adjust stock if changed
   - Create adjustment record
4. If new:
   - Create product
   - Set initial stock
   - Create adjustment record
```

### API Endpoints

**Bulk Upload:**
```
POST /products/bulk-upload/
Content-Type: multipart/form-data
File: csv_file
```

**Export Products:**
```
GET /products/export/
Returns: CSV file download
```

**Download Template:**
```
GET /products/template/
Returns: CSV template with samples
```

## Troubleshooting

### CSV Won't Upload

**Problem**: "File must be a CSV!"

**Solutions:**
- Save as CSV (Comma delimited)
- Check file extension is .csv
- Don't use Excel format (.xlsx)

### Wrong Number of Columns

**Problem**: "Row has wrong number of columns"

**Solutions:**
- Check all rows have 6 columns
- No extra commas in data
- Use quotes for text with commas

### Encoding Issues

**Problem**: Special characters appear wrong

**Solutions:**
- Save as UTF-8 encoding
- Avoid special characters
- Use plain text only

### All Rows Fail

**Problem**: Every row shows error

**Solutions:**
- Check column names exactly match
- Verify CSV format
- Try template file first

## Sample Files

### Included Files

**sample_products.csv**
- 10 sample products
- Various categories
- Ready to upload
- Located in project root

**Template (via download)**
- Empty template
- 3 sample rows
- Shows correct format
- Download from bulk upload page

## Integration with Other Features

### Barcode Scanning
- Upload products with codes
- Codes immediately available for scanning
- Test at POS after upload

### Inventory Management
- Stock quantities set on upload
- Adjustment records created
- Low stock thresholds configured

### Categories
- Auto-created from CSV
- No need to create separately
- Consistent naming important

### Stock Alerts
- Thresholds set per product
- Alerts active immediately
- Check dashboard after upload

## Security & Validation

### File Validation
- Only .csv files accepted
- File size checked
- Content validated

### Data Validation
- Required fields checked
- Data types validated
- Duplicates prevented
- Invalid data skipped

### Error Recovery
- Invalid rows skipped
- Valid rows processed
- Detailed error messages
- No partial updates per row

## Tips for Large Uploads

### Handling 1000+ Products

**Split Files:**
- Upload in batches of 500
- Easier to troubleshoot
- Faster processing

**Optimize Data:**
- Remove unnecessary columns
- Clean data before upload
- Validate in spreadsheet first

**Monitor Progress:**
- Watch success count
- Check for errors
- Verify in product list

## Summary

The CSV bulk upload feature provides:
- ✅ Fast product entry
- ✅ Easy bulk updates
- ✅ Automatic category creation
- ✅ Stock adjustment tracking
- ✅ Error handling
- ✅ Export capability
- ✅ Template download

Perfect for:
- Initial shop setup
- Bulk price updates
- Stock corrections
- Adding new product lines
- Migrating from other systems

---

**Version**: 1.3.0  
**Added**: February 6, 2026  
**Status**: ✅ Active
