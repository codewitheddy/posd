from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0089_normalize_product_types_to_stock'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='product_type',
        ),
    ]
