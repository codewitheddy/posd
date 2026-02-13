# Generated migration to add cost_price field to Product model

from django.db import migrations, models
from decimal import Decimal


def set_default_cost_price(apps, schema_editor):
    """Set cost_price to 0 for existing products"""
    Product = apps.get_model('pos', 'Product')
    Product.objects.filter(cost_price__isnull=True).update(cost_price=Decimal('0.00'))


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0026_alter_businesssettings_vat_rate_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='cost_price',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Cost price (what you pay to stock the product)',
                max_digits=10
            ),
        ),
        migrations.RunPython(set_default_cost_price, migrations.RunPython.noop),
    ]
