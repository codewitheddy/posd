# User Management & Business Settings - Quick Start Guide

## 🚀 What's New?

Your POS system now includes:
- **User Management**: Create and manage staff accounts with roles
- **Business Settings**: Configure your business information and preferences
- **Activity Log**: Track all system activities for audit and security

## 📋 Quick Setup (3 Steps)

### Step 1: Migrations Already Applied ✓
The database has been updated with new tables.

### Step 2: Business Settings Initialized ✓
Default business settings have been created.

### Step 3: Access the Features

#### For Managers/Admins:
1. Login to your POS system
2. Look for the new **"Admin"** dropdown in the navigation bar
3. You'll see:
   - **User Management** - Manage staff accounts
   - **Business Settings** - Configure your business
   - **Activity Log** - View system activities

#### For All Users:
1. Click on your username in the top-right corner
2. Select **"My Profile"**
3. Update your personal information

## 🎯 Common Tasks

### Create a New User
1. Go to **Admin > User Management**
2. Click **"Add New User"**
3. Fill in:
   - Username (required)
   - Password (required)
   - Email, name (optional)
   - Role (Cashier, Manager, Stock Manager)
   - Employee ID, phone, etc.
4. Click **"Create User"**

### Configure Your Business
1. Go to **Admin > Business Settings**
2. Update sections:
   - **Business Information**: Name, address, contact details
   - **Tax Settings**: VAT rate (default 16%)
   - **Currency**: Symbol and position
   - **Receipt Settings**: Custom header/footer text
   - **Stock Settings**: Default thresholds and alerts
   - **System Settings**: Various preferences
3. Click **"Save Settings"**

### View Activity Logs
1. Go to **Admin > Activity Log**
2. Use filters:
   - Filter by user
   - Filter by action type (create, update, delete, login, etc.)
   - Filter by date
3. View detailed activity history

### Update Your Profile
1. Click your username > **"My Profile"**
2. Update:
   - Personal information
   - Contact details
   - Password (if needed)
3. Click **"Update Profile"**

## 🔐 User Roles

### Administrator (Superuser)
- Full system access
- Can manage all users
- Can access Django admin
- Can configure business settings

### Manager
- Can manage users
- Can view all reports
- Can configure business settings
- Can view activity logs
- Can manage inventory and purchases

### Stock Manager
- Can manage products
- Can adjust stock
- Can manage purchases
- Can view stock reports

### Cashier
- Can make sales
- Can view products
- Can view own sales report
- Can update own profile

## 📊 Features Overview

### User Management
- ✅ Create, edit, delete users
- ✅ Assign roles and permissions
- ✅ Track employee information
- ✅ View user sales statistics
- ✅ Activate/deactivate accounts
- ✅ Password management

### Business Settings
- ✅ Business information
- ✅ Tax/VAT configuration
- ✅ Currency settings
- ✅ Receipt customization
- ✅ Stock management defaults
- ✅ System preferences

### Activity Log
- ✅ Track all user actions
- ✅ Login/logout tracking
- ✅ Sales tracking
- ✅ Stock adjustment tracking
- ✅ IP address logging
- ✅ Filterable and searchable

## 🎨 Navigation Updates

### New Admin Menu (Managers Only)
Located in the top navigation bar:
```
Admin ▼
├── User Management
├── Business Settings
├── Activity Log
└── Django Admin
```

### Updated User Menu
Click your username:
```
Username ▼
├── My Profile (NEW)
└── Logout
```

## 💡 Tips & Best Practices

### Security
- ✓ Use strong passwords for all users
- ✓ Regularly review activity logs
- ✓ Deactivate users who leave the company
- ✓ Assign appropriate roles to users
- ✓ Don't share admin credentials

### Business Settings
- ✓ Configure business settings before first sale
- ✓ Set appropriate VAT rate for your region
- ✓ Customize receipt header/footer for branding
- ✓ Set realistic stock thresholds
- ✓ Review settings periodically

### User Management
- ✓ Create unique accounts for each staff member
- ✓ Use employee IDs for tracking
- ✓ Keep contact information updated
- ✓ Assign roles based on job responsibilities
- ✓ Train users on their specific features

### Activity Monitoring
- ✓ Check activity logs regularly
- ✓ Look for unusual patterns
- ✓ Use filters to find specific activities
- ✓ Export logs for record keeping
- ✓ Review user performance

## 🔧 Troubleshooting

### Can't see Admin menu?
**Solution**: You need Manager or Administrator role
- Ask your administrator to assign you the Manager role
- Or login with an admin account

### Business settings not saving?
**Solution**: Check for validation errors
- Ensure all required fields are filled
- Check that VAT rate is between 0-100
- Verify currency symbol is valid

### Activity logs empty?
**Solution**: Logs are created automatically
- Perform some actions (create product, make sale, etc.)
- Refresh the activity log page
- Check date filter isn't excluding logs

### Can't delete a user?
**Solution**: Some users are protected
- You cannot delete yourself
- You cannot delete superuser accounts
- Check if user has associated sales (they're protected)

## 📱 Mobile Friendly

All new features are fully responsive and work on:
- Desktop computers
- Tablets
- Mobile phones

## 🆘 Need Help?

### Documentation
- `USER_MANAGEMENT.md` - Detailed feature documentation
- `SETUP_USER_MANAGEMENT.md` - Technical setup guide
- This file - Quick start guide

### Support
1. Check the documentation files
2. Review activity logs for errors
3. Check Django admin for data issues
4. Verify user permissions

## 🎉 You're All Set!

Your POS system now has professional user management and business configuration. Start by:

1. **Configure your business settings** - Make it yours!
2. **Create user accounts** - Add your team
3. **Assign roles** - Give appropriate access
4. **Test the features** - Try everything out
5. **Monitor activity** - Keep track of what's happening

Enjoy your enhanced POS system! 🚀
