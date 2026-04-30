# Performance optimization: Add indexes on frequently queried fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0076_add_password_history'),
    ]

    operations = [
        # Product: barcode lookup, active catalog, low stock queries
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['business', 'is_active'], name='pos_product_bus_active_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['business', 'product_code'], name='pos_product_bus_code_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['business', 'barcode'], name='pos_product_bus_barcode_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['business', 'stock_quantity'], name='pos_product_bus_stock_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['business', 'category'], name='pos_product_bus_cat_idx'),
        ),

        # Sale: date-range reporting, cashier reports, status filters
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['business', 'date'], name='pos_sale_bus_date_idx'),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['business', 'cashier', 'date'], name='pos_sale_bus_cashier_date_idx'),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['business', 'customer'], name='pos_sale_bus_customer_idx'),
        ),

        # Customer: phone/email lookup, tier filtering
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['business', 'phone'], name='pos_customer_bus_phone_idx'),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['business', 'tier'], name='pos_customer_bus_tier_idx'),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['business', 'is_active'], name='pos_customer_bus_active_idx'),
        ),

        # StockAdjustment: product history, date range
        migrations.AddIndex(
            model_name='stockadjustment',
            index=models.Index(fields=['business', 'product', 'created_at'], name='pos_stockadj_bus_prod_dt_idx'),
        ),
        migrations.AddIndex(
            model_name='stockadjustment',
            index=models.Index(fields=['business', 'created_at'], name='pos_stockadj_bus_dt_idx'),
        ),

        # Purchase: date and status filtering
        migrations.AddIndex(
            model_name='purchase',
            index=models.Index(fields=['business', 'date'], name='pos_purchase_bus_date_idx'),
        ),
        migrations.AddIndex(
            model_name='purchase',
            index=models.Index(fields=['business', 'status'], name='pos_purchase_bus_status_idx'),
        ),
    ]
