from decimal import Decimal
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0082_remove_customer_pos_customer_bus_phone_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='unit_barcode',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                help_text='Barcode for the individual base unit (distinct from bulk barcode)',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='product',
            name='bulk_low_stock_threshold',
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                help_text='Alert when stock falls below this many bulk units',
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='bulk_discount_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal('0'))],
                help_text='Per-unit price when customer buys at least one full bulk unit quantity',
            ),
        ),
        migrations.AlterField(
            model_name='stockadjustment',
            name='adjustment_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('restock', 'Restock'),
                    ('damage', 'Damage/Loss'),
                    ('return', 'Customer Return'),
                    ('correction', 'Stock Correction'),
                    ('sale', 'Sale'),
                    ('bulk_break', 'Bulk Break'),
                ],
            ),
        ),
    ]
