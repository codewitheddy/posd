# Performance optimization migration - Add database indexes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0040_add_variable_pricing'),
    ]

    operations = [
        # Product indexes for fast lookups
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['barcode'], name='pos_product_barcode_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['product_code'], name='pos_product_code_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['business', 'stock_quantity'], name='pos_product_stock_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['business', 'category'], name='pos_product_cat_idx'),
        ),
        
        # Customer indexes for fast phone lookup
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['business', 'phone'], name='pos_customer_phone_idx'),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['customer_code'], name='pos_customer_code_idx'),
        ),
        
        # Sale indexes for reports and queries
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['business', 'date'], name='pos_sale_date_idx'),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['invoice_number'], name='pos_sale_invoice_idx'),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['business', 'cashier', 'date'], name='pos_sale_cashier_idx'),
        ),
        
        # SaleItem indexes for reporting
        migrations.AddIndex(
            model_name='saleitem',
            index=models.Index(fields=['business', 'sale'], name='pos_saleitem_sale_idx'),
        ),
        migrations.AddIndex(
            model_name='saleitem',
            index=models.Index(fields=['product'], name='pos_saleitem_product_idx'),
        ),
        
        # Purchase indexes
        migrations.AddIndex(
            model_name='purchase',
            index=models.Index(fields=['business', 'date'], name='pos_purchase_date_idx'),
        ),
        migrations.AddIndex(
            model_name='purchase',
            index=models.Index(fields=['business', 'supplier'], name='pos_purchase_supplier_idx'),
        ),
        
        # Supplier indexes
        migrations.AddIndex(
            model_name='supplier',
            index=models.Index(fields=['business', 'is_active'], name='pos_supplier_active_idx'),
        ),
        
        # Shift indexes for Z-reports
        migrations.AddIndex(
            model_name='shift',
            index=models.Index(fields=['cashier', 'start_time'], name='pos_shift_cashier_idx'),
        ),
        migrations.AddIndex(
            model_name='shift',
            index=models.Index(fields=['status', 'start_time'], name='pos_shift_status_idx'),
        ),
    ]
