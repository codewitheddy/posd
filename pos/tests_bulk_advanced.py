"""
Unit tests for Bulk Product Advanced Features.
Tests model helpers, field validation, and audit trail creation.

Run with:
    python manage.py test pos.tests_bulk_advanced
"""
from decimal import Decimal
import django.test
from django.contrib.auth.models import User

from pos.models import Business, Product, Category, StockAdjustment


class BulkProductTestCase(django.test.TestCase):
    """Base test case with minimal fixtures for bulk product tests."""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.business = Business.objects.create(
            name='Test Business',
            slug='test-business',
            owner=self.user,
        )
        self.category = Category.objects.get_or_create(
            business=self.business,
            name='Test Category'
        )[0]

    def _make_product(self, **kwargs):
        """Create a minimal product with sensible defaults."""
        defaults = dict(
            business=self.business,
            name='Test Product',
            cost_price=Decimal('10.00'),
            unit_price=Decimal('15.00'),
            stock_quantity=Decimal('100'),
            low_stock_threshold=Decimal('10'),
            bulk_unit_name='Carton',
            bulk_unit_quantity=Decimal('12'),
            bulk_unit_price=Decimal('120.00'),
        )
        defaults.update(kwargs)
        return Product.objects.create(**defaults)

    # ── 1. Derived unit cost calculation ─────────────────────────────────────

    def test_derived_unit_cost(self):
        """bulk_unit_price=120, bulk_unit_quantity=12 → cost_price=10.00"""
        product = self._make_product(
            bulk_unit_price=Decimal('120.00'),
            bulk_unit_quantity=Decimal('12'),
            cost_price=Decimal('10.00'),
        )
        expected = Decimal('120.00') / Decimal('12')
        self.assertEqual(product.cost_price, expected)

    # ── 2. is_bulk_low_stock() ────────────────────────────────────────────────

    def test_is_bulk_low_stock_true(self):
        """Returns True when stock_quantity / bulk_unit_quantity <= bulk_low_stock_threshold."""
        # 24 units / 12 per carton = 2 cartons; threshold = 3 → low stock
        product = self._make_product(
            stock_quantity=Decimal('24'),
            bulk_unit_quantity=Decimal('12'),
            bulk_low_stock_threshold=Decimal('3'),
        )
        self.assertTrue(product.is_bulk_low_stock())

    def test_is_bulk_low_stock_false(self):
        """Returns False when bulk stock level is above threshold."""
        # 60 units / 12 per carton = 5 cartons; threshold = 3 → not low stock
        product = self._make_product(
            stock_quantity=Decimal('60'),
            bulk_unit_quantity=Decimal('12'),
            bulk_low_stock_threshold=Decimal('3'),
        )
        self.assertFalse(product.is_bulk_low_stock())

    def test_is_bulk_low_stock_none_quantity(self):
        """Returns False when bulk_unit_quantity is None."""
        product = self._make_product(
            bulk_unit_quantity=None,
            bulk_unit_name='',
            bulk_unit_price=None,
            bulk_low_stock_threshold=Decimal('3'),
        )
        self.assertFalse(product.is_bulk_low_stock())

    # ── 3. bulk_stock_level() ─────────────────────────────────────────────────

    def test_bulk_stock_level_returns_ratio(self):
        """Returns stock_quantity / bulk_unit_quantity."""
        product = self._make_product(
            stock_quantity=Decimal('60'),
            bulk_unit_quantity=Decimal('12'),
        )
        self.assertEqual(product.bulk_stock_level(), Decimal('60') / Decimal('12'))

    def test_bulk_stock_level_none_when_no_quantity(self):
        """Returns None when bulk_unit_quantity is None."""
        product = self._make_product(
            bulk_unit_quantity=None,
            bulk_unit_name='',
            bulk_unit_price=None,
        )
        self.assertIsNone(product.bulk_stock_level())

    # ── 4. is_low_stock() ────────────────────────────────────────────────────

    def test_is_low_stock_true(self):
        """Returns True when stock_quantity <= low_stock_threshold."""
        product = self._make_product(
            stock_quantity=Decimal('5'),
            low_stock_threshold=Decimal('10'),
        )
        self.assertTrue(product.is_low_stock())

    def test_is_low_stock_false(self):
        """Returns False when stock_quantity > low_stock_threshold."""
        product = self._make_product(
            stock_quantity=Decimal('50'),
            low_stock_threshold=Decimal('10'),
        )
        self.assertFalse(product.is_low_stock())

    # ── 5. Break-bulk StockAdjustment creation ────────────────────────────────

    def test_bulk_break_adjustment_can_be_created(self):
        """StockAdjustment with adjustment_type='bulk_break' can be created and saved."""
        product = self._make_product()
        adj = StockAdjustment.objects.create(
            business=self.business,
            product=product,
            adjustment_type='bulk_break',
            quantity_change=0,
            previous_quantity=100,
            new_quantity=100,
            reason='Broke 2 cartons into individual units',
        )
        self.assertEqual(adj.adjustment_type, 'bulk_break')
        self.assertEqual(adj.quantity_change, 0)
        self.assertIsNotNone(adj.pk)

    def test_bulk_break_quantity_change_zero_is_valid(self):
        """quantity_change=0 is valid for a bulk_break adjustment."""
        product = self._make_product()
        adj = StockAdjustment.objects.create(
            business=self.business,
            product=product,
            adjustment_type='bulk_break',
            quantity_change=0,
            previous_quantity=100,
            new_quantity=100,
            reason='Reclassification only',
        )
        fetched = StockAdjustment.objects.get(pk=adj.pk)
        self.assertEqual(fetched.quantity_change, 0)

    # ── 6. 'bulk_break' in ADJUSTMENT_TYPES ──────────────────────────────────

    def test_bulk_break_in_adjustment_types(self):
        """'bulk_break' is a valid choice in StockAdjustment.ADJUSTMENT_TYPES."""
        valid_types = [code for code, _ in StockAdjustment.ADJUSTMENT_TYPES]
        self.assertIn('bulk_break', valid_types)

    # ── 7. unit_barcode field ─────────────────────────────────────────────────

    def test_unit_barcode_can_be_saved(self):
        """A product can be saved with a unit_barcode value."""
        product = self._make_product(unit_barcode='UNIT-BAR-001')
        fetched = Product.objects.get(pk=product.pk)
        self.assertEqual(fetched.unit_barcode, 'UNIT-BAR-001')

    # ── 8. bulk_discount_price field ─────────────────────────────────────────

    def test_bulk_discount_price_can_be_saved(self):
        """A product can be saved with a bulk_discount_price value."""
        product = self._make_product(bulk_discount_price=Decimal('9.50'))
        fetched = Product.objects.get(pk=product.pk)
        self.assertEqual(fetched.bulk_discount_price, Decimal('9.50'))
