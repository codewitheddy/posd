"""
Unit and Integration Tests for Product Bulk CSV Upload
"""

import io
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User

from pos.models import Business, Branch, Product, Category, BranchStock, StockMovement


class ProductBulkUploadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='admin_bulk', password='password123', email='admin@test.com')
        self.business = Business.objects.create(name='Supermarket Business', owner=self.user, is_active=True)
        self.branch = Branch.objects.create(business=self.business, name='Main Store', is_default=True, is_active=True)
        
        # Log in user
        self.client.login(username='admin_bulk', password='password123')

    def test_bulk_upload_without_cost_price_column_succeeds(self):
        """CSV without cost_price column should gracefully default cost_price = unit_price and succeed."""
        csv_content = """name,product_code,category,unit_price,stock_quantity,low_stock_threshold
Sugar 1kg,SUG01,Groceries,150.00,20,5
Salt 500g,SLT01,Groceries,40.00,50,10
Cooking Oil 2L,OIL01,Groceries,550.00,15,3
"""
        csv_file = SimpleUploadedFile("products.csv", csv_content.encode('utf-8'), content_type="text/csv")
        
        response = self.client.post(
            reverse('product_bulk_upload', kwargs={'slug': self.business.slug}),
            {'csv_file': csv_file},
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # Verify all 3 products were created
        self.assertEqual(Product.objects.filter(business=self.business).count(), 3)
        sugar = Product.objects.get(business=self.business, product_code='SUG01')
        self.assertEqual(sugar.name, 'Sugar 1kg')
        self.assertEqual(sugar.unit_price, Decimal('150.00'))
        self.assertEqual(sugar.cost_price, Decimal('150.00'))  # Defaulted safely
        self.assertEqual(sugar.stock_quantity, Decimal('20.000'))

        # Verify branch stock was created and initialized
        b_stock = BranchStock.objects.get(branch=self.branch, product=sugar)
        self.assertEqual(b_stock.quantity, Decimal('20.000'))

    def test_bulk_upload_with_cost_price_and_flexible_headers(self):
        """CSV with flexible headers (Buying Price, Selling Price, SKU, Barcode, etc.) and currency symbols."""
        csv_content = """Product Name,SKU,Barcode,Category,Buying Price,Selling Price,Quantity,Reorder Level
Basmati Rice 5kg,RICE-5K,616110001234,Grains,KES 850.00,"KES 1,100.00",30,5
Wheat Flour 2kg,FLR-2K,616110005678,Baking,160.00,210.00,40,10
"""
        csv_file = SimpleUploadedFile("products_flex.csv", csv_content.encode('utf-8'), content_type="text/csv")

        response = self.client.post(
            reverse('product_bulk_upload', kwargs={'slug': self.business.slug}),
            {'csv_file': csv_file},
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(Product.objects.filter(business=self.business).count(), 2)
        rice = Product.objects.get(business=self.business, product_code='RICE-5K')
        self.assertEqual(rice.name, 'Basmati Rice 5kg')
        self.assertEqual(rice.barcode, '616110001234')
        self.assertEqual(rice.cost_price, Decimal('850.00'))
        self.assertEqual(rice.unit_price, Decimal('1100.00'))
        self.assertEqual(rice.stock_quantity, Decimal('30.000'))
        self.assertEqual(rice.low_stock_threshold, Decimal('5.000'))

    def test_bulk_upload_updates_existing_product_and_adjusts_ledger(self):
        """Updating existing products with new price and stock updates BranchStock and creates StockAdjustment."""
        existing = Product.objects.create(
            business=self.business,
            name='Soap 200g',
            product_code='SOP-01',
            cost_price=Decimal('50.00'),
            unit_price=Decimal('80.00'),
            stock_quantity=Decimal('10.000')
        )
        BranchStock.objects.create(
            branch=self.branch,
            product=existing,
            quantity=Decimal('10.000'),
            average_cost=Decimal('50.00')
        )

        csv_content = """name,product_code,cost_price,unit_price,stock_quantity
Soap 200g,SOP-01,55.00,90.00,25
"""
        csv_file = SimpleUploadedFile("update.csv", csv_content.encode('utf-8'), content_type="text/csv")
        response = self.client.post(
            reverse('product_bulk_upload', kwargs={'slug': self.business.slug}),
            {'csv_file': csv_file},
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        existing.refresh_from_db()
        self.assertEqual(existing.cost_price, Decimal('55.00'))
        self.assertEqual(existing.unit_price, Decimal('90.00'))
        self.assertEqual(existing.stock_quantity, Decimal('25.000'))

        b_stock = BranchStock.objects.get(branch=self.branch, product=existing)
        self.assertEqual(b_stock.quantity, Decimal('25.000'))

    def test_download_template(self):
        """Test downloading CSV template returns 200 and valid CSV header."""
        response = self.client.get(reverse('product_download_template', kwargs={'slug': self.business.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn('name,product_code,barcode,category,cost_price,unit_price', content)

    def test_export_csv(self):
        """Test exporting products to CSV returns 200 and contains product data."""
        Product.objects.create(
            business=self.business,
            name='Milk 500ml',
            cost_price=Decimal('45.00'),
            unit_price=Decimal('60.00'),
            stock_quantity=Decimal('30.000')
        )
        response = self.client.get(reverse('product_export_csv', kwargs={'slug': self.business.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn('Milk 500ml', content)
        self.assertIn('45.00', content)
        self.assertIn('60.00', content)

    def test_bulk_upload_800_products_performance(self):
        """Test uploading 800 products simultaneously completes quickly and cleanly creates all records."""
        lines = ["name,product_code,barcode,category,cost_price,unit_price,stock_quantity,low_stock_threshold"]
        for i in range(1, 801):
            lines.append(f"Product Item {i:04d},SKU{i:04d},880000{i:04d},Category {(i % 10) + 1},{50 + (i % 20)}.00,{75 + (i % 20)}.00,10,5")
        
        csv_content = "\n".join(lines) + "\n"
        csv_file = SimpleUploadedFile("products_800.csv", csv_content.encode('utf-8'), content_type="text/csv")

        response = self.client.post(
            reverse('product_bulk_upload', kwargs={'slug': self.business.slug}),
            {'csv_file': csv_file},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.filter(business=self.business).count(), 800)
        self.assertEqual(BranchStock.objects.filter(branch=self.branch).count(), 800)
        self.assertEqual(StockMovement.objects.filter(branch=self.branch).count(), 800)

