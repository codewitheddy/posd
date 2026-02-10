# Product Expiry Tracking

## Overview

The expiry tracking feature helps you manage perishable products by tracking expiry dates and alerting you before products expire.

## Features

### Expiry Date Management
- ✅ Add expiry dates to products (optional)
- ✅ Set custom alert threshold per product (default: 3 days)
- ✅ Track products without expiry dates (non-perishable)
- ✅ Update expiry dates when editing products

### Automatic Alerts
- ✅ Dashboard shows expired and expiring soon counts
- ✅ Color-coded status badges (Expired, Expiring Soon, Good)
- ✅ Dedicated expiry alerts page
- ✅ Real-time expiry status calculation

### Expiry Status Types
1. **Expired**: Product has passed expiry date (Red badge)
2. **Expiring Soon**: Within alert threshold (Yellow badge)
3. **Good**: More than alert threshold remaining (Green badge)
4. **No Expiry**: Non-perishable product (Gray text)

## How to Use

### Adding Expiry Date to New Product
1. Go to **Products** → **Add Product**
2. Fill in product details
3. Set **Expiry Date** (optional)
4. Set **Expiry Alert Days** (default: 3)
5. Click **Save Product**

### Updating Expiry Date
1. Go to **Products** list
2. Click **Edit** on the product
3. Update **Expiry Date** field
4. Adjust **Expiry Alert Days** if needed
5. Click **Save Product**

### Viewing Expiry Alerts
1. Check **Dashboard** for alert counts
2. Click **View Expiry Alerts** button
3. See two sections:
   - **Expired Products**: Immediate action required
   - **Expiring Soon**: Plan promotions or discounts

### Dashboard Alerts
The dashboard shows:
- Number of expired products (red)
- Number of expiring soon products (yellow)
- Quick link to expiry alerts page

## Expiry Alert Page

### Expired Products Section
- Shows products past expiry date
- Displays days overdue
- Action buttons:
  - **Remove Stock**: Adjust stock to zero
  - **Edit**: Update product details

### Expiring Soon Section
- Shows products within alert threshold
- Displays days until expiry
- Helps plan sales strategies

## Best Practices

### For Retail Shops
1. **Daily Checks**: Review expiry alerts every morning
2. **FIFO Method**: First In, First Out - sell older stock first
3. **Stock Rotation**: Place new stock behind old stock
4. **Promotions**: Discount products expiring soon
5. **Remove Expired**: Immediately remove expired items

### For Different Product Types

**Food Items**
- Set expiry dates for all perishable items
- Use 3-5 day alert threshold
- Check daily

**Medicines/Pharmaceuticals**
- Always set expiry dates
- Use 7-14 day alert threshold
- Check weekly
- Strict removal of expired items

**Cosmetics**
- Set expiry dates
- Use 7-30 day alert threshold
- Check weekly

**Non-Perishable Items**
- Leave expiry date blank
- No alerts generated

## Configuration

### Expiry Alert Threshold
- Default: 3 days before expiry
- Customizable per product
- Range: 1-365 days

### Examples
- Milk: 1-2 days alert
- Bread: 1-3 days alert
- Canned goods: 30-60 days alert
- Medicines: 7-14 days alert

## Database Fields

### Product Model
- `expiry_date`: DateField (optional)
- `expiry_alert_days`: IntegerField (default: 3)

### Helper Methods
- `is_expired()`: Check if expired
- `is_expiring_soon()`: Check if within threshold
- `days_until_expiry()`: Calculate remaining days
- `expiry_status`: Get status string

## Integration

### Dashboard
- Shows expired count
- Shows expiring soon count
- Alert button when issues exist

### Product List
- New "Expiry Status" column
- Color-coded badges
- Shows expiry date or status

### Product Form
- Expiry date input field
- Expiry alert days input
- Optional fields (can be blank)

## Workflow Example

### Daily Morning Routine
1. **Open Dashboard**
   - Check for expiry alerts
   
2. **View Expiry Alerts**
   - Review expired products
   - Review expiring soon products

3. **Take Action**
   - Remove expired items from shelves
   - Create promotions for expiring soon items
   - Update stock quantities

4. **Plan Orders**
   - Reduce orders for slow-moving perishables
   - Adjust stock levels

### Weekly Review
1. Check expiry trends
2. Identify slow-moving perishables
3. Adjust ordering patterns
4. Update alert thresholds if needed

## Tips for Success

### Inventory Management
- Order smaller quantities of perishables
- Track which items expire frequently
- Adjust stock levels based on sales velocity
- Use purchase orders to track delivery dates

### Sales Strategies
- **Discount Strategy**: 20-30% off items expiring in 2-3 days
- **Bundle Deals**: Combine expiring items
- **Flash Sales**: Quick sales for items expiring today
- **Customer Communication**: Be transparent about discounts

### Stock Organization
- **Front to Back**: New stock goes behind old stock
- **Clear Labels**: Mark expiry dates clearly
- **Separate Storage**: Keep expiring items visible
- **Regular Audits**: Physical checks match system

## Troubleshooting

### Product Shows Wrong Status
- Check expiry date is correct
- Verify alert threshold setting
- Ensure date format is correct

### No Alerts Showing
- Verify products have expiry dates set
- Check products have stock quantity > 0
- Confirm expiry dates are in the future

### Too Many Alerts
- Adjust expiry alert threshold
- Increase alert days for slow-moving items
- Review ordering patterns

## Reports and Analytics

### Current Features
- Count of expired products
- Count of expiring soon products
- Dashboard summary

### Future Enhancements
- Expiry trend reports
- Product waste tracking
- Expiry rate by category
- Financial impact of expired products

## Mobile Access

The expiry tracking system works on:
- Desktop browsers
- Tablets
- Mobile phones
- Responsive design for all screens

## Summary

The expiry tracking feature helps you:
- ✅ Reduce product waste
- ✅ Improve inventory management
- ✅ Increase customer safety
- ✅ Optimize ordering patterns
- ✅ Maximize profitability
- ✅ Maintain product quality

Perfect for:
- Grocery stores
- Pharmacies
- Convenience stores
- Restaurants
- Bakeries
- Any business with perishable products

---

**Version**: 1.5.0  
**Feature**: Product Expiry Tracking  
**Status**: ✅ Complete and Ready  
**Date**: February 6, 2026
