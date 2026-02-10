# Role-Based Access Control & Cashier Management

## Overview

A comprehensive role-based access control (RBAC) system that allows you to create multiple user accounts with different permission levels, track which cashier made each sale, and generate cashier performance reports.

## User Roles

### 1. Manager (Full Access)
**Permissions:**
- ✅ Full access to all features
- ✅ Create/edit/delete products
- ✅ Manage purchases and suppliers
- ✅ Manage stock
- ✅ Make sales
- ✅ View all reports
- ✅ View cashier reports
- ✅ Manage users

**Use Case:** Shop owner, store manager

### 2. Cashier (Sales Only)
**Permissions:**
- ✅ Make sales (POS screen)
- ✅ View products
- ✅ View their own sales
- ❌ Cannot add/edit products
- ❌ Cannot manage purchases
- ❌ Cannot manage stock
- ❌ Cannot view cashier reports

**Use Case:** Front desk staff, sales clerks

### 3. Stock Manager (Inventory)
**Permissions:**
- ✅ Add/edit/delete products
- ✅ Manage stock levels
- ✅ Create purchase orders
- ✅ Manage suppliers
- ✅ View stock reports
- ❌ Cannot make sales
- ❌ Cannot view cashier reports

**Use Case:** Inventory manager, warehouse staff

## Setup Instructions

### Step 1: Set Up Roles
Run this command to create the three roles:
```bash
python manage.py setup_roles
```

This creates:
- Manager group
- Cashier group
- Stock Manager group

### Step 2: Create User Accounts

**Option A: Via Admin Panel**
1. Login as admin
2. Go to Admin Panel (click username → Admin Panel)
3. Click "Users" → "Add User"
4. Enter username and password
5. Click "Save and continue editing"
6. Scroll to "Groups" section
7. Select appropriate group (Manager, Cashier, or Stock Manager)
8. Click "Save"

**Option B: Via Command Line**
```bash
# Create a cashier
python manage.py createsuperuser --username cashier1

# Then assign to Cashier group via admin panel
```

### Step 3: Test Access
1. Logout from admin account
2. Login with new user credentials
3. Verify they only see allowed features

## Features

### Cashier Tracking
Every sale is automatically tracked with:
- Cashier who made the sale
- Date and time
- Invoice number
- Total amount

### Cashier Reports
Managers can view:
- Sales by cashier
- Revenue by cashier
- Number of transactions
- Average sale amount
- Individual sale details

### Permission Enforcement
- Automatic permission checks
- Friendly error messages
- Redirect to dashboard if unauthorized
- Menu items hidden based on permissions

## How to Use

### Creating a Cashier Account

1. **Login as Manager/Admin**
2. **Go to Admin Panel**
3. **Click "Users" → "Add User"**
4. **Fill in details:**
   - Username: cashier1
   - Password: (strong password)
5. **Click "Save and continue editing"**
6. **Assign to Cashier group:**
   - Scroll to "Groups"
   - Select "Cashier"
   - Click arrow to move to "Chosen groups"
7. **Optional: Add personal info:**
   - First name
   - Last name
   - Email
8. **Click "Save"**

### Cashier Login & Work

1. **Cashier logs in** with their credentials
2. **They see limited menu:**
   - Dashboard (limited view)
   - New Sale (POS screen)
   - Products (view only)
3. **Make sales:**
   - Go to New Sale
   - Add products to cart
   - Complete sale
   - Sale is automatically tagged with their username

### Viewing Cashier Reports

1. **Login as Manager**
2. **Go to Reports → Cashier Report**
3. **Select date** to view
4. **See performance:**
   - Each cashier's sales count
   - Revenue generated
   - Items sold
   - Average sale amount
5. **Click "View Sales"** to see individual transactions

### End of Shift Report

1. **Manager selects today's date**
2. **Views each cashier's performance**
3. **Expands details** to see all sales
4. **Verifies totals**
5. **Closes shift**

## Permission Matrix

| Feature | Manager | Cashier | Stock Manager |
|---------|---------|---------|---------------|
| Dashboard | ✅ Full | ✅ Limited | ✅ Full |
| Make Sales | ✅ | ✅ | ❌ |
| View Products | ✅ | ✅ | ✅ |
| Add/Edit Products | ✅ | ❌ | ✅ |
| Delete Products | ✅ | ❌ | ✅ |
| Manage Stock | ✅ | ❌ | ✅ |
| Create Purchases | ✅ | ❌ | ✅ |
| Manage Suppliers | ✅ | ❌ | ✅ |
| Sales Reports | ✅ | ✅ Own | ✅ |
| Cashier Reports | ✅ | ❌ | ❌ |
| User Management | ✅ | ❌ | ❌ |

## Cashier Report Features

### Summary Statistics
- Total sales for the day
- Total revenue
- Number of cashiers active
- Overall performance

### Per-Cashier Breakdown
- Cashier name and username
- Number of sales made
- Total items sold
- Total revenue generated
- Average sale amount
- Expandable sales list

### Individual Sale Details
- Invoice number
- Time of sale
- Number of items
- Total amount
- Link to view full invoice

## Use Cases

### Scenario 1: Morning Shift
1. **Cashier A logs in** at 8 AM
2. **Makes sales** throughout morning
3. **Manager checks** mid-day performance
4. **Sees Cashier A** has made 15 sales, KES 45,000

### Scenario 2: Multiple Shifts
1. **Cashier A** works 8 AM - 2 PM
2. **Cashier B** works 2 PM - 8 PM
3. **Manager views report** at end of day
4. **Compares performance:**
   - Cashier A: 20 sales, KES 60,000
   - Cashier B: 25 sales, KES 75,000

### Scenario 3: Discrepancy Investigation
1. **Manager notices** cash shortage
2. **Views cashier report** for the day
3. **Expands sales** for each cashier
4. **Verifies** each transaction
5. **Identifies** missing sale

### Scenario 4: Performance Review
1. **Manager reviews** weekly performance
2. **Checks each day's** cashier report
3. **Calculates totals** per cashier
4. **Provides feedback** based on data

## Security Features

### Password Protection
- All accounts require strong passwords
- Passwords are encrypted
- Cannot be viewed by anyone

### Session Management
- Automatic logout after inactivity
- Secure session cookies
- One session per user

### Audit Trail
- Every sale tracked to cashier
- Timestamps on all transactions
- Cannot be modified after creation

### Permission Enforcement
- Automatic checks on every page
- Cannot bypass via URL manipulation
- Error messages for unauthorized access

## Best Practices

### For Managers
1. **Create unique accounts** for each cashier
2. **Use strong passwords**
3. **Review reports daily**
4. **Verify cash vs. system totals**
5. **Provide feedback** to cashiers
6. **Change passwords** if employee leaves

### For Cashiers
1. **Never share** your login credentials
2. **Logout** when leaving the counter
3. **Verify** each sale before completing
4. **Report issues** immediately
5. **Keep password** secure

### For Security
1. **Regular password changes**
2. **Disable accounts** for ex-employees
3. **Monitor unusual activity**
4. **Backup data** regularly
5. **Use HTTPS** in production

## Troubleshooting

### Cashier Can't Access Feature
- Check they're in correct group
- Verify group permissions
- Ensure they're logged in
- Check if feature requires manager role

### Sales Not Showing in Report
- Verify cashier was logged in during sale
- Check correct date selected
- Ensure sale was completed
- Refresh the page

### Can't Create New User
- Must be logged in as manager/admin
- Use admin panel for user creation
- Assign to appropriate group
- Save changes

## Advanced Configuration

### Custom Permissions
You can create custom permission combinations:
1. Go to Admin Panel
2. Click "Groups"
3. Create new group
4. Select specific permissions
5. Assign users to group

### Permission Codes
- `pos.add_product` - Can add products
- `pos.change_product` - Can edit products
- `pos.delete_product` - Can delete products
- `pos.add_sale` - Can make sales
- `pos.view_sale` - Can view sales
- `pos.add_purchase` - Can create purchases
- `pos.change_purchase` - Can edit purchases

## Reports & Analytics

### Daily Cashier Report
- View by date
- See all cashiers who worked
- Compare performance
- Drill down to individual sales

### Monthly Summary (Future)
- Total sales per cashier
- Average daily performance
- Best performing cashier
- Trends over time

## Integration

### With Existing Features
- Sales automatically tagged
- Invoices show cashier name
- Reports filter by cashier
- Dashboard shows user info

### With Admin Panel
- User management
- Group assignment
- Permission control
- Activity logs

## Summary

The Role-Based Access Control system provides:
- ✅ Three predefined roles
- ✅ Automatic cashier tracking
- ✅ Comprehensive reports
- ✅ Permission enforcement
- ✅ Security features
- ✅ Easy user management
- ✅ Audit trail
- ✅ Performance monitoring

Perfect for:
- Multi-cashier environments
- Shift-based operations
- Performance tracking
- Security compliance
- Accountability
- Professional retail operations

---

**Version**: 1.7.0  
**Feature**: Role-Based Access Control & Cashier Management  
**Status**: ✅ Complete and Secure  
**Date**: February 6, 2026
