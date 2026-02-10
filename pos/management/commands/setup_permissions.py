from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from pos.models import Product, Sale, Customer, Supplier, Purchase, StockAdjustment


class Command(BaseCommand):
    help = 'Setup user roles and permissions for POS system'

    def handle(self, *args, **options):
        self.stdout.write('Setting up user roles and permissions...')
        
        # Create user groups/roles
        roles = {
            'Administrator': {
                'description': 'Full system access - can do everything',
                'permissions': 'all'
            },
            'Manager': {
                'description': 'Management access - reports, user management, settings',
                'permissions': [
                    # User management
                    'auth.add_user', 'auth.change_user', 'auth.delete_user', 'auth.view_user',
                    'auth.add_group', 'auth.change_group', 'auth.delete_group', 'auth.view_group',
                    
                    # Product management
                    'pos.add_product', 'pos.change_product', 'pos.delete_product', 'pos.view_product',
                    'pos.add_category', 'pos.change_category', 'pos.delete_category', 'pos.view_category',
                    
                    # Sales and customers
                    'pos.add_sale', 'pos.change_sale', 'pos.view_sale',
                    'pos.add_customer', 'pos.change_customer', 'pos.delete_customer', 'pos.view_customer',
                    
                    # Suppliers and purchases
                    'pos.add_supplier', 'pos.change_supplier', 'pos.delete_supplier', 'pos.view_supplier',
                    'pos.add_purchase', 'pos.change_purchase', 'pos.delete_purchase', 'pos.view_purchase',
                    
                    # Stock management
                    'pos.add_stockadjustment', 'pos.change_stockadjustment', 'pos.view_stockadjustment',
                    
                    # Business settings
                    'pos.change_businesssettings', 'pos.view_businesssettings',
                    
                    # Activity logs
                    'pos.view_activitylog',
                    
                    # Loyalty program
                    'pos.add_loyaltyreward', 'pos.change_loyaltyreward', 'pos.delete_loyaltyreward', 'pos.view_loyaltyreward',
                    'pos.view_loyaltytransaction', 'pos.view_loyaltyredemption',
                ]
            },
            'Stock Manager': {
                'description': 'Inventory and stock management',
                'permissions': [
                    # Product management
                    'pos.add_product', 'pos.change_product', 'pos.view_product',
                    'pos.add_category', 'pos.change_category', 'pos.view_category',
                    
                    # Stock management
                    'pos.add_stockadjustment', 'pos.change_stockadjustment', 'pos.view_stockadjustment',
                    
                    # Suppliers and purchases
                    'pos.add_supplier', 'pos.change_supplier', 'pos.view_supplier',
                    'pos.add_purchase', 'pos.change_purchase', 'pos.view_purchase',
                    
                    # Sales (view only)
                    'pos.view_sale',
                    
                    # Customers (view only)
                    'pos.view_customer',
                ]
            },
            'Cashier': {
                'description': 'Point of sale operations',
                'permissions': [
                    # Sales operations
                    'pos.add_sale', 'pos.view_sale',
                    
                    # Products (view only)
                    'pos.view_product', 'pos.view_category',
                    
                    # Customers
                    'pos.add_customer', 'pos.change_customer', 'pos.view_customer',
                    
                    # Loyalty program (basic)
                    'pos.view_loyaltytransaction',
                ]
            },
            'Sales Associate': {
                'description': 'Sales and customer service',
                'permissions': [
                    # Sales operations
                    'pos.add_sale', 'pos.view_sale',
                    
                    # Products (view only)
                    'pos.view_product', 'pos.view_category',
                    
                    # Customers
                    'pos.add_customer', 'pos.change_customer', 'pos.view_customer',
                    
                    # Loyalty program
                    'pos.view_loyaltytransaction', 'pos.view_loyaltyreward',
                ]
            },
            'Viewer': {
                'description': 'Read-only access to reports and data',
                'permissions': [
                    # View only permissions
                    'pos.view_product', 'pos.view_category',
                    'pos.view_sale', 'pos.view_customer',
                    'pos.view_supplier', 'pos.view_purchase',
                    'pos.view_stockadjustment',
                    'pos.view_loyaltytransaction', 'pos.view_loyaltyreward',
                ]
            }
        }
        
        created_groups = 0
        updated_groups = 0
        
        for role_name, role_data in roles.items():
            group, created = Group.objects.get_or_create(name=role_name)
            
            if created:
                created_groups += 1
                self.stdout.write(f'✓ Created role: {role_name}')
            else:
                updated_groups += 1
                self.stdout.write(f'✓ Updated role: {role_name}')
            
            # Clear existing permissions
            group.permissions.clear()
            
            # Add permissions
            if role_data['permissions'] == 'all':
                # Administrator gets all permissions
                all_permissions = Permission.objects.all()
                group.permissions.set(all_permissions)
                self.stdout.write(f'  → Added ALL permissions ({all_permissions.count()} permissions)')
            else:
                # Add specific permissions
                permissions_added = 0
                for perm_code in role_data['permissions']:
                    try:
                        app_label, codename = perm_code.split('.')
                        permission = Permission.objects.get(
                            content_type__app_label=app_label,
                            codename=codename
                        )
                        group.permissions.add(permission)
                        permissions_added += 1
                    except Permission.DoesNotExist:
                        self.stdout.write(f'  ⚠ Permission not found: {perm_code}')
                    except ValueError:
                        self.stdout.write(f'  ⚠ Invalid permission format: {perm_code}')
                
                self.stdout.write(f'  → Added {permissions_added} permissions')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'✅ Setup complete!'))
        self.stdout.write(f'Created {created_groups} new roles')
        self.stdout.write(f'Updated {updated_groups} existing roles')
        self.stdout.write('')
        self.stdout.write('Available roles:')
        for role_name, role_data in roles.items():
            self.stdout.write(f'  • {role_name}: {role_data["description"]}')
        
        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write('1. Assign roles to users in General Admin')
        self.stdout.write('2. Test permissions with different user accounts')
        self.stdout.write('3. Adjust permissions as needed')