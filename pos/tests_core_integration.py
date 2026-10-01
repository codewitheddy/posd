"""
Tests for POS Integration onto Platform Core (Phase 4 Strangler Migration).
Verifies:
- Concurrency-safe Document Numbering via Core DocumentSequence
- Outbox Domain Event Publishing (pos.sale_completed.v1, pos.sale_refunded.v1, pos.shift_closed.v1)
- Unified Audit Logging via Core AuditLog
- Public API Boundary compliance (HR accessing POS via pos.api)
"""
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from pos.models import (
    Business, Branch, Category, Product, Customer, Sale, SaleItem,
    Purchase, Supplier, SupplierPayment, Shift, SaleReturn, PaymentMethod,
    Expense, ExpenseCategory, ActivityLog
)
from core.models.organization import Company, Branch as CoreBranch
from core.models.numbering import DocumentSequence
from core.models.events import OutboxEvent
from core.models.audit import AuditLog
from pos import api as pos_api


class PosCoreStranglerIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='cashier1',
            password='password123',
            first_name='John',
            last_name='Mwangi'
        )
        self.business = Business.objects.create(
            name='K-Mart Supermarket',
            slug='k-mart-supermarket',
            owner=self.user,
            tax_id='P051234567Z'
        )
        self.branch = Branch.objects.create(
            business=self.business,
            name='Nairobi Central',
            code='NBI01',
            is_hq=True
        )
        self.category = Category.objects.create(
            business=self.business,
            name='Groceries'
        )
        self.product = Product.objects.create(
            business=self.business,
            name='Kenyan Tea 500g',
            category=self.category,
            unit_price=Decimal('250.00'),
            cost_price=Decimal('180.00'),
            stock_quantity=100
        )
        self.customer = Customer.objects.create(
            business=self.business,
            name='Alice Wanjiku',
            phone='0712345678'
        )
        self.payment_method, _ = PaymentMethod.objects.get_or_create(
            business=self.business,
            code='CASH',
            defaults={'name': 'Cash'}
        )
        self.supplier = Supplier.objects.create(
            business=self.business,
            name='Ketepa Supplies Ltd',
            email='orders@ketepa.co.ke'
        )
        self.expense_category = ExpenseCategory.objects.create(
            business=self.business,
            name='Store Utilities'
        )

    def test_sale_document_numbering_uses_core_document_sequence(self):
        """Saving a sale generates sequential collision-free invoice numbers via Core DocumentSequence."""
        sale1 = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.user,
            customer=self.customer,
            subtotal=Decimal('500.00'),
            vat_amount=Decimal('80.00'),
            total=Decimal('580.00'),
            amount_paid=Decimal('600.00'),
            change_given=Decimal('20.00'),
        )
        sale2 = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.user,
            customer=self.customer,
            subtotal=Decimal('250.00'),
            vat_amount=Decimal('40.00'),
            total=Decimal('290.00'),
            amount_paid=Decimal('300.00'),
            change_given=Decimal('10.00'),
        )

        today_str = timezone.now().strftime('%Y%m%d')
        self.assertTrue(sale1.invoice_number.startswith(f'INV-{today_str}-'))
        self.assertTrue(sale2.invoice_number.startswith(f'INV-{today_str}-'))
        
        # Verify Core DocumentSequence was updated
        seq = DocumentSequence.objects.filter(
            document_type='sale_invoice',
            fiscal_year=timezone.now().year
        ).first()
        self.assertIsNotNone(seq)
        self.assertGreaterEqual(seq.current_number, 2)

    def test_sale_completion_publishes_event_to_core_outbox(self):
        """Creating a new Sale publishes pos.sale_completed.v1 event to Core OutboxEvent table."""
        sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.user,
            customer=self.customer,
            subtotal=Decimal('1000.00'),
            vat_amount=Decimal('160.00'),
            total=Decimal('1160.00'),
            amount_paid=Decimal('1200.00'),
            change_given=Decimal('40.00'),
        )

        event = OutboxEvent.objects.filter(
            event_name='pos.sale_completed.v1',
            status=OutboxEvent.STATUS_PENDING,
        ).first()

        self.assertIsNotNone(event)
        self.assertEqual(event.payload['invoice_number'], sale.invoice_number)
        self.assertEqual(event.payload['total'], '1160.00')
        self.assertEqual(event.payload['cashier_id'], self.user.id)

    def test_purchase_document_numbering_uses_core(self):
        """Purchase orders generate sequential numbering via Core DocumentSequence."""
        po = Purchase.objects.create(
            business=self.business,
            branch=self.branch,
            supplier=self.supplier,
            created_by=self.user,
            subtotal=Decimal('5000.00'),
            tax_amount=Decimal('800.00'),
            total_amount=Decimal('5800.00'),
        )

        today_str = timezone.now().strftime('%Y%m%d')
        self.assertTrue(po.purchase_number.startswith(f'PO-{today_str}-'))

        seq = DocumentSequence.objects.filter(
            document_type='purchase_order',
            fiscal_year=timezone.now().year
        ).first()
        self.assertIsNotNone(seq)

    def test_shift_close_publishes_domain_event(self):
        """Closing a shift calculates variance and publishes pos.shift_closed.v1 event to Core Outbox."""
        shift = Shift.objects.create(
            cashier=self.user,
            opening_cash=Decimal('5000.00'),
            status='open'
        )
        self.assertTrue(shift.shift_number.startswith('SHIFT-'))

        shift.close_shift(closing_cash=Decimal('5500.00'))

        self.assertEqual(shift.status, 'closed')
        self.assertIsNotNone(shift.end_time)

        event = OutboxEvent.objects.filter(
            event_name='pos.shift_closed.v1',
            status=OutboxEvent.STATUS_PENDING,
        ).first()

        self.assertIsNotNone(event)
        self.assertEqual(event.payload['shift_number'], shift.shift_number)
        self.assertEqual(event.payload['cashier_id'], self.user.id)
        self.assertEqual(event.payload['closing_cash'], '5500.00')

    def test_sale_return_publishes_domain_event(self):
        """Refunding a sale publishes pos.sale_refunded.v1 event to Core Outbox."""
        sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.user,
            customer=self.customer,
            subtotal=Decimal('500.00'),
            vat_amount=Decimal('80.00'),
            total=Decimal('580.00'),
            amount_paid=Decimal('580.00'),
        )

        ret = SaleReturn.objects.create(
            original_sale=sale,
            customer=self.customer,
            processed_by=self.user,
            subtotal=Decimal('250.00'),
            vat_amount=Decimal('40.00'),
            total_refund=Decimal('290.00'),
            reason='defective',
            refund_method=self.payment_method,
        )

        self.assertTrue(ret.return_number.startswith('RET-'))

        event = OutboxEvent.objects.filter(
            event_name='pos.sale_refunded.v1',
            status=OutboxEvent.STATUS_PENDING,
        ).first()

        self.assertIsNotNone(event)
        self.assertEqual(event.payload['return_number'], ret.return_number)
        self.assertEqual(event.payload['original_invoice'], sale.invoice_number)
        self.assertEqual(event.payload['total_refund_amount'], '290.00')

    def test_audit_mixin_logs_to_core_audit_log(self):
        """Saving models with AuditModelMixin writes records to Core AuditLog."""
        sale = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.user,
            customer=self.customer,
            subtotal=Decimal('300.00'),
            vat_amount=Decimal('48.00'),
            total=Decimal('348.00'),
            amount_paid=Decimal('350.00'),
        )

        core_audit = AuditLog.objects.filter(
            action='create',
            object_id=str(sale.pk)
        ).first()

        self.assertIsNotNone(core_audit)
        self.assertIn('Invoice', core_audit.object_repr)

    def test_pos_public_api_boundary_for_hr(self):
        """HR module functions can query POS cashier metrics via pos.api without direct model imports."""
        # Create sales
        sale1 = Sale.objects.create(
            business=self.business,
            branch=self.branch,
            cashier=self.user,
            customer=self.customer,
            subtotal=Decimal('500.00'),
            vat_amount=Decimal('80.00'),
            total=Decimal('580.00'),
            amount_paid=Decimal('600.00'),
        )
        SaleItem.objects.create(
            business=self.business,
            sale=sale1,
            product=self.product,
            quantity=Decimal('2.000'),
            unit_price=Decimal('250.00'),
            total_price=Decimal('500.00'),
        )

        today = timezone.now().date()
        metrics = pos_api.get_cashier_performance_metrics(
            business_id=self.business.id,
            cashier_user_id=self.user.id,
            period_start=today - timedelta(days=1),
            period_end=today + timedelta(days=1),
        )

        self.assertEqual(metrics['total_sales'], 1)
        self.assertEqual(metrics['total_transactions'], 2)
        self.assertEqual(metrics['total_refunds'], 0)

        # Test shift summary
        shift = Shift.objects.create(
            cashier=self.user,
            opening_cash=Decimal('1000.00')
        )
        summary = pos_api.get_shift_summary(shift.id)
        self.assertIsNotNone(summary)
        self.assertEqual(summary['cashier_id'], self.user.id)
        self.assertFalse(summary['is_closed'])
