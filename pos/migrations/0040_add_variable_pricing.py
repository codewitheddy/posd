# Generated migration for variable pricing feature

from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0039_goodsreturnednote_goodsreturnednoteitem'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_variable_price',
            field=models.BooleanField(
                default=False,
                help_text='Enable variable pricing (price calculated by weight/quantity)'
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='price_per_unit',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=2,
                null=True,
                blank=True,
                help_text='Price per unit (e.g., price per 100g, per kg, per liter)'
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='pricing_unit_quantity',
            field=models.DecimalField(
                max_digits=10,
                decimal_places=3,
                default=Decimal('1.000'),
                help_text='Quantity for pricing unit (e.g., 100 for "per 100g", 1 for "per kg")'
            ),
        ),
    ]
