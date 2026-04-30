from django.db import migrations


def normalize_product_types_to_stock(apps, schema_editor):
    Product = apps.get_model('pos', 'Product')
    Product.objects.exclude(product_type='stock').update(product_type='stock')


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0088_backupauditlog'),
    ]

    operations = [
        migrations.RunPython(
            normalize_product_types_to_stock,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
