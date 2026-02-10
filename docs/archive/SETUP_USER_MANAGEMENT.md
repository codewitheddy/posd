# Setup Guide: User Management & Business Settings

## Quick Setup Steps

### 1. Run Migrations
Create the new database tables:
```bash
python manage.py makemigrations
python manage.py migrate
```

### 2. Initialize Business Settings
```bash
python manage.py setup_business
```

### 3. Create User Profiles for Existing Users
If you have existing users, create profiles for them:
```bash
python manage.py shell
```

Then run:
```python
from django.contrib.auth.models import User
from pos.models import UserProfile

for user in User.objects.all():
    UserProfile.objects.get_or_create(user=user)
    print(f"Profile created for {user.username}")
```

### 4. Access the Features

#### User Management
1. Login as admin/manager
2. Navigate to: Admin > User Management
3. Create new users or edit existing ones

#### Business Settings
1. Login as admin/manager
2. Navigate to: Admin > Business Settings
3. Configure your business information

#### Activity Log
1. Login as admin/manager
2. Navigate to: Admin > Activity Log
3. View system activities

#### User Profile
1. Any logged-in user can access
2. Click username > My Profile
3. Update personal information

## Testing the Features

### Test User Management
1. Create a new user:
   - Username: testcashier
   - Password: test123
   - Role: Cashier
   - Employee ID: EMP001

2. Edit the user:
   - Add phone number
   - Add address
   - Change role

3. View user statistics:
   - Check total sales
   - Check total revenue

### Test Business Settings
1. Update business information:
   - Business name: "My Retail Store"
   - Phone: "+254 123 456 789"
   - Address: "123 Main Street, Nairobi"

2. Configure tax settings:
   - VAT Rate: 16%
   - Enable VAT: Yes

3. Customize receipts:
   - Header: "Welcome to My Store!"
   - Footer: "Thank you for shopping with us!"

4. Set stock defaults:
   - Low stock threshold: 10
   - Expiry alert days: 3

### Test Activity Log
1. Perform various actions:
   - Create a product
   - Make a sale
   - Adjust stock
   - Update settings

2. View activity log:
   - Filter by user
   - Filter by action type
   - Filter by date

3. Check logged information:
   - User who performed action
   - Action type
   - Description
   - IP address
   - Timestamp

## Troubleshooting

### Issue: Cannot access User Management
**Solution**: Ensure you're logged in as a Manager or Superuser
```bash
python manage.py shell
```
```python
from django.contrib.auth.models import User, Group

# Make user a manager
user = User.objects.get(username='your_username')
manager_group = Group.objects.get(name='Manager')
user.groups.add(manager_group)
```

### Issue: Business Settings not showing
**Solution**: Initialize business settings
```bash
python manage.py setup_business
```

### Issue: Activity logs not appearing
**Solution**: Activities are logged automatically. Ensure:
1. You're performing logged actions (create, update, delete, etc.)
2. You're logged in as a user
3. The ActivityLog model is properly migrated

### Issue: User profile missing
**Solution**: Create profile manually
```bash
python manage.py shell
```
```python
from django.contrib.auth.models import User
from pos.models import UserProfile

user = User.objects.get(username='username')
UserProfile.objects.create(user=user)
```

## Security Checklist

- [ ] All users have strong passwords
- [ ] Only managers have access to user management
- [ ] Only managers have access to business settings
- [ ] Activity logging is working
- [ ] Users cannot delete themselves
- [ ] Superuser accounts are protected
- [ ] Password changes require confirmation

## Next Steps

1. **Configure Business Settings**: Set up your business information
2. **Create User Accounts**: Add accounts for all staff members
3. **Assign Roles**: Give appropriate permissions to each user
4. **Test Access Control**: Verify users can only access what they should
5. **Monitor Activity**: Regularly check activity logs for unusual behavior

## Integration with Existing Features

The new modules integrate seamlessly with existing features:

### Sales
- Sales are now tracked by cashier
- Activity logs record all sales
- Cashier reports show per-user statistics

### Stock Management
- Stock adjustments are logged
- Default thresholds from business settings
- Expiry alerts use business settings

### Purchases
- Purchase activities are logged
- Supplier management unchanged
- Stock updates tracked in activity log

### Reports
- Cashier reports show user performance
- Activity log provides audit trail
- Sales reports include user information

## Customization

### Adding Custom Activity Types
Edit `pos/models.py`:
```python
class ActivityLog(models.Model):
    ACTION_TYPES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('sale', 'Sale'),
        ('stock_adjust', 'Stock Adjustment'),
        ('purchase', 'Purchase'),
        ('settings', 'Settings Change'),
        ('custom', 'Custom Action'),  # Add your custom type
    ]
```

### Adding Custom User Profile Fields
Edit `pos/models.py`:
```python
class UserProfile(models.Model):
    # ... existing fields ...
    department = models.CharField(max_length=100, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # Add your custom fields
```

Then run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

### Adding Custom Business Settings
Edit `pos/models.py`:
```python
class BusinessSettings(models.Model):
    # ... existing fields ...
    enable_loyalty_program = models.BooleanField(default=False)
    loyalty_points_rate = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    # Add your custom settings
```

Then run migrations and update the template.

## Support

For issues or questions:
1. Check the USER_MANAGEMENT.md documentation
2. Review the activity log for errors
3. Check Django admin for model data
4. Verify migrations are applied
5. Check user permissions and roles
