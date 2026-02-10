# Update Expiry Date Feature

## Overview

Added the ability to quickly update product expiry dates directly from the stock management page, making it easy to manage expiry dates when receiving new stock or correcting dates.

## New Features

### Stock List Enhancements

**New Column: Expiry Date**
- Shows expiry date with color-coded badges
- Red badge: Expired products
- Yellow badge: Expiring soon (with days left)
- Green badge: Good (plenty of time)
- Gray text: No expiry date set

**New Button: Update Expiry**
- Yellow button with calendar icon
- Available for every product
- Quick access to expiry management

### Update Expiry Page

**Product Information Display**
- Product name, code, category
- Current stock quantity
- Current expiry date (if set)
- Expiry status with color coding

**Update Form**
- Expiry date input (date picker)
- Expiry alert days input (number)
- Clear instructions and tips
- Option to remove expiry date

**Helpful Information**
- Current status alert (expired/expiring/good)
- Days until/past expiry
- Recommended alert days by product type
- Usage tips

## How to Use

### From Stock List
1. Go to **Stock** → **Stock List**
2. Find the product you want to update
3. Click **Update Expiry** button
4. Update the expiry date
5. Adjust alert days if needed
6. Click **Update Expiry Date**

### Common Scenarios

**Scenario 1: Receiving New Stock**
1. Product arrives with new expiry date
2. Go to Stock List
3. Click "Update Expiry" on the product
4. Enter new expiry date
5. Save

**Scenario 2: Correcting Wrong Date**
1. Notice incorrect expiry date
2. Click "Update Expiry"
3. Enter correct date
4. Save

**Scenario 3: Multiple Batches**
1. Have products with different expiry dates
2. Use the earliest expiry date
3. Update in system
4. Follow FIFO (First In, First Out)

**Scenario 4: Non-Perishable Item**
1. Product doesn't expire
2. Click "Update Expiry"
3. Leave expiry date blank
4. Save (removes expiry tracking)

## Stock List Display

### Expiry Date Column
Shows one of:
- **Red badge + "Expired!"**: Past expiry date
- **Yellow badge + "X days left"**: Expiring soon
- **Green badge**: Future expiry date
- **"No expiry"**: No date set

### Visual Indicators
- Color-coded for quick scanning
- Days countdown for expiring products
- Clear status messages
- Responsive design

## Update Expiry Page Features

### Current Status Alert
- **Red alert**: Product expired
- **Yellow alert**: Expiring soon
- **Green alert**: Good status
- **Gray alert**: No expiry set

### Form Fields

**Expiry Date**
- Date picker input
- Pre-filled with current date
- Can be cleared (blank = no expiry)
- HTML5 date input for easy selection

**Alert Days**
- Number input (1-365)
- Default: 3 days
- Pre-filled with current setting
- Customizable per product

### Helpful Tips Section
Shows recommended alert days:
- Dairy: 1-2 days
- Bread: 1-2 days
- Fresh produce: 2-3 days
- Meat: 1-2 days
- Medicines: 7-14 days
- Cosmetics: 7-30 days
- Canned goods: 30-60 days
- Packaged foods: 7-14 days

### Usage Tips
- Update when receiving new stock
- Use earliest date for multiple batches
- Set appropriate alert days
- Remove date for non-perishables

## Integration

### Stock Management
- Seamlessly integrated with stock list
- Consistent with other stock operations
- Same navigation and layout

### Expiry Tracking
- Updates reflected immediately
- Dashboard shows updated status
- Expiry alerts page updates
- Product list shows new dates

### Audit Trail
- Changes are saved to database
- Success messages confirm updates
- Shows old and new dates in message

## Benefits

### Quick Updates
- No need to edit full product details
- Focused on expiry management
- Fast workflow

### Batch Processing
- Easy to update multiple products
- Quick navigation between products
- Efficient for receiving days

### Flexibility
- Can add expiry dates
- Can update existing dates
- Can remove expiry dates
- Adjust alert thresholds

### Better Management
- Keep expiry dates current
- Reduce expired stock
- Improve FIFO compliance
- Better inventory control

## Workflow Examples

### Morning Receiving Routine
1. **Receive delivery**
2. **Check expiry dates** on packages
3. **Go to Stock List**
4. **For each product:**
   - Click "Update Expiry"
   - Enter new date
   - Save
5. **Continue with stock adjustment** (if needed)

### Weekly Expiry Review
1. **Check expiry alerts**
2. **Verify dates are correct**
3. **Update any incorrect dates**
4. **Adjust alert days** if needed

### New Product Setup
1. **Add product** with initial expiry
2. **Later, update from Stock List** as needed
3. **Adjust alert days** based on experience

## Success Messages

The system shows clear feedback:
- "Expiry date updated from [old] to [new]"
- "Expiry date set to [date]"
- "Expiry date removed"

## Mobile Friendly

- Responsive design
- Touch-friendly buttons
- Date picker works on mobile
- Easy to use on tablets

## Technical Details

### URL Route
```
/stock/<id>/update-expiry/
```

### View Function
- `update_expiry(request, pk)`
- GET: Display form
- POST: Update expiry date
- Redirects to stock list

### Template
- `pos/templates/pos/update_expiry.html`
- Bootstrap styling
- Color-coded alerts
- Helpful tips section

### Database Updates
- Updates `expiry_date` field
- Updates `expiry_alert_days` field
- Saves to Product model
- Immediate effect

## Best Practices

### When to Update
- Upon receiving new stock
- When correcting errors
- When consolidating batches
- During inventory audits

### FIFO Compliance
- Always use earliest expiry date
- Update when mixing batches
- Rotate stock properly
- Track batch information

### Alert Day Settings
- Start with defaults
- Adjust based on sales velocity
- Consider product type
- Monitor and refine

## Tips for Success

### Daily Operations
- Update expiry dates during receiving
- Check expiry alerts daily
- Keep dates current
- Train staff on process

### Inventory Management
- Use expiry dates for ordering decisions
- Track which products expire frequently
- Adjust order quantities
- Implement FIFO strictly

### Waste Reduction
- Accurate dates prevent waste
- Early alerts enable promotions
- Better planning reduces losses
- Track expiry trends

## Summary

The Update Expiry feature provides:
- ✅ Quick access from stock list
- ✅ Easy-to-use update form
- ✅ Current status display
- ✅ Helpful tips and recommendations
- ✅ Color-coded visual indicators
- ✅ Flexible date management
- ✅ Mobile-friendly interface
- ✅ Immediate updates across system

Perfect for:
- Receiving new stock
- Correcting dates
- Managing multiple batches
- Maintaining accurate expiry tracking
- Reducing waste
- Improving inventory control

---

**Version**: 1.5.2  
**Feature**: Update Expiry Date from Stock List  
**Status**: ✅ Complete and Ready  
**Date**: February 6, 2026
