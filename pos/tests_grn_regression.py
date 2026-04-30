from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from pos.models import (
    Business,
    BusinessMembership,
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    GoodsReturnedNote,
    GoodsReturnedNoteItem,
    Product,
    Purchase,
    PurchaseItem,
    Supplier,
)


class GRNRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='grn-owner', password='pass123!')
        self.business = Business.objects.create(
            name='GRN Business',
            slug='grn-business',
            owner=self.user,
        )
        BusinessMembership.objects.create(user=self.user, business=self.business, role='owner')

        self.client.force_login(self.user)

        self.supplier = Supplier.objects.create(
            business=self.business,
            name='GRN Supplier',
            is_active=True,
        )

        self.product = Product.objects.create(
            business=self.business,
            name='GRN Product',
            product_code='GRN-001',
            cost_price=Decimal('50.00'),
            unit_price=Decimal('75.00'),
            stock_quantity=Decimal('100.00'),
        )

    def _create_purchase_with_damage(self, qty_ordered=5, qty_damaged=3):
        purchase = Purchase.objects.create(
            business=self.business,
            supplier=self.supplier,
            status='received',
            subtotal=Decimal('250.00'),
            total_amount=Decimal('250.00'),
        )

        PurchaseItem.objects.create(
            business=self.business,
            purchase=purchase,
            product=self.product,
            quantity=qty_ordered,
            unit_cost=Decimal('50.00'),
            quantity_received=max(qty_ordered - qty_damaged, 0),
            quantity_damaged=qty_damaged,
        )

        grn_received = GoodsReceivedNote.objects.create(
            business=self.business,
            purchase=purchase,
            supplier=self.supplier,
            received_by=self.user,
            total_ordered_qty=qty_ordered,
            total_received_qty=max(qty_ordered - qty_damaged, 0),
            total_damaged_qty=qty_damaged,
            total_value=Decimal('250.00'),
        )
        GoodsReceivedNoteItem.objects.create(
            grn=grn_received,
            product=self.product,
            quantity_ordered=qty_ordered,
            quantity_received=max(qty_ordered - qty_damaged, 0),
            quantity_damaged=qty_damaged,
            unit_cost=Decimal('50.00'),
        )

        return purchase, grn_received

    def test_goods_received_detail_blocks_return_when_damaged_already_fully_returned(self):
        purchase, goods_received = self._create_purchase_with_damage(qty_ordered=5, qty_damaged=3)

        returned_note = GoodsReturnedNote.objects.create(
            business=self.business,
            supplier=self.supplier,
            related_purchase=purchase,
            return_reason='damaged',
            reason_details='Previously returned all damaged units',
            created_by=self.user,
            status='submitted',
        )
        GoodsReturnedNoteItem.objects.create(
            grn=returned_note,
            product=self.product,
            quantity=3,
            unit_cost=Decimal('50.00'),
        )

        url = reverse('goods_received_detail', kwargs={'slug': self.business.slug, 'pk': goods_received.pk})
        with patch('pos.views.render', return_value=HttpResponse('ok')) as mock_render:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        rendered_context = mock_render.call_args[0][2]
        self.assertFalse(rendered_context['can_create_return_note'])
        self.assertEqual(rendered_context['remaining_damaged_qty'], 0)

    def test_grn_create_rejects_damaged_return_when_no_remaining_damaged_qty(self):
        purchase, _ = self._create_purchase_with_damage(qty_ordered=4, qty_damaged=2)

        returned_note = GoodsReturnedNote.objects.create(
            business=self.business,
            supplier=self.supplier,
            related_purchase=purchase,
            return_reason='damaged',
            reason_details='All damaged already returned',
            created_by=self.user,
            status='submitted',
        )
        GoodsReturnedNoteItem.objects.create(
            grn=returned_note,
            product=self.product,
            quantity=2,
            unit_cost=Decimal('50.00'),
        )

        initial_count = GoodsReturnedNote.objects.filter(business=self.business).count()
        payload = {
            'supplier': str(self.supplier.id),
            'related_purchase': str(purchase.id),
            'return_reason': 'damaged',
            'reason_details': 'Trying duplicate return',
        }

        with patch('pos.views.render', return_value=HttpResponse('invalid')) as mock_render:
            response = self.client.post(reverse('grn_create', kwargs={'slug': self.business.slug}), payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        self.assertEqual(GoodsReturnedNote.objects.filter(business=self.business).count(), initial_count)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertIn('All damaged quantities for this purchase have already been returned.', messages)

    def test_grn_create_rejects_quantity_above_remaining_damaged_qty(self):
        purchase, _ = self._create_purchase_with_damage(qty_ordered=5, qty_damaged=2)

        existing_note = GoodsReturnedNote.objects.create(
            business=self.business,
            supplier=self.supplier,
            related_purchase=purchase,
            return_reason='damaged',
            reason_details='Partial prior return',
            created_by=self.user,
            status='submitted',
        )
        GoodsReturnedNoteItem.objects.create(
            grn=existing_note,
            product=self.product,
            quantity=1,
            unit_cost=Decimal('50.00'),
        )

        initial_count = GoodsReturnedNote.objects.filter(business=self.business).count()
        payload = {
            'supplier': str(self.supplier.id),
            'related_purchase': str(purchase.id),
            'return_reason': 'damaged',
            'reason_details': 'Requesting too much',
            'item_product_1': str(self.product.id),
            'item_quantity_1': '2',
            'item_cost_1': '50.00',
        }

        with patch('pos.views.render', return_value=HttpResponse('invalid')) as mock_render:
            response = self.client.post(reverse('grn_create', kwargs={'slug': self.business.slug}), payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        self.assertEqual(GoodsReturnedNote.objects.filter(business=self.business).count(), initial_count)
        messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any('exceeds available damaged quantity' in msg for msg in messages))

    def test_purchase_detail_hides_return_note_when_no_remaining_damaged(self):
        purchase = Purchase.objects.create(
            business=self.business,
            supplier=self.supplier,
            status='received',
            subtotal=Decimal('5000.00'),
            total_amount=Decimal('5000.00'),
        )
        PurchaseItem.objects.create(
            business=self.business,
            purchase=purchase,
            product=self.product,
            quantity=100,
            quantity_received=100,
            quantity_damaged=0,
            unit_cost=Decimal('50.00'),
        )

        url = reverse('purchase_detail', kwargs={'slug': self.business.slug, 'pk': purchase.pk})
        with patch('pos.views.render', return_value=HttpResponse('ok')) as mock_render:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_render.called)
        rendered_context = mock_render.call_args[0][2]
        self.assertFalse(rendered_context['can_create_return_note'])
        self.assertEqual(rendered_context['remaining_damaged_qty'], 0)
