"""
Automated tests for Bulk Actions on Admin Products List and Django Admin.
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.admin.sites import site

from pos.models import (
    Business, BusinessMembership, Branch, Category, Brand, Product,
    Sale, SaleItem, Purchase, PurchaseItem, VATCode, Customer, ActivityLog
)
from pos.admin import ProductAdmin


class ProductBulkActionTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Admin user and business setup
        self.user = User.objects.create_user(
            username="bulk_admin",
            password="password123!",
            is_staff=True,
            is_superuser=True
        )

        self.business = Business.objects.first()
        if not self.business:
            self.business = Business.objects.create(
                name="Retail Store",
                slug="retail-store",
                owner=self.user,
                is_active=True
            )
        else:
            self.business.owner = self.user
            self.business.save()

        BusinessMembership.objects.get_or_create(
            user=self.user,
            business=self.business,
            defaults={'role': 'owner'}
        )

        # Other business for cross-business isolation test
        self.other_user = User.objects.create_user(
            username="other_admin",
            password="password123!"
        )
        self.other_business = Business.objects.create(
            name="Other Store",
            slug="other-store",
            owner=self.other_user,
            is_active=True
        )
        BusinessMembership.objects.create(
            user=self.other_user,
            business=self.other_business,
            role='owner'
        )

        # Categories & Brands
        self.cat1 = Category.objects.create(business=self.business, name="Beverages")
        self.cat2 = Category.objects.create(business=self.business, name="Snacks")
        self.brand1 = Brand.objects.create(business=self.business, name="Nestle")
        self.brand2 = Brand.objects.create(business=self.business, name="Cadbury")

        # VAT Code
        self.vat_16 = VATCode.objects.create(
            business=self.business,
            code="A",
            name="Standard Rate",
            vat_rate=Decimal('16.00'),
            is_active=True
        )

        # Test Products
        self.prod1 = Product.objects.create(
            business=self.business,
            name="Coffee Jar",
            product_code="PRD-001",
            barcode="6001001",
            category=self.cat1,
            brand=self.brand1,
            cost_price=Decimal('100.00'),
            unit_price=Decimal('150.00'),
            wholesale_price=Decimal('130.00'),
            stock_quantity=Decimal('50.00'),
            is_active=True,
            tax_class='standard'
        )
        self.prod2 = Product.objects.create(
            business=self.business,
            name="Tea Bag Pack",
            product_code="PRD-002",
            barcode="6001002",
            category=self.cat1,
            brand=self.brand1,
            cost_price=Decimal('80.00'),
            unit_price=Decimal('120.00'),
            wholesale_price=Decimal('100.00'),
            stock_quantity=Decimal('30.00'),
            is_active=True,
            tax_class='standard'
        )
        self.prod3 = Product.objects.create(
            business=self.business,
            name="Milk Chocolate",
            product_code="PRD-003",
            barcode="6001003",
            category=self.cat2,
            brand=self.brand2,
            cost_price=Decimal('50.00'),
            unit_price=Decimal('80.00'),
            wholesale_price=Decimal('70.00'),
            stock_quantity=Decimal('20.00'),
            is_active=False,
            tax_class='zero_rated'
        )

        # Foreign product
        self.other_prod = Product.objects.create(
            business=self.other_business,
            name="Foreign Item",
            product_code="FOR-001",
            cost_price=Decimal('10.00'),
            unit_price=Decimal('20.00'),
            is_active=True
        )

        self.client.login(username="bulk_admin", password="password123!")

    def test_bulk_activate_and_deactivate(self):
        """Test bulk activation and deactivation of selected products"""
        url = reverse('product_bulk_action')
        
        # Deactivate prod1 and prod2
        response = self.client.post(url, {
            'bulk_action': 'deactivate',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'admin_password': 'password123!',
            'reason': 'Seasonal deactivation',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertFalse(self.prod1.is_active)
        self.assertFalse(self.prod2.is_active)

        # Activate all three
        response = self.client.post(url, {
            'bulk_action': 'activate',
            'selected_products': [self.prod1.pk, self.prod2.pk, self.prod3.pk],
            'admin_password': 'password123!',
            'reason': 'Bulk activation for sale',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.prod3.refresh_from_db()
        self.assertTrue(self.prod1.is_active)
        self.assertTrue(self.prod2.is_active)
        self.assertTrue(self.prod3.is_active)

    def test_bulk_action_security_rejections(self):
        """Test that bulk operations are rejected when password or reason is invalid/missing"""
        url = reverse('product_bulk_action')

        # 1. Missing password
        response = self.client.post(url, {
            'bulk_action': 'activate',
            'selected_products': [self.prod3.pk],
            'reason': 'Activating product',
        })
        self.assertEqual(response.status_code, 302)
        self.prod3.refresh_from_db()
        self.assertFalse(self.prod3.is_active)

        # 2. Wrong password
        response = self.client.post(url, {
            'bulk_action': 'activate',
            'selected_products': [self.prod3.pk],
            'admin_password': 'wrongpassword!',
            'reason': 'Activating product',
        })
        self.assertEqual(response.status_code, 302)
        self.prod3.refresh_from_db()
        self.assertFalse(self.prod3.is_active)

        # 3. Missing reason
        response = self.client.post(url, {
            'bulk_action': 'activate',
            'selected_products': [self.prod3.pk],
            'admin_password': 'password123!',
            'reason': '',
        })
        self.assertEqual(response.status_code, 302)
        self.prod3.refresh_from_db()
        self.assertFalse(self.prod3.is_active)

    def test_bulk_change_category(self):
        """Test moving selected products to a new category"""
        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'change_category',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'target_category': str(self.cat2.pk),
            'admin_password': 'password123!',
            'reason': 'Category restructuring',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertEqual(self.prod1.category, self.cat2)
        self.assertEqual(self.prod2.category, self.cat2)

        # Test uncategorizing
        response = self.client.post(url, {
            'bulk_action': 'change_category',
            'selected_products': [self.prod1.pk],
            'target_category': '',
            'admin_password': 'password123!',
            'reason': 'Uncategorize items',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.assertIsNone(self.prod1.category)

    def test_bulk_change_brand(self):
        """Test updating brand/department for selected products"""
        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'change_brand',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'target_brand': str(self.brand2.pk),
            'admin_password': 'password123!',
            'reason': 'Department rebrand',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertEqual(self.prod1.brand, self.brand2)
        self.assertEqual(self.prod2.brand, self.brand2)

    def test_bulk_change_tax_and_vat_code(self):
        """Test updating tax class and VAT code"""
        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'change_tax',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'target_tax_class': 'exempt',
            'target_vat_code': str(self.vat_16.pk),
            'admin_password': 'password123!',
            'reason': 'Fiscal tax exemption',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertEqual(self.prod1.tax_class, 'exempt')
        self.assertEqual(self.prod1.vat_code, self.vat_16)
        self.assertEqual(self.prod2.tax_class, 'exempt')
        self.assertEqual(self.prod2.vat_code, self.vat_16)

    def test_bulk_adjust_price_percentage_increase(self):
        """Test increasing prices by a percentage (e.g., +10%)"""
        url = reverse('product_bulk_action')
        # prod1 was 150.00 -> 10% increase should be 165.00
        # prod2 was 120.00 -> 10% increase should be 132.00
        response = self.client.post(url, {
            'bulk_action': 'adjust_price',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'price_target_field': 'unit_price',
            'price_adj_type': 'percent_increase',
            'price_adj_value': '10',
            'price_round_mode': 'two_decimals',
            'admin_password': 'password123!',
            'reason': 'Annual inflation price increase',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertEqual(self.prod1.unit_price, Decimal('165.00'))
        self.assertEqual(self.prod2.unit_price, Decimal('132.00'))

    def test_bulk_adjust_price_fixed_decrease_and_rounding(self):
        """Test fixed price decrease with integer rounding"""
        url = reverse('product_bulk_action')
        # prod1 unit_price 150.00 - 15.30 = 134.70 -> round to integer = 135.00
        response = self.client.post(url, {
            'bulk_action': 'adjust_price',
            'selected_products': [self.prod1.pk],
            'price_target_field': 'unit_price',
            'price_adj_type': 'fixed_decrease',
            'price_adj_value': '15.30',
            'price_round_mode': 'integer',
            'admin_password': 'password123!',
            'reason': 'Promotional markdown',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.unit_price, Decimal('135.00'))

    def test_bulk_adjust_cost_price(self):
        """Test updating cost price with minimum validation"""
        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'adjust_price',
            'selected_products': [self.prod1.pk],
            'price_target_field': 'cost_price',
            'price_adj_type': 'set_exact',
            'price_adj_value': '115.50',
            'price_round_mode': 'two_decimals',
            'admin_password': 'password123!',
            'reason': 'Supplier revised cost price',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.assertEqual(self.prod1.cost_price, Decimal('115.50'))

    def test_bulk_safe_delete_and_discontinue(self):
        """Test safe delete: deletes unused products, discontinues products with sales history"""
        # Create a sale with prod1
        sale = Sale.objects.create(
            business=self.business,
            invoice_number="INV-BULK-001",
            subtotal=Decimal('129.31'),
            vat_amount=Decimal('20.69'),
            total=Decimal('150.00'),
            amount_paid=Decimal('150.00')
        )
        SaleItem.objects.create(
            business=self.business,
            sale=sale,
            product=self.prod1,
            quantity=Decimal('1.000'),
            unit_price=Decimal('150.00'),
            total_price=Decimal('150.00')
        )

        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'delete',
            'delete_mode': 'safe_delete',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'admin_password': 'password123!',
            'reason': 'Catalog cleanup for discontinued lines',
        })
        self.assertEqual(response.status_code, 302)

        # prod2 has no sales history -> permanently deleted
        self.assertFalse(Product.objects.filter(pk=self.prod2.pk).exists())

        # prod1 has sales history -> discontinued (is_active=False, stock_quantity=0)
        self.prod1.refresh_from_db()
        self.assertFalse(self.prod1.is_active)
        self.assertEqual(self.prod1.stock_quantity, Decimal('0.00'))

    def test_bulk_export_csv(self):
        """Test exporting selected products as CSV (read-only, does not require password)"""
        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'export_csv',
            'selected_products': [self.prod1.pk, self.prod2.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn("Coffee Jar", content)
        self.assertIn("Tea Bag Pack", content)
        self.assertNotIn("Milk Chocolate", content)

    def test_bulk_barcode_label_print(self):
        """Test barcode printable sheet view with copies"""
        url = reverse('product_bulk_barcode_print')
        response = self.client.get(url, {
            'ids': f"{self.prod1.pk},{self.prod2.pk}",
            'copies': '2'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/product_barcode_labels.html')
        self.assertEqual(len(response.context['products']), 4)
        self.assertContains(response, "Coffee Jar")
        self.assertContains(response, "Tea Bag Pack")

    def test_business_isolation_prevents_foreign_product_tampering(self):
        """Test that user cannot perform bulk actions on products belonging to another business"""
        url = reverse('product_bulk_action')
        initial_status = self.other_prod.is_active
        
        response = self.client.post(url, {
            'bulk_action': 'deactivate',
            'selected_products': [self.other_prod.pk],
            'admin_password': 'password123!',
            'reason': 'Unauthorized tampering attempt',
        })
        # Should redirect with a warning because 0 valid products found for current business
        self.assertEqual(response.status_code, 302)
        self.other_prod.refresh_from_db()
        self.assertEqual(self.other_prod.is_active, initial_status)

    def test_ajax_bulk_action_response(self):
        """Test JSON response when requested via AJAX"""
        url = reverse('product_bulk_action')
        response = self.client.post(
            url,
            {
                'bulk_action': 'activate',
                'selected_products': [self.prod3.pk],
                'admin_password': 'password123!',
                'reason': 'AJAX activation test',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('count'), 1)

    def test_django_admin_product_actions(self):
        """Test Django Admin ProductAdmin custom actions"""
        prod_admin = ProductAdmin(Product, site)
        qs = Product.objects.filter(pk__in=[self.prod1.pk, self.prod2.pk])
        
        # Test make_inactive
        prod_admin.make_inactive(None, qs)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertFalse(self.prod1.is_active)
        self.assertFalse(self.prod2.is_active)

        # Test make_active
        prod_admin.make_active(None, qs)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertTrue(self.prod1.is_active)
        self.assertTrue(self.prod2.is_active)

        # Test set_tax_zero_rated
        prod_admin.set_tax_zero_rated(None, qs)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertEqual(self.prod1.tax_class, 'zero_rated')
        self.assertEqual(self.prod2.tax_class, 'zero_rated')

    def test_bulk_delete_discontinue_all_mode(self):
        """Test discontinue_all mode marks all selected products as inactive with 0 stock"""
        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'delete',
            'delete_mode': 'discontinue_all',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'admin_password': 'password123!',
            'reason': 'Discontinue obsolete line',
        })
        self.assertEqual(response.status_code, 302)
        self.prod1.refresh_from_db()
        self.prod2.refresh_from_db()
        self.assertFalse(self.prod1.is_active)
        self.assertFalse(self.prod2.is_active)
        self.assertEqual(self.prod1.stock_quantity, Decimal('0.00'))
        self.assertEqual(self.prod2.stock_quantity, Decimal('0.00'))

    def test_bulk_delete_unused_only_mode(self):
        """Test delete_unused_only deletes unreferenced products and skips products with sales history"""
        sale = Sale.objects.create(
            business=self.business,
            invoice_number="INV-BULK-002",
            subtotal=Decimal('129.31'),
            vat_amount=Decimal('20.69'),
            total=Decimal('150.00'),
            amount_paid=Decimal('150.00')
        )
        SaleItem.objects.create(
            business=self.business,
            sale=sale,
            product=self.prod1,
            quantity=Decimal('1.000'),
            unit_price=Decimal('150.00'),
            total_price=Decimal('150.00')
        )

        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'delete',
            'delete_mode': 'delete_unused_only',
            'selected_products': [self.prod1.pk, self.prod2.pk],
            'admin_password': 'password123!',
            'reason': 'Clean unused items only',
        })
        self.assertEqual(response.status_code, 302)

        # prod2 was unused -> deleted
        self.assertFalse(Product.objects.filter(pk=self.prod2.pk).exists())

        # prod1 had sales -> skipped and remained untouched
        self.prod1.refresh_from_db()
        self.assertTrue(self.prod1.is_active)
        self.assertEqual(self.prod1.stock_quantity, Decimal('50.00'))

    def test_bulk_delete_with_stock_movements(self):
        """Test that products with initial stock movements can still be deleted if unused in sales/purchases"""
        from pos.models import StockMovement, Branch
        branch = Branch.objects.filter(business=self.business).first() or Branch.objects.create(
            business=self.business, name="Test Branch", code="TB"
        )
        StockMovement.objects.create(
            product=self.prod2,
            business=self.business,
            branch=branch,
            movement_type='initial',
            quantity_delta=Decimal('30.00'),
            balance_after=Decimal('30.00'),
            unit_cost=Decimal('80.00'),
            total_cost=Decimal('2400.00')
        )

        url = reverse('product_bulk_action')
        response = self.client.post(url, {
            'bulk_action': 'delete',
            'delete_mode': 'safe_delete',
            'selected_products': [self.prod2.pk],
            'admin_password': 'password123!',
            'reason': 'Cleanup unused product with initial stock',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=self.prod2.pk).exists())

    def test_product_list_pagination_30_per_page(self):
        """Test that product list view paginates at 30 items per page"""
        # Create 35 additional products (total > 30)
        new_prods = [
            Product(
                business=self.business,
                name=f"Paged Product {i}",
                cost_price=Decimal('10.00'),
                unit_price=Decimal('15.00')
            )
            for i in range(1, 36)
        ]
        Product.objects.bulk_create(new_prods)

        url = reverse('product_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('page_obj', response.context)
        self.assertEqual(len(response.context['products']), 30)
        self.assertTrue(response.context['page_obj'].has_next())
        self.assertEqual(response.context['paginator'].num_pages, 2)

        # Page 2 has the remaining products
        response_p2 = self.client.get(url + "?page=2")
        self.assertEqual(response_p2.status_code, 200)
        self.assertEqual(len(response_p2.context['products']), (3 + 35) - 30)  # 38 - 30 = 8

    def test_single_product_delete_security(self):
        """Test single product deletion requires password and reason"""
        url = reverse('product_delete', kwargs={'pk': self.prod2.pk})

        # Rejection without password
        resp = self.client.post(url, {'action': 'delete', 'reason': 'Deleting test prod'})
        self.assertEqual(resp.status_code, 200) # Re-rendered confirm template with error
        self.assertTrue(Product.objects.filter(pk=self.prod2.pk).exists())

        # Success with valid password and reason
        resp = self.client.post(url, {
            'action': 'delete',
            'admin_password': 'password123!',
            'reason': 'Authorized single item deletion'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=self.prod2.pk).exists())


