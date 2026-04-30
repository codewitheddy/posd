"""
Business-specific data restore management command
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from pos.models import Business
import json
import os
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Restore business data from JSON backup file'

    def add_arguments(self, parser):
        parser.add_argument('backup_file', type=str, help='Path to the business backup JSON file')
        parser.add_argument('--confirm', action='store_true', help='Confirm restoration (required for safety)')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be restored without doing it')
        parser.add_argument('--create-business', action='store_true', help='Create business if it does not exist')

    def handle(self, *args, **options):
        backup_file = options['backup_file']
        confirm = options['confirm']
        dry_run = options['dry_run']

        if not os.path.exists(backup_file):
            self.stdout.write(self.style.ERROR('Backup file not found: ' + backup_file))
            return

        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
        except Exception as e:
            self.stdout.write(self.style.ERROR('Failed to load backup file: ' + str(e)))
            return

        if 'metadata' not in backup_data or 'business' not in backup_data:
            self.stdout.write(self.style.ERROR('Invalid backup file format'))
            return

        metadata = backup_data['metadata']
        business_slug = metadata.get('business_slug')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes will be made'))
            self._show_plan(backup_data)
            return

        if not confirm:
            self.stdout.write(self.style.WARNING('Use --confirm to proceed with restoration.'))
            self._show_plan(backup_data)
            return

        try:
            business = Business.objects.get(slug=business_slug)
            self.stdout.write('Restoring into business: ' + business.name)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR('Business not found: ' + str(business_slug)))
            return

        self._show_plan(backup_data)
        self._restore(backup_data, business)
        self.stdout.write(self.style.SUCCESS('Restoration completed'))

    def _show_plan(self, backup_data):
        self.stdout.write('Backup date: ' + str(backup_data['metadata'].get('backup_date', 'unknown')))
        for key, val in backup_data.items():
            if key not in ('metadata', 'business') and isinstance(val, list):
                self.stdout.write('  ' + key + ': ' + str(len(val)) + ' records')

    def _d(self, val, default=0):
        """Safely coerce a value to Decimal."""
        from decimal import Decimal, InvalidOperation
        if val is None:
            return Decimal(str(default))
        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError):
            return Decimal(str(default))

    def _restore(self, backup_data, business):
        from pos.models import (
            Category, PaymentMethod, Supplier, Customer,
            Product, Purchase, PurchaseItem, Sale, SaleItem, SalePayment,
        )

        # --- Categories ---
        cat_map = {}
        for entry in backup_data.get('categories', []):
            f = entry['fields']
            obj, _ = Category.objects.get_or_create(
                business=business,
                name=f['name'],
            )
            cat_map[entry['pk']] = obj
        self.stdout.write('Categories: ' + str(len(cat_map)))

        # --- Payment Methods ---
        pm_map = {}
        for entry in backup_data.get('payment_methods', []):
            f = entry['fields']
            obj, _ = PaymentMethod.objects.get_or_create(
                business=business,
                code=f['code'],
                defaults={
                    'name': f['name'],
                    'is_active': f.get('is_active', True),
                }
            )
            pm_map[entry['pk']] = obj
        self.stdout.write('Payment methods: ' + str(len(pm_map)))

        # --- Suppliers ---
        sup_map = {}
        for entry in backup_data.get('suppliers', []):
            f = entry['fields']
            obj, _ = Supplier.objects.get_or_create(
                business=business,
                name=f['name'],
                defaults={
                    'contact_person': f.get('contact_person', ''),
                    'phone': f.get('phone', ''),
                    'email': f.get('email', ''),
                    'address': f.get('address', ''),
                }
            )
            sup_map[entry['pk']] = obj
        self.stdout.write('Suppliers: ' + str(len(sup_map)))

        # --- Customers ---
        cust_map = {}
        for entry in backup_data.get('customers', []):
            f = entry['fields']
            try:
                obj, _ = Customer.objects.get_or_create(
                    business=business,
                    phone=f.get('phone', ''),
                    defaults={
                        'name': f['name'],
                        'email': f.get('email', ''),
                        'address': f.get('address', ''),
                        'tier': f.get('tier', 'bronze'),
                        'loyalty_points': int(f.get('loyalty_points', f.get('points', 0)) or 0),
                        'is_active': f.get('is_active', f.get('active', True)),
                        'notes': f.get('notes', ''),
                        'customer_type': f.get('customer_type', 'regular'),
                        'total_purchases': self._d(f.get('total_purchases', 0)),
                        'visit_count': int(f.get('visit_count', 0) or 0),
                        'credit_limit': self._d(f.get('credit_limit', 0)),
                        'credit_balance': self._d(f.get('credit_balance', 0)),
                    }
                )
                cust_map[entry['pk']] = obj
            except Exception as e:
                self.stdout.write(self.style.WARNING('Customer failed: ' + str(e)))
        self.stdout.write('Customers: ' + str(len(cust_map)))

        # --- Products ---
        prod_map = {}
        for entry in backup_data.get('products', []):
            f = entry['fields']
            cat = cat_map.get(f.get('category')) if f.get('category') else None
            try:
                obj, _ = Product.objects.get_or_create(
                    business=business,
                    name=f['name'],
                    defaults={
                        'description': f.get('description', ''),
                        'barcode': f.get('barcode', ''),
                        'product_code': f.get('product_code') or None,
                        'category': cat,
                        'unit_price': self._d(f.get('unit_price', 0)),
                        'cost_price': self._d(f.get('cost_price', 0)),
                        'minimum_price': self._d(f.get('minimum_price')) if f.get('minimum_price') else None,
                        'stock_quantity': self._d(f.get('stock_quantity', 0)),
                        'low_stock_threshold': self._d(f.get('low_stock_threshold', f.get('reorder_level', 10))),
                        'reorder_quantity': self._d(f.get('reorder_quantity', 0)),
                        'is_active': f.get('is_active', True),
                        'tax_class': f.get('tax_class', 'standard'),
                        'bulk_unit_name': f.get('bulk_unit_name', ''),
                        'bulk_unit_quantity': self._d(f.get('bulk_unit_quantity')) if f.get('bulk_unit_quantity') else None,
                        'bulk_unit_price': self._d(f.get('bulk_unit_price')) if f.get('bulk_unit_price') else None,
                        'is_variable_price': f.get('is_variable_price', False),
                        'price_per_unit': self._d(f.get('price_per_unit')) if f.get('price_per_unit') else None,
                    }
                )
                prod_map[entry['pk']] = obj
            except Exception as e:
                self.stdout.write(self.style.WARNING('Product failed: ' + f['name'] + ' - ' + str(e)))
        self.stdout.write('Products: ' + str(len(prod_map)))

        # --- Purchases ---
        pur_map = {}
        for entry in backup_data.get('purchases', []):
            f = entry['fields']
            supplier = sup_map.get(f.get('supplier'))
            if not supplier:
                continue
            try:
                obj = Purchase(
                    business=business,
                    supplier=supplier,
                    date=f.get('date', timezone.now()),
                    status=f.get('status', 'received'),
                    notes=f.get('notes', ''),
                    subtotal=self._d(f.get('subtotal', 0)),
                    tax_amount=self._d(f.get('tax_amount', 0)),
                    discount_amount=self._d(f.get('discount_amount', 0)),
                    total_amount=self._d(f.get('total_amount', 0)),
                )
                obj.save()
                pur_map[entry['pk']] = obj
            except Exception as e:
                self.stdout.write(self.style.WARNING('Purchase failed: ' + str(e)))
        self.stdout.write('Purchases: ' + str(len(pur_map)))

        # --- Purchase Items ---
        pi_count = 0
        for entry in backup_data.get('purchase_items', []):
            f = entry['fields']
            purchase = pur_map.get(f.get('purchase'))
            product = prod_map.get(f.get('product'))
            if not purchase or not product:
                continue
            try:
                PurchaseItem(
                    business=business,
                    purchase=purchase,
                    product=product,
                    quantity=int(f.get('quantity', 0) or 0),
                    unit_cost=self._d(f.get('unit_cost', 0)),
                    discount=self._d(f.get('discount', 0)),
                    total_cost=self._d(f.get('total_cost', 0)),
                    quantity_received=int(f.get('quantity_received', 0) or 0),
                    quantity_damaged=int(f.get('quantity_damaged', 0) or 0),
                ).save()
                pi_count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING('PurchaseItem failed: ' + str(e)))
        self.stdout.write('Purchase items: ' + str(pi_count))

        # --- Sales ---
        sale_map = {}
        for entry in backup_data.get('sales', []):
            f = entry['fields']
            customer = cust_map.get(f.get('customer')) if f.get('customer') else None
            original_invoice = f.get('invoice_number', '')
            if original_invoice and Sale.objects.filter(business=business, invoice_number=original_invoice).exists():
                sale_map[entry['pk']] = Sale.objects.get(business=business, invoice_number=original_invoice)
                continue
            try:
                obj = Sale(
                    business=business,
                    date=f.get('date', timezone.now()),
                    customer=customer,
                    subtotal=self._d(f.get('subtotal', 0)),
                    discount_amount=self._d(f.get('discount_amount', 0)),
                    discount_type=f.get('discount_type', 'percentage'),
                    discount_value=self._d(f.get('discount_value', 0)),
                    vat_amount=self._d(f.get('vat_amount', f.get('tax_amount', 0))),
                    vat_rate=self._d(f.get('vat_rate', 16)),
                    total=self._d(f.get('total', 0)),
                    amount_paid=self._d(f.get('amount_paid', f.get('total', 0))),
                    status=f.get('status', 'completed'),
                    notes=f.get('notes', ''),
                )
                if original_invoice:
                    obj.invoice_number = original_invoice
                obj.save()
                sale_map[entry['pk']] = obj
            except Exception as e:
                self.stdout.write(self.style.WARNING('Sale failed: ' + str(e)))
        self.stdout.write('Sales: ' + str(len(sale_map)))

        # --- Sale Items ---
        si_count = 0
        for entry in backup_data.get('sale_items', []):
            f = entry['fields']
            sale = sale_map.get(f.get('sale'))
            product = prod_map.get(f.get('product'))
            if not sale or not product:
                continue
            try:
                SaleItem(
                    business=business,
                    sale=sale,
                    product=product,
                    quantity=self._d(f.get('quantity', 1)),
                    unit_price=self._d(f.get('unit_price', 0)),
                    total_price=self._d(f.get('total_price', 0)),
                    note=f.get('note', ''),
                    unit_type=f.get('unit_type', 'base'),
                    unit_name=f.get('unit_name', ''),
                ).save()
                si_count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING('SaleItem failed: ' + str(e)))
        self.stdout.write('Sale items: ' + str(si_count))

        # --- Sale Payments ---
        sp_count = 0
        for entry in backup_data.get('sale_payments', []):
            f = entry['fields']
            sale = sale_map.get(f.get('sale'))
            pm = pm_map.get(f.get('payment_method'))
            if not sale or not pm:
                continue
            try:
                SalePayment(
                    business=business,
                    sale=sale,
                    payment_method=pm,
                    amount=self._d(f.get('amount', 0)),
                ).save()
                sp_count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING('SalePayment failed: ' + str(e)))
        self.stdout.write('Sale payments: ' + str(sp_count))
