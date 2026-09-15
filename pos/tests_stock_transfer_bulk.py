import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone

from pos.models import (
    Business, BusinessMembership, Branch, BranchMembership,
    Product, Category, BranchStock, StockTransfer, Sale, SaleItem,
)
from pos.branch_services import BranchStockService


class BulkStockTransferViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(username="admin_user", password="password123")
        self.business = Business.objects.create(name="Apex Retailers", owner=self.admin_user, slug="apex-retailers")
        BusinessMembership.objects.create(user=self.admin_user, business=self.business, role="admin", is_active=True)

        self.source_branch = Branch.objects.create(
            business=self.business,
            name="Nairobi West",
            code="NRB-W",
            is_active=True,
        )
        self.dest_branch = Branch.objects.create(
            business=self.business,
            name="Mombasa Coast",
            code="MSA-C",
            is_active=True,
        )

        BranchMembership.objects.create(
            user=self.admin_user, branch=self.source_branch, role="manager", is_active=True
        )

        # Categories
        self.cat_food = Category.objects.create(business=self.business, name="Food & Beverages")
        self.cat_elec = Category.objects.create(business=self.business, name="Electronics")

        # Products
        self.prod_slow = Product.objects.create(
            business=self.business,
            name="Slow Moving Widget",
            product_code="SKU-SLOW-001",
            barcode="111122223333",
            category=self.cat_elec,
            cost_price=Decimal("100.00"),
            unit_price=Decimal("150.00"),
            stock_quantity=Decimal("50.000"),
            is_active=True,
        )
        self.prod_fast = Product.objects.create(
            business=self.business,
            name="Fast Selling Soda",
            product_code="SKU-FAST-002",
            barcode="444455556666",
            category=self.cat_food,
            cost_price=Decimal("20.00"),
            unit_price=Decimal("35.00"),
            stock_quantity=Decimal("100.000"),
            is_active=True,
        )
        self.prod_new = Product.objects.create(
            business=self.business,
            name="Brand New Arrival",
            product_code="SKU-NEW-003",
            barcode="777788889999",
            category=self.cat_food,
            cost_price=Decimal("50.00"),
            unit_price=Decimal("80.00"),
            stock_quantity=Decimal("30.000"),
            is_active=True,
        )

        # Seed source branch stock
        BranchStockService.add(self.source_branch, self.prod_slow, Decimal("40.000"), Decimal("100.00"))
        BranchStockService.add(self.source_branch, self.prod_fast, Decimal("80.000"), Decimal("20.00"))
        BranchStockService.add(self.source_branch, self.prod_new, Decimal("25.000"), Decimal("50.00"))

        # Create a sale for fast selling product to create sales velocity contrast
        sale = Sale.objects.create(
            business=self.business,
            branch=self.source_branch,
            subtotal=Decimal("70.00"),
            vat_amount=Decimal("0.00"),
            total=Decimal("70.00"),
            amount_paid=Decimal("70.00"),
        )
        SaleItem.objects.create(
            business=self.business,
            sale=sale,
            product=self.prod_fast,
            quantity=Decimal("2.000"),
            unit_price=Decimal("35.00"),
            total_price=Decimal("70.00"),
        )

        self.client.login(username="admin_user", password="password123")
        session = self.client.session
        session['business_id'] = self.business.pk
        session.save()

    def test_transfer_form_get_view_enriched_data(self):
        """GET transfer form includes enriched stock, sales count, and categories."""
        url = reverse('transfer_create', kwargs={'branch_id': self.source_branch.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/branches/transfer_form.html')
        self.assertIn('products_json', response.context)
        self.assertIn('categories', response.context)

        # Inspect products json
        products_data = json.loads(response.context['products_json'])
        self.assertEqual(len(products_data), 3)

        # Check that stock and sold attributes are populated
        slow_data = next(p for p in products_data if p['id'] == self.prod_slow.pk)
        fast_data = next(p for p in products_data if p['id'] == self.prod_fast.pk)

        self.assertEqual(slow_data['stock'], 40.0)
        self.assertEqual(slow_data['sold'], 0.0) # least sold

        self.assertEqual(fast_data['stock'], 80.0)
        self.assertEqual(fast_data['sold'], 2.0) # sold 2 units

    def test_bulk_transfer_submission_json(self):
        """POST bulk transfer with items_json payload transfers all items atomically."""
        url = reverse('transfer_create', kwargs={'branch_id': self.source_branch.pk})

        items_payload = [
            {'product_id': self.prod_slow.pk, 'quantity': 10},
            {'product_id': self.prod_fast.pk, 'quantity': 15},
        ]

        post_data = {
            'destination_branch': self.dest_branch.pk,
            'note': 'Transferring slow items to Mombasa',
            'items_json': json.dumps(items_payload),
        }

        response = self.client.post(url, post_data)
        self.assertRedirects(response, reverse('transfer_list', kwargs={'branch_id': self.source_branch.pk}))

        # Verify StockTransfer records
        transfers = StockTransfer.objects.filter(
            source_branch=self.source_branch,
            destination_branch=self.dest_branch
        )
        self.assertEqual(transfers.count(), 2)
        self.assertTrue(all(t.status == 'completed' for t in transfers))

        # Verify source branch stock deductions
        source_slow_stock = BranchStock.objects.get(branch=self.source_branch, product=self.prod_slow)
        source_fast_stock = BranchStock.objects.get(branch=self.source_branch, product=self.prod_fast)
        self.assertEqual(source_slow_stock.quantity, Decimal("30.000")) # 40 - 10
        self.assertEqual(source_fast_stock.quantity, Decimal("65.000")) # 80 - 15

        # Verify destination branch stock additions
        dest_slow_stock = BranchStock.objects.get(branch=self.dest_branch, product=self.prod_slow)
        dest_fast_stock = BranchStock.objects.get(branch=self.dest_branch, product=self.prod_fast)
        self.assertEqual(dest_slow_stock.quantity, Decimal("10.000"))
        self.assertEqual(dest_fast_stock.quantity, Decimal("15.000"))

    def test_single_transfer_backward_compatibility(self):
        """POST single product form (legacy fallback) still transfers accurately."""
        url = reverse('transfer_create', kwargs={'branch_id': self.source_branch.pk})

        post_data = {
            'destination_branch': self.dest_branch.pk,
            'product': self.prod_new.pk,
            'quantity': '5',
            'note': 'Single item transfer',
        }

        response = self.client.post(url, post_data)
        self.assertRedirects(response, reverse('transfer_list', kwargs={'branch_id': self.source_branch.pk}))

        transfer = StockTransfer.objects.get(
            source_branch=self.source_branch,
            destination_branch=self.dest_branch,
            product=self.prod_new
        )
        self.assertEqual(transfer.quantity, Decimal("5.000"))
        self.assertEqual(transfer.status, 'completed')

    def test_transfer_validation_errors(self):
        """Validation fails if destination is missing, same branch, or no items selected."""
        url = reverse('transfer_create', kwargs={'branch_id': self.source_branch.pk})

        # Same branch error
        response = self.client.post(url, {
            'destination_branch': self.source_branch.pk,
            'items_json': json.dumps([{'product_id': self.prod_slow.pk, 'quantity': 1}])
        })
        self.assertRedirects(response, url)

        # Empty items error
        response = self.client.post(url, {
            'destination_branch': self.dest_branch.pk,
            'items_json': json.dumps([])
        })
        self.assertRedirects(response, url)

    def test_transfer_list_view_and_filtering(self):
        """Test transfer_list view rendering, filtering by direction/status/query, and stats."""
        # Create an outgoing transfer and an incoming transfer
        StockTransfer.objects.create(
            business=self.business,
            source_branch=self.source_branch,
            destination_branch=self.dest_branch,
            product=self.prod_slow,
            quantity=Decimal("12.000"),
            status='completed',
            initiated_by=self.admin_user,
            reference='TRF-TEST-001',
            note='Test outbound movement',
        )
        StockTransfer.objects.create(
            business=self.business,
            source_branch=self.dest_branch,
            destination_branch=self.source_branch,
            product=self.prod_fast,
            quantity=Decimal("8.000"),
            status='completed',
            initiated_by=self.admin_user,
            reference='TRF-TEST-002',
            note='Test inbound movement',
        )

        url = reverse('transfer_list', kwargs={'branch_id': self.source_branch.pk})

        # 1. Base list view
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/branches/transfer_list.html')
        self.assertEqual(len(response.context['transfers']), 2)
        stats = response.context['stats']
        self.assertEqual(stats['total_count'], 2)
        self.assertEqual(stats['outbound_count'], 1)
        self.assertEqual(stats['inbound_count'], 1)
        self.assertEqual(stats['outbound_units'], Decimal("12.000"))
        self.assertEqual(stats['inbound_units'], Decimal("8.000"))

        # 2. Filter outgoing
        response_out = self.client.get(url, {'direction': 'outgoing'})
        self.assertEqual(len(response_out.context['transfers']), 1)
        self.assertEqual(response_out.context['transfers'][0].reference, 'TRF-TEST-001')

        # 3. Filter incoming
        response_in = self.client.get(url, {'direction': 'incoming'})
        self.assertEqual(len(response_in.context['transfers']), 1)
        self.assertEqual(response_in.context['transfers'][0].reference, 'TRF-TEST-002')

        # 4. Search query
        response_search = self.client.get(url, {'q': 'Soda'})
        self.assertEqual(len(response_search.context['transfers']), 1)
        self.assertEqual(response_search.context['transfers'][0].product.name, self.prod_fast.name)

    def test_business_transfer_list_view_and_filtering(self):
        """Test business_transfer_list view enterprise overview and filters."""
        StockTransfer.objects.create(
            business=self.business,
            source_branch=self.source_branch,
            destination_branch=self.dest_branch,
            product=self.prod_slow,
            quantity=Decimal("5.000"),
            status='completed',
            initiated_by=self.admin_user,
            reference='TRF-ENT-001',
        )

        url = reverse('business_transfer_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'pos/branches/business_transfer_list.html')
        self.assertEqual(len(response.context['transfers']), 1)
        self.assertEqual(response.context['stats']['total_transfers'], 1)
        self.assertEqual(response.context['stats']['total_units'], Decimal("5.000"))

        # Filter by source branch
        resp_src = self.client.get(url, {'source_branch': str(self.source_branch.pk)})
        self.assertEqual(len(resp_src.context['transfers']), 1)

        resp_dest = self.client.get(url, {'source_branch': str(self.dest_branch.pk)})
        self.assertEqual(len(resp_dest.context['transfers']), 0)

