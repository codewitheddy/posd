from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from pos.models import Product, Sale, Purchase, Supplier, StockAdjustment


class Command(BaseCommand):
    help = 'Set up user roles and permissions for POS system'

    def handle(self, *args, **kwargs):
        # Create groups
        manager_group, _ = Group.objects.get_or_create(name='Manager')
        cashier_group, _ = Group.objects.get_or_create(name='Cashier')
        stock_manager_group, _ = Group.objects.get_or_create(name='Stock Manager')

        # Get content types
        product_ct = ContentType.objects.get_for_model(Product)
        sale_ct = ContentType.objects.get_for_model(Sale)
        purchase_ct = ContentType.objects.get_for_model(Purchase)
        supplier_ct = ContentType.objects.get_for_model(Supplier)
        stock_ct = ContentType.objects.get_for_model(StockAdjustment)

        # Manager - Full access to everything
        manager_permissions = Permission.objects.filter(
            content_type__in=[product_ct, sale_ct, purchase_ct, supplier_ct, stock_ct]
        )
        manager_group.permissions.set(manager_permissions)

        # Cashier - Can only make sales and view products
        cashier_permissions = Permission.objects.filter(
            content_type=sale_ct, codename__in=['add_sale', 'view_sale']
        ) | Permission.objects.filter(
            content_type=product_ct, codename='view_product'
        )
        cashier_group.permissions.set(cashier_permissions)

        # Stock Manager - Can manage products, stock, and purchases
        stock_permissions = Permission.objects.filter(
            content_type__in=[product_ct, stock_ct, purchase_ct, supplier_ct]
        )
        stock_manager_group.permissions.set(stock_permissions)

        self.stdout.write(self.style.SUCCESS('Successfully set up roles:'))
        self.stdout.write(self.style.SUCCESS('  - Manager: Full access'))
        self.stdout.write(self.style.SUCCESS('  - Cashier: Sales only'))
        self.stdout.write(self.style.SUCCESS('  - Stock Manager: Inventory & purchases'))
