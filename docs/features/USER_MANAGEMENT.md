# User Management & Business Settings Module

## Overview
Complete user management and business settings system for the POS application with role-based access control, activity logging, and comprehensive business configuration.

## Features

### 1. User Management
- **User CRUD Operations**: Create, read, update, and delete users
- **User Profiles**: Extended user information including:
  - Employee ID
  - Phone number
  - Address
  - Date of birth
  - Hire date
  - Custom notes
- **Role Assignment**: Assign users to groups (Manager, Cashier, Stock Manager)
- **User Statistics**: Track sales and revenue per user
- **Password Management**: Change passwords with validation
- **Status Management**: Activate/deactivate users

### 2. Business Settings
Comprehensive business configuration including:

#### Business Information
- Business name
- Address
- Phone, email, website
- Tax/VAT registration number

#### Tax Settings
- VAT/Tax rate configuration
- Enable/disable VAT calculation

#### Currency Settings
- Currency symbol (KES, $, €, £, etc.)
- Currency position (before/after amount)

#### Receipt Settings
- Custom header text
- Custom footer text
- Logo display option

#### Stock Management Settings
- Default low stock threshold
- Enable/disable low stock alerts
- Default expiry alert days
- Enable/disable expiry alerts

#### System Settings
- Allow negative stock
- Require product code
- Auto-generate product codes

### 3. Activity Log
- Track all system activities
- Log user actions (create, update, delete, login, logout, sales, etc.)
- IP address tracking
- Filterable by user, action type, and date
- Paginated view (50 logs per page)

## Database Models

### UserProfile
Extended user profile with additional fields:
- `user` - OneToOne relationship with Django User
- `phone` - Contact phone number
- `address` - Physical address
- `employee_id` - Unique employee identifier
- `date_of_birth` - Date of birth
- `hire_date` - Employment start date
- `is_active` - Active status
- `notes` - Additional notes

### BusinessSettings
Singleton model for global business settings:
- Business information fields
- Tax and currency settings
- Receipt customization
- Stock management defaults
- System preferences

### ActivityLog
Track all system activities:
- `user` - User who performed the action
- `action_type` - Type of action (create, update, delete, etc.)
- `model_name` - Model affected
- `object_id` - ID of affected object
- `description` - Action description
- `ip_address` - User's IP address
- `timestamp` - When action occurred

## URLs

### User Management
- `/users/` - List all users
- `/users/create/` - Create new user
- `/users/<id>/edit/` - Edit user
- `/users/<id>/delete/` - Delete user
- `/profile/` - View/edit own profile

### Business Settings
- `/settings/` - View/edit business settings

### Activity Log
- `/activity-log/` - View activity logs with filters

## Access Control

### Manager Required
The following views require Manager or Superuser role:
- User list, create, edit, delete
- Business settings
- Activity log

### All Authenticated Users
- View/edit own profile

## Usage

### Creating a User
1. Navigate to Admin > User Management
2. Click "Add New User"
3. Fill in required fields:
   - Username (required)
   - Password (required)
   - Email, name, role (optional)
4. Add profile information (employee ID, phone, etc.)
5. Set user status (active/inactive)
6. Click "Create User"

### Editing Business Settings
1. Navigate to Admin > Business Settings
2. Update any section:
   - Business Information
   - Tax Settings
   - Currency Settings
   - Receipt Settings
   - Stock Management Settings
   - System Settings
3. Click "Save Settings"

### Viewing Activity Logs
1. Navigate to Admin > Activity Log
2. Use filters to narrow down logs:
   - Filter by user
   - Filter by action type
   - Filter by date
3. View paginated results

### Editing Own Profile
1. Click on username in top-right corner
2. Select "My Profile"
3. Update personal information
4. Change password if needed
5. Click "Update Profile"

## Activity Logging

Activities are automatically logged for:
- User creation, updates, deletion
- Business settings changes
- Sales transactions
- Stock adjustments
- Purchase orders
- Login/logout events

To manually log an activity:
```python
from pos.models import ActivityLog

ActivityLog.log_activity(
    user=request.user,
    action_type='create',
    model_name='Product',
    object_id=product.id,
    description='Created new product: Product Name',
    request=request
)
```

## Navigation

New navigation items added to the base template:
- **Admin dropdown** (Manager/Superuser only):
  - User Management
  - Business Settings
  - Activity Log
  - Django Admin
- **User dropdown**:
  - My Profile
  - Logout

## Security Features

1. **Role-Based Access**: Only managers can access user management and settings
2. **Self-Protection**: Users cannot delete their own accounts
3. **Superuser Protection**: Cannot delete superuser accounts
4. **Password Validation**: Confirm password required for changes
5. **Activity Tracking**: All actions logged with IP addresses
6. **Singleton Settings**: Only one business settings instance allowed

## Migration

To apply the new models:
```bash
python manage.py makemigrations
python manage.py migrate
```

## Initial Setup

1. Run migrations to create new tables
2. Access Business Settings to configure your business
3. Create user accounts for your staff
4. Assign appropriate roles to users

## Future Enhancements

Potential improvements:
- User permissions at granular level
- Email notifications for activities
- Export activity logs to CSV
- User session management
- Two-factor authentication
- Password strength requirements
- User avatar uploads
- Business logo upload
- Multi-language support
- Audit trail for settings changes
