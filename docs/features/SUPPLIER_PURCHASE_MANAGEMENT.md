# Supplier and Purchase Management

## Overview

The Supplier and Purchase Management module allows you to track your suppliers, create purchase orders, and automatically update stock when purchases are received.

## Features

### Supplier Management
- Add, edit, and delete suppliers
- Track supplier contact information
- View purchase history per supplier
- Mark suppliers as active/inactive
- Track total purchases and purchase count

### Purchase Order Management
- Create purchase orders from suppliers
- Add multiple products to each purchase
- Track purchase status (Pending, Ordered, Received, Cancelled)
- Set expected delivery dates
- Add notes to purchases
- View purchase history

### Automatic Stock Updates
- Mark purchases as received
- Automatically update product stock quantities
- Create stock adjustment records for audit trail
- Prevent duplicate stock updates

## Database Models

### Supplier Model
- **name**: Supplier name (required)
- **contact_person**: Contact person name
- **email**: Email address
- **phone**: Phone number
- **address**: Physical address
- **notes**: Additional notes
- **is_active**: Active status
- **created_at**: Creation timestamp
- **updated_at**: Last update timestamp

### Purchase Model
- **purchase_number**: Auto-generated (PO-YYYYMMDD-XXXX)
- **supplier**: Foreign key to Supplier
- **date**: Purchase date
- **expected_delivery**: Expected delivery date
- **status**: Pending, Ordered, Received, or Cancelled
- **subtotal**: Total before tax
- **tax_amount**: Tax amount
- **total_amount**: Final total
- **notes**: Additional notes
- **received_date**: Date when marked as received


### PurchaseItem Model
- **purchase**: Foreign key to Purchase
- **product**: Foreign key to Product
- **quantity**: Quantity ordered
- **unit_cost**: Cost per unit
- **total_cost**: Quantity × Unit Cost (auto-calculated)

## How to Use

### Managing Suppliers

#### Add a New Supplier
1. Navigate to **Suppliers** from the menu
2. Click **Add Supplier**
3. Fill in supplier details:
   - Name (required)
   - Contact Person
   - Phone
   - Email
   - Address
   - Notes
   - Active status
4. Click **Save Supplier**

#### Edit a Supplier
1. Go to **Suppliers** list
2. Click **Edit** next to the supplier
3. Update the information
4. Click **Save Supplier**

#### Delete a Supplier
1. Go to **Suppliers** list
2. Click **Delete** next to the supplier
3. Confirm deletion
4. Note: Suppliers with purchase orders will show a warning

### Creating Purchase Orders

#### Create a New Purchase Order
1. Navigate to **Purchases** from the menu
2. Click **New Purchase Order**
3. Select a supplier
4. Set expected delivery date (optional)
5. Add notes (optional)
6. Add purchase items:
   - Click **Add Item**
   - Select product
   - Enter quantity
   - Enter unit cost (auto-fills with product price)
   - Repeat for more items
7. Review the summary (Subtotal, Tax, Total)
8. Click **Create Purchase Order**

#### View Purchase Details
1. Go to **Purchases** list
2. Click **View** next to any purchase
3. See all purchase information and items

#### Receive a Purchase
1. Open the purchase order details
2. Click **Mark as Received**
3. Review the items and stock changes
4. Click **Yes, Mark as Received**
5. Stock is automatically updated for all items
6. Stock adjustment records are created

#### Cancel a Purchase
1. Open the purchase order details
2. Click **Cancel**
3. Confirm cancellation
4. Note: Cannot cancel received purchases

### Viewing Purchase History
1. Navigate to **Purchases**
2. Filter by status:
   - All Statuses
   - Pending
   - Ordered
   - Received
   - Cancelled
3. View purchase list with details

## Purchase Number Format

Purchase numbers are auto-generated in the format:
```
PO-YYYYMMDD-XXXX
```

Example: `PO-20260206-0001`

- **PO**: Purchase Order prefix
- **YYYYMMDD**: Date (Year-Month-Day)
- **XXXX**: Sequential number (resets daily)

## Stock Integration

### Automatic Stock Updates
When a purchase is marked as received:
1. Purchase status changes to "Received"
2. Received date is recorded
3. For each item in the purchase:
   - Product stock quantity increases
   - Stock adjustment record is created
   - Adjustment type: "Restock"
   - Reason: "Purchase received: PO-XXXXXXXX-XXXX"

### Stock Adjustment Records
Each purchase creates audit trail records:
- **Product**: The product restocked
- **Adjustment Type**: Restock
- **Quantity Change**: +X (positive number)
- **Previous Quantity**: Stock before purchase
- **New Quantity**: Stock after purchase
- **Reason**: Purchase number reference
- **Created At**: Timestamp

### Preventing Duplicate Updates
- Purchases can only be received once
- Status check prevents duplicate stock updates
- Warning message shown if already received

## Dashboard Integration

The dashboard shows:
- **Total Suppliers**: Count of active suppliers
- **Pending Purchases**: Count of pending purchase orders

Quick actions include:
- **New Purchase**: Create a new purchase order

## Navigation

New menu items added:
- **Suppliers**: Manage suppliers
- **Purchases**: Manage purchase orders

## Admin Panel

All models are registered in the admin panel:
- **Suppliers**: Full CRUD operations
- **Purchases**: View and manage purchases
- **Purchase Items**: Inline editing in purchase admin

## Reports and Analytics

### Supplier Statistics
Each supplier shows:
- Total purchase amount (sum of received purchases)
- Number of purchases

### Purchase Status Tracking
Filter purchases by:
- Pending: Not yet ordered
- Ordered: Order placed with supplier
- Received: Stock updated
- Cancelled: Order cancelled

## Best Practices

### Supplier Management
1. Keep supplier information up to date
2. Mark inactive suppliers instead of deleting
3. Add detailed notes for special terms or conditions
4. Maintain accurate contact information

### Purchase Orders
1. Always set expected delivery dates
2. Add notes for special instructions
3. Review items before creating purchase
4. Mark as received promptly when stock arrives
5. Only cancel if necessary (before receiving)

### Stock Management
1. Verify quantities before marking as received
2. Check stock adjustment history for audit trail
3. Use purchase orders for all restocking
4. Keep purchase records for accounting

## Workflow Example

### Complete Purchase Workflow
1. **Add Supplier**
   - Name: ABC Distributors
   - Contact: John Doe
   - Phone: 0712345678
   - Email: john@abc.com

2. **Create Purchase Order**
   - Supplier: ABC Distributors
   - Expected Delivery: 2026-02-10
   - Items:
     - Product A: 50 units @ KES 100
     - Product B: 30 units @ KES 150
   - Total: KES 9,500

3. **Track Status**
   - Status: Pending → Ordered (manually update)

4. **Receive Purchase**
   - When stock arrives, mark as received
   - Stock automatically updated:
     - Product A: +50 units
     - Product B: +30 units
   - Status: Received

5. **Verify Stock**
   - Check stock list
   - View stock history
   - See purchase reference in adjustments

## Troubleshooting

### Cannot Delete Supplier
- Suppliers with purchases cannot be deleted
- Mark as inactive instead
- Or delete associated purchases first

### Purchase Already Received
- Cannot receive a purchase twice
- Check purchase status
- View received date

### Stock Not Updated
- Ensure purchase is marked as received
- Check stock adjustment history
- Verify purchase items exist

### Wrong Stock Quantity
- Cannot undo automatic stock update
- Create manual stock adjustment
- Use "Stock Correction" adjustment type

## Future Enhancements

Possible additions:
- Purchase order approval workflow
- Supplier performance tracking
- Purchase order templates
- Bulk purchase creation
- Email notifications to suppliers
- Purchase order PDF generation
- Payment tracking
- Supplier invoices
- Purchase analytics and reports

## Technical Details

### URL Routes
```python
# Suppliers
/suppliers/                    # List suppliers
/suppliers/create/             # Create supplier
/suppliers/<id>/edit/          # Edit supplier
/suppliers/<id>/delete/        # Delete supplier

# Purchases
/purchases/                    # List purchases
/purchases/create/             # Create purchase
/purchases/<id>/               # View purchase details
/purchases/<id>/receive/       # Mark as received
/purchases/<id>/cancel/        # Cancel purchase
```

### Views
- `supplier_list`: Display all suppliers
- `supplier_create`: Create new supplier
- `supplier_edit`: Edit existing supplier
- `supplier_delete`: Delete supplier
- `purchase_list`: Display all purchases
- `purchase_create`: Create new purchase
- `purchase_detail`: View purchase details
- `purchase_receive`: Mark purchase as received
- `purchase_cancel`: Cancel purchase

### Templates
- `supplier_list.html`: Supplier listing
- `supplier_form.html`: Supplier create/edit form
- `supplier_confirm_delete.html`: Delete confirmation
- `purchase_list.html`: Purchase listing
- `purchase_form.html`: Purchase creation form
- `purchase_detail.html`: Purchase details view
- `purchase_receive_confirm.html`: Receive confirmation
- `purchase_cancel_confirm.html`: Cancel confirmation

## Summary

The Supplier and Purchase Management module provides:
- ✅ Complete supplier management
- ✅ Purchase order creation and tracking
- ✅ Automatic stock updates on receipt
- ✅ Full audit trail with stock adjustments
- ✅ Dashboard integration
- ✅ Status tracking and filtering
- ✅ Supplier performance metrics

This module streamlines the procurement process and ensures accurate stock management for your retail business.

---

**Version**: 1.4.0  
**Last Updated**: February 6, 2026  
**Status**: Complete and Tested
