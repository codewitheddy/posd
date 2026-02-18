# Generated migration for adding performance indexes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0050_add_cash_float_management'),
    ]

    operations = [
        # Add index to Sale.date for faster date-based queries
        migrations.AlterField(
            model_name='sale',
            name='date',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        # Add index to Product.barcode for faster barcode lookups
        migrations.AlterField(
            model_name='product',
            name='barcode',
            field=models.CharField(max_length=100, blank=True, db_index=True, help_text="Barcode for scanning (EAN, UPC, etc.)"),
        ),
        # Add index to Customer.phone for faster phone lookups
        migrations.AlterField(
            model_name='customer',
            name='phone',
            field=models.CharField(max_length=20, blank=True, db_index=True),
        ),
        # Add index to Purchase.date for faster date-based queries
        migrations.AlterField(
            model_name='purchase',
            name='date',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
    ]
