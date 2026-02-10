from django.core.management.base import BaseCommand
from pos.models import Category, Product


class Command(BaseCommand):
    help = 'Seed database with sample products and categories'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding database...')

        # Create categories
        categories_data = [
            'Beverages',
            'Snacks',
            'Groceries',
            'Personal Care',
            'Household',
        ]

        categories = {}
        for cat_name in categories_data:
            cat, created = Category.objects.get_or_create(name=cat_name)
            categories[cat_name] = cat
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created category: {cat_name}'))

        # Create products with product codes and stock
        products_data = [
            ('Coca Cola 500ml', 'BEV001', 'Beverages', 80, 50),
            ('Fanta Orange 500ml', 'BEV002', 'Beverages', 80, 45),
            ('Sprite 500ml', 'BEV003', 'Beverages', 80, 40),
            ('Bottled Water 500ml', 'BEV004', 'Beverages', 50, 100),
            ('Milk 1L', 'BEV005', 'Beverages', 120, 30),
            ('Bread', 'GRO001', 'Groceries', 55, 25),
            ('Sugar 1kg', 'GRO002', 'Groceries', 150, 20),
            ('Rice 2kg', 'GRO003', 'Groceries', 250, 15),
            ('Cooking Oil 1L', 'GRO004', 'Groceries', 300, 12),
            ('Tea Leaves 250g', 'GRO005', 'Groceries', 180, 18),
            ('Crisps', 'SNK001', 'Snacks', 50, 60),
            ('Biscuits', 'SNK002', 'Snacks', 40, 55),
            ('Chocolate Bar', 'SNK003', 'Snacks', 100, 35),
            ('Peanuts 100g', 'SNK004', 'Snacks', 60, 40),
            ('Soap Bar', 'PER001', 'Personal Care', 45, 30),
            ('Toothpaste', 'PER002', 'Personal Care', 120, 25),
            ('Shampoo 200ml', 'PER003', 'Personal Care', 250, 20),
            ('Tissue Paper', 'HOU001', 'Household', 80, 35),
            ('Detergent 500g', 'HOU002', 'Household', 180, 22),
            ('Matchbox', 'HOU003', 'Household', 10, 50),
        ]

        for name, code, category_name, price, stock in products_data:
            product, created = Product.objects.get_or_create(
                name=name,
                defaults={
                    'product_code': code,
                    'category': categories[category_name],
                    'unit_price': price,
                    'stock_quantity': stock,
                    'low_stock_threshold': 10
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created product: {name} (Code: {code}, Stock: {stock})'))
            else:
                # Update existing products with codes and stock if they don't have them
                updated = False
                if not product.product_code:
                    product.product_code = code
                    updated = True
                if product.stock_quantity == 0:
                    product.stock_quantity = stock
                    updated = True
                if updated:
                    product.save()
                    self.stdout.write(self.style.SUCCESS(f'Updated product: {name}'))

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
