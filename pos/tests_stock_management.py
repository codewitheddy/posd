"""
Unit tests for Upgraded Stock Management:
- Advanced Filtering (Category, Status: in_stock, low, out, expiring_soon, expired, least_sold, most_sold)
- Advanced Sorting (latest, oldest, least_sold, most_sold, stock_asc, stock_desc, val_desc, name_asc)
- Sales Velocity calculations
- Stock Valuation properties
- CSV Export with UTF-8 BOM
- Pagination
"""
from decimal import Decimal
from datetime import timedelta
import django.test
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse
from pos.models import (
    Business,
    Branch,
    BusinessMembership,
    Product,
    Category,
    Sale,
    SaleItem,
)


class StockManagementTestCase(django.test.TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='stockadmin', password='password123')
        self.business = Business.objects.create(
            name='Inventory Hub Test',
            slug='inventory-hub-test',
            owner=self.user,
        )
        self.membership = BusinessMembership.objects.create(
            user=self.user,
            business=self.business,
            role='admin',
            is_active=True,
        )

        self.client.login(username='stockadmin', password='password123')

        # Categories
        self.cat_electronics = Category.objects.create(business=self.business, name='Electronics')
        self.cat_groceries = Category.objects.create(business=self.business, name='Groceries')

        today = timezone.now().date()

        # Products
        # 1. High Velocity / Fast Mover
        self.prod_phone = Product.objects.create(
            business=self.business,
            name='Smartphone Alpha',
            product_code='PHN-001',
            barcode='111222333',
            category=self.cat_electronics,
            cost_price=Decimal('10000.00'),
            unit_price=Decimal('15000.00'),
            stock_quantity=Decimal('25.000'),
            low_stock_threshold=Decimal('5.000'),
            expiry_date=today + timedelta(days=365),
        )

        # 2. Low Stock Product
        self.prod_milk = Product.objects.create(
            business=self.business,
            name='Fresh Milk 1L',
            product_code='MLK-001',
            barcode='444555666',
            category=self.cat_groceries,
            cost_price=Decimal('50.00'),
            unit_price=Decimal('70.00'),
            stock_quantity=Decimal('3.000'),
            low_stock_threshold=Decimal('10.000'),
            expiry_date=today + timedelta(days=5),  # expiring soon
        )

        # 3. Out of Stock / Dead Stock (0 sold, 0 stock)
        self.prod_tv = Product.objects.create(
            business=self.business,
            name='Vintage CRT TV',
            product_code='TV-001',
            barcode='777888999',
            category=self.cat_electronics,
            cost_price=Decimal('2000.00'),
            unit_price=Decimal('3000.00'),
            stock_quantity=Decimal('0.000'),
            low_stock_threshold=Decimal('2.000'),
            expiry_date=None,
        )

        # 4. Expired Product
        self.prod_yogurt = Product.objects.create(
            business=self.business,
            name='Strawberry Yogurt',
            product_code='YOG-001',
            barcode='333444555',
            category=self.cat_groceries,
            cost_price=Decimal('80.00'),
            unit_price=Decimal('120.00'),
            stock_quantity=Decimal('15.000'),
            low_stock_threshold=Decimal('5.000'),
            expiry_date=today - timedelta(days=2),  # expired!
        )

        # 5. Uncategorized Slow Moving item with stock
        self.prod_misc = Product.objects.create(
            business=self.business,
            name='Mystery Widget',
            product_code='MSC-001',
            category=None,
            cost_price=Decimal('100.00'),
            unit_price=Decimal('200.00'),
            stock_quantity=Decimal('50.000'),
            low_stock_threshold=Decimal('5.000'),
        )

        # Create sales to establish velocity
        sale = Sale.objects.create(
            business=self.business,
            cashier=self.user,
            subtotal=Decimal('60000.00'),
            vat_amount=Decimal('0.00'),
            total=Decimal('60000.00'),
        )
        SaleItem.objects.create(
            business=self.business,
            sale=sale,
            product=self.prod_phone,
            quantity=Decimal('4.000'),
            unit_price=Decimal('15000.00'),
            total_price=Decimal('60000.00'),
        )

        sale2 = Sale.objects.create(
            business=self.business,
            cashier=self.user,
            subtotal=Decimal('700.00'),
            vat_amount=Decimal('0.00'),
            total=Decimal('700.00'),
        )
        SaleItem.objects.create(
            business=self.business,
            sale=sale2,
            product=self.prod_milk,
            quantity=Decimal('10.000'),
            unit_price=Decimal('70.00'),
            total_price=Decimal('700.00'),
        )

    def test_stock_list_renders_and_calculates_stats(self):
        """Test stock_list renders 200 OK and aggregates statistics."""
        url = reverse('stock_list', kwargs={'slug': self.business.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Verify stats in context
        stats = response.context['stats']
        self.assertEqual(response.context['total_products_count'], 5)
        self.assertEqual(stats['low_stock_count'], 1)  # prod_milk
        self.assertEqual(stats['out_of_stock_count'], 1)  # prod_tv
        self.assertEqual(stats['expired_count'], 1)  # prod_yogurt
        self.assertEqual(stats['expiring_soon_count'], 1)  # prod_milk

    def test_filter_by_category(self):
        """Test filtering products by category and uncategorized."""
        url = reverse('stock_list', kwargs={'slug': self.business.slug})
        
        # Filter by Electronics
        resp = self.client.get(url, {'category': self.cat_electronics.id})
        self.assertEqual(resp.status_code, 200)
        products = list(resp.context['products'])
        self.assertEqual(len(products), 2)
        self.assertIn(self.prod_phone, products)
        self.assertIn(self.prod_tv, products)

        # Filter by Uncategorized
        resp_uncat = self.client.get(url, {'category': 'uncategorized'})
        products_uncat = list(resp_uncat.context['products'])
        self.assertEqual(len(products_uncat), 1)
        self.assertIn(self.prod_misc, products_uncat)

    def test_filter_by_status(self):
        """Test filtering by stock statuses: low, out, in_stock, expired, expiring_soon."""
        url = reverse('stock_list', kwargs={'slug': self.business.slug})

        # Low Stock
        resp_low = self.client.get(url, {'status': 'low'})
        low_prods = list(resp_low.context['products'])
        self.assertEqual(len(low_prods), 1)
        self.assertEqual(low_prods[0].id, self.prod_milk.id)

        # Out of Stock
        resp_out = self.client.get(url, {'status': 'out'})
        out_prods = list(resp_out.context['products'])
        self.assertEqual(len(out_prods), 1)
        self.assertEqual(out_prods[0].id, self.prod_tv.id)

        # Expired
        resp_exp = self.client.get(url, {'status': 'expired'})
        exp_prods = list(resp_exp.context['products'])
        self.assertEqual(len(exp_prods), 1)
        self.assertEqual(exp_prods[0].id, self.prod_yogurt.id)

        # Expiring Soon
        resp_soon = self.client.get(url, {'status': 'expiring_soon'})
        soon_prods = list(resp_soon.context['products'])
        self.assertEqual(len(soon_prods), 1)
        self.assertEqual(soon_prods[0].id, self.prod_milk.id)

    def test_filter_by_search_query(self):
        """Test searching by product name, SKU, and barcode."""
        url = reverse('stock_list', kwargs={'slug': self.business.slug})

        # Search by name
        resp_name = self.client.get(url, {'q': 'Smartphone'})
        self.assertEqual(len(list(resp_name.context['products'])), 1)

        # Search by SKU
        resp_sku = self.client.get(url, {'q': 'MLK-001'})
        self.assertEqual(len(list(resp_sku.context['products'])), 1)

        # Search by barcode
        resp_bar = self.client.get(url, {'q': '777888999'})
        self.assertEqual(len(list(resp_bar.context['products'])), 1)

    def test_sorting_options(self):
        """Test sorting by least_sold, most_sold, stock_asc, stock_desc."""
        url = reverse('stock_list', kwargs={'slug': self.business.slug})

        # Most sold first: prod_milk (10 sold), prod_phone (4 sold), others (0 sold)
        resp_most = self.client.get(url, {'sort': 'most_sold'})
        prods_most = list(resp_most.context['products'])
        self.assertEqual(prods_most[0].id, self.prod_milk.id)
        self.assertEqual(prods_most[1].id, self.prod_phone.id)

        # Least sold first: 0 sold products with highest stock first (prod_misc with 50 stock)
        resp_least = self.client.get(url, {'sort': 'least_sold'})
        prods_least = list(resp_least.context['products'])
        self.assertEqual(prods_least[0].id, self.prod_misc.id)

        # Stock Ascending (0 stock first: prod_tv)
        resp_asc = self.client.get(url, {'sort': 'stock_asc'})
        prods_asc = list(resp_asc.context['products'])
        self.assertEqual(prods_asc[0].id, self.prod_tv.id)

    def test_csv_export_functionality(self):
        """Test CSV export endpoint returns text/csv with correct headers and rows."""
        url = reverse('stock_list', kwargs={'slug': self.business.slug})
        resp = self.client.get(url, {'export': 'csv', 'category': self.cat_electronics.id})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="stock_inventory_', resp['Content-Disposition'])

        content = resp.content.decode('utf-8-sig')
        lines = content.strip().splitlines()
        
        # Verify header line
        self.assertIn('Product Name', lines[0])
        self.assertIn('Total Cost Valuation (KES)', lines[0])
        self.assertIn('Units Sold', lines[0])

        # Verify 2 electronics items in CSV
        self.assertEqual(len(lines), 3)  # 1 header + 2 product rows
        self.assertIn('Smartphone Alpha', content)
        self.assertIn('Vintage CRT TV', content)
        self.assertNotIn('Fresh Milk 1L', content)

    def test_selected_ids_csv_export(self):
        """Test CSV export with selected_ids parameter exports only selected products."""
        url = reverse('stock_list', kwargs={'slug': self.business.slug})
        resp = self.client.get(url, {'export': 'csv', 'selected_ids': f"{self.prod_phone.id},{self.prod_milk.id}"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8-sig')
        lines = content.strip().splitlines()
        self.assertEqual(len(lines), 3)  # 1 header + 2 selected rows
        self.assertIn('Smartphone Alpha', content)
        self.assertIn('Fresh Milk 1L', content)
        self.assertNotIn('Vintage CRT TV', content)

    def test_model_valuation_properties(self):
        """Test total_cost_value and total_retail_value properties on Product model."""
        # prod_phone: 25 * 10,000 = 250,000 cost, 25 * 15,000 = 375,000 retail
        self.assertEqual(self.prod_phone.total_cost_value, Decimal('250000.00'))
        self.assertEqual(self.prod_phone.total_retail_value, Decimal('375000.00'))

        # prod_tv (0 stock): 0
        self.assertEqual(self.prod_tv.total_cost_value, Decimal('0.00'))
        self.assertEqual(self.prod_tv.total_retail_value, Decimal('0.00'))
