"""
Unit & Integration Tests for Phase 2: Core Platform & Shared Foundations
Validates Party, UOM, Tax, Currency, Document Numbering, and Multi-Tenant Isolation.
"""
from decimal import Decimal
from django.test import TestCase
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from core.models import (
    Company,
    Branch,
    Party,
    UnitOfMeasure,
    UOMConversion,
    TaxRate,
    Currency,
    ExchangeRate,
    DocumentSequence,
)
from core.services import (
    create_party,
    update_party,
    check_credit_limit,
    calculate_tax,
    convert_quantity,
    convert_currency,
    next_document_number,
)
from core.selectors import (
    get_parties,
    get_customers,
    get_vendors,
    get_tax_rates,
    get_units_of_measure,
)

User = get_user_model()


class CorePlatformFoundationsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testadmin', password='testpassword123')
        
        # Create 2 Tenant Companies for multi-tenancy tests
        self.company_a = Company.objects.create(
            name="Retail Hub Kenya",
            slug="retail-hub-kenya",
            kra_pin="P051234567Z",
            currency="KES",
        )
        self.branch_a1 = Branch.objects.create(
            company=self.company_a,
            name="Nairobi CBD",
            code="CBD",
            is_headquarters=True,
        )

        self.company_b = Company.objects.create(
            name="Mombasa Wholesale Ltd",
            slug="mombasa-wholesale",
            kra_pin="P057654321A",
            currency="KES",
        )

    def test_party_creation_and_auto_numbering(self):
        """Test party creation with explicit code and auto-generated code."""
        # 1. Explicit code
        customer = create_party(
            company=self.company_a,
            name="Acme Corp Ltd",
            party_type=Party.PARTY_TYPE_CUSTOMER,
            code="CUST-ACME",
            tax_pin="P059999999X",
            phone="+254711000000",
            credit_limit=Decimal('50000.00'),
            payment_terms=Party.PAYMENT_TERMS_NET30,
            created_by=self.user,
        )
        self.assertEqual(customer.code, "CUST-ACME")
        self.assertEqual(customer.company, self.company_a)
        self.assertTrue(customer.is_customer)
        self.assertFalse(customer.is_vendor)

        # 2. Auto-generated code
        vendor = create_party(
            company=self.company_a,
            name="Kenya Supplies Ltd",
            party_type=Party.PARTY_TYPE_VENDOR,
            created_by=self.user,
        )
        self.assertTrue(vendor.code.startswith("VEND-"))
        self.assertTrue(vendor.is_vendor)

    def test_party_credit_limit_validation(self):
        """Test credit limit verification helper."""
        customer = create_party(
            company=self.company_a,
            name="Credit Customer",
            party_type=Party.PARTY_TYPE_CUSTOMER,
            credit_limit=Decimal('10000.00'),
        )

        # Allowed within limit: 4000 + 5000 <= 10000
        self.assertTrue(check_credit_limit(customer, requested_amount=Decimal('5000.00'), current_outstanding=Decimal('4000.00')))
        # Exceeds limit: 4000 + 7000 > 10000
        self.assertFalse(check_credit_limit(customer, requested_amount=Decimal('7000.00'), current_outstanding=Decimal('4000.00')))

    def test_uom_creation_and_conversion(self):
        """Test unit of measure conversion calculations."""
        pcs = UnitOfMeasure.objects.create(
            company=self.company_a,
            name="Piece",
            code="PCS",
            category=UnitOfMeasure.CATEGORY_UNIT,
            is_base_unit=True,
        )
        box = UnitOfMeasure.objects.create(
            company=self.company_a,
            name="Box of 12",
            code="BOX12",
            category=UnitOfMeasure.CATEGORY_UNIT,
        )
        # 1 Box = 12 Pieces
        UOMConversion.objects.create(
            company=self.company_a,
            from_uom=box,
            to_uom=pcs,
            conversion_factor=Decimal('12.000000'),
        )

        # Convert 5 Boxes to Pieces => 60 Pieces
        qty_pcs = convert_quantity(
            quantity=Decimal('5'),
            from_uom=box,
            to_uom=pcs,
            company=self.company_a,
        )
        self.assertEqual(qty_pcs, Decimal('60.0000'))

        # Inverse: Convert 24 Pieces to Boxes => 2 Boxes
        qty_box = convert_quantity(
            quantity=Decimal('24'),
            from_uom=pcs,
            to_uom=box,
            company=self.company_a,
        )
        self.assertEqual(qty_box, Decimal('2.0000'))

    def test_tax_calculations_inclusive_and_exclusive(self):
        """Test VAT calculation for 16% inclusive and exclusive prices."""
        vat16 = TaxRate.objects.create(
            company=self.company_a,
            name="Standard VAT 16%",
            code="VAT-16",
            rate=Decimal('16.00'),
            kra_etims_code="A",
            is_default=True,
        )

        # 1. Tax Inclusive: Gross 116.00 => Base 100.00, Tax 16.00
        calc_inc = calculate_tax(amount=Decimal('116.00'), tax_rate=vat16, is_inclusive=True)
        self.assertEqual(calc_inc['base_amount'], Decimal('100.00'))
        self.assertEqual(calc_inc['tax_amount'], Decimal('16.00'))
        self.assertEqual(calc_inc['gross_amount'], Decimal('116.00'))

        # 2. Tax Exclusive: Base 1000.00 => Tax 160.00, Gross 1160.00
        calc_exc = calculate_tax(amount=Decimal('1000.00'), tax_rate=vat16, is_inclusive=False)
        self.assertEqual(calc_exc['base_amount'], Decimal('1000.00'))
        self.assertEqual(calc_exc['tax_amount'], Decimal('160.00'))
        self.assertEqual(calc_exc['gross_amount'], Decimal('1160.00'))

    def test_currency_exchange_conversion(self):
        """Test multi-currency exchange rate conversions."""
        kes = Currency.objects.create(code="KES", name="Kenya Shilling", symbol="KSh")
        usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$")

        # 1 USD = 130 KES
        ExchangeRate.objects.create(
            company=self.company_a,
            from_currency=usd,
            to_currency=kes,
            rate=Decimal('130.000000'),
        )

        # Convert 100 USD to KES => 13,000.00 KES
        amount_kes = convert_currency(
            amount=Decimal('100.00'),
            from_currency=usd,
            to_currency=kes,
            company=self.company_a,
        )
        self.assertEqual(amount_kes, Decimal('13000.00'))

        # Inverse: Convert 26,000 KES to USD => 200.00 USD
        amount_usd = convert_currency(
            amount=Decimal('26000.00'),
            from_currency=kes,
            to_currency=usd,
            company=self.company_a,
        )
        self.assertEqual(amount_usd, Decimal('200.00'))

    def test_document_sequence_atomic_generation(self):
        """Test consecutive atomic document number generation."""
        doc1 = next_document_number(
            document_type='sale_invoice',
            company=self.company_a,
            branch=self.branch_a1,
            prefix='INV',
        )
        doc2 = next_document_number(
            document_type='sale_invoice',
            company=self.company_a,
            branch=self.branch_a1,
            prefix='INV',
        )
        self.assertTrue(doc1.endswith('-0001'))
        self.assertTrue(doc2.endswith('-0002'))

    def test_multi_tenant_isolation(self):
        """Verify Company A's parties and rates are isolated from Company B."""
        create_party(company=self.company_a, name="Company A Customer", code="CUST-001")
        create_party(company=self.company_b, name="Company B Customer", code="CUST-001")

        parties_a = get_parties(self.company_a)
        parties_b = get_parties(self.company_b)

        self.assertEqual(parties_a.count(), 1)
        self.assertEqual(parties_b.count(), 1)
        self.assertEqual(parties_a.first().name, "Company A Customer")
        self.assertEqual(parties_b.first().name, "Company B Customer")
