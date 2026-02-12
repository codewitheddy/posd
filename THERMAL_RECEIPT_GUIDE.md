# Thermal Receipt Printer Guide

## Overview
The POS system now includes a thermal printer-optimized receipt format designed for 80mm and 58mm thermal printers commonly used in retail environments.

## Features

### Receipt Design
- **Compact Layout**: Optimized for 80mm (3.15") thermal paper width
- **Responsive**: Automatically adjusts for 58mm (2.28") printers
- **Monospace Font**: Uses 'Courier New' for consistent character spacing
- **Clear Sections**: Organized with dashed dividers for easy reading
- **Auto-Print**: Automatically triggers print dialog when opened

### Information Displayed
1. **Header Section**
   - Shop name (bold, centered)
   - Business address
   - Phone number
   - Email
   - Tax ID/PIN

2. **Transaction Details**
   - Invoice number
   - Date and time
   - Cashier name
   - Customer name (if applicable)

3. **Items List**
   - Product name
   - Quantity × Unit price
   - Line total

4. **Totals Breakdown**
   - Subtotal (excl. VAT)
   - Discount (if applied)
   - VAT amount and rate
   - Grand total (incl. VAT)

5. **Payment Information**
   - Payment method(s) used
   - Reference numbers
   - Amount paid
   - Change given (if applicable)

6. **Loyalty Points** (if customer selected)
   - Points earned from transaction
   - Current points balance

7. **Footer**
   - Thank you message
   - Website (if configured)
   - Invoice number barcode placeholder

## How to Use

### From Invoice Page
1. Complete a sale in the POS screen
2. You'll be redirected to the invoice page
3. Click the **"Print Thermal Receipt"** button (green button)
4. The thermal receipt will open in a new tab
5. Print dialog will appear automatically
6. Select your thermal printer and print

### Direct URL Access
Access thermal receipt directly via:
```
/invoice/<sale_id>/thermal/
```

### Printer Setup

#### Windows
1. Install thermal printer driver
2. Set paper size to 80mm (or 58mm)
3. In print dialog, select your thermal printer
4. Adjust margins to 0 if needed

#### Linux
1. Install CUPS and printer drivers
2. Configure printer with correct paper size
3. Use browser print or command line:
   ```bash
   lp -d thermal_printer receipt.html
   ```

#### ESC/POS Printers
For direct ESC/POS printing (advanced):
- Use JavaScript libraries like `escpos` or `node-thermal-printer`
- Send raw commands directly to printer
- Requires additional integration

## Customization

### Adjust Paper Width
Edit `receipt_thermal.html` and modify the body width:

```css
body {
    width: 58mm;  /* Change to 58mm for smaller printers */
}
```

### Change Font Size
Adjust font sizes in the CSS:

```css
body {
    font-size: 11px;  /* Smaller for more content */
}
```

### Add Logo
Add an image in the header section:

```html
<div class="header">
    <img src="/static/logo.png" style="width: 50mm; margin-bottom: 5px;">
    <div class="shop-name">{{ shop_name|upper }}</div>
    ...
</div>
```

### Add Barcode
Install a barcode library and add to template:

```html
<div style="text-align: center; margin-top: 10px;">
    <img src="{% url 'generate_barcode' sale.invoice_number %}" alt="Barcode">
</div>
```

## Business Settings Integration

The thermal receipt automatically pulls information from Business Settings:
- Shop name
- Address
- Phone
- Email
- Tax ID/PIN
- Website

To configure these:
1. Go to **Settings** in the main menu
2. Fill in your business information
3. Save changes
4. Receipts will automatically show updated information

## Print Settings Recommendations

### Browser Print Settings
- **Margins**: None (0mm all sides)
- **Headers/Footers**: Disabled
- **Background graphics**: Enabled (for borders)
- **Scale**: 100%

### Thermal Printer Settings
- **Paper width**: 80mm or 58mm
- **Paper type**: Thermal
- **Print speed**: Medium (for better quality)
- **Darkness**: Medium to Dark
- **Cut**: Auto-cut after print (if supported)

## Troubleshooting

### Receipt is too wide
- Check printer paper size setting
- Reduce font size in CSS
- Change body width to 58mm

### Content is cut off
- Increase font size
- Check printer margins
- Verify paper roll is loaded correctly

### Auto-print doesn't work
- Check browser popup blocker
- Enable JavaScript
- Try manual print (Ctrl+P / Cmd+P)

### Formatting issues
- Clear browser cache
- Check printer driver is up to date
- Test with different browser

## Comparison: Thermal vs Standard Invoice

| Feature | Thermal Receipt | Standard Invoice |
|---------|----------------|------------------|
| Paper Size | 80mm/58mm | A4 (210mm) |
| Layout | Vertical, compact | Full page |
| Font | Monospace | Proportional |
| Use Case | Quick receipts | Formal invoices |
| Print Speed | Fast | Slower |
| Cost | Low (thermal paper) | Higher (ink/toner) |

## Best Practices

1. **Keep thermal paper dry** - Moisture affects print quality
2. **Store receipts properly** - Thermal prints fade over time
3. **Regular printer maintenance** - Clean print head monthly
4. **Test prints** - Verify formatting before busy periods
5. **Backup digital copies** - Keep PDF invoices for records

## Future Enhancements

Potential improvements:
- QR code for digital receipt
- Barcode generation for invoice number
- Direct ESC/POS printing without browser
- Receipt customization in admin panel
- Multiple receipt templates
- Email receipt option
- SMS receipt delivery

## Technical Details

### File Location
```
posd/pos/templates/pos/receipt_thermal.html
```

### View Function
```python
@login_required
def thermal_receipt(request, pk):
    """View thermal printer receipt"""
    # Located in posd/pos/views.py
```

### URL Pattern
```python
path('invoice/<int:pk>/thermal/', views.thermal_receipt, name='thermal_receipt')
```

### CSS Media Queries
- Default: 80mm width
- `@media (max-width: 58mm)`: Adjusts for 58mm printers
- `@media print`: Print-specific styles

## Support

For issues or questions:
1. Check printer driver installation
2. Verify business settings are configured
3. Test with standard browser print first
4. Check browser console for JavaScript errors
5. Ensure thermal printer is set as default for receipt printing
