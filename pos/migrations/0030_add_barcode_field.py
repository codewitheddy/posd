# Add separate barcode field to Product model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0029_add_tax_class_to_product'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='barcode',
            field=models.CharField(
                blank=True,
                max_length=100,
                help_text='Barcode for scanning (EAN, UPC, etc.)'
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='product_code',
            field=models.CharField(
                blank=True,
                max_length=50,
                null=True,
                help_text='Internal product code or SKU'
            ),
        ),
    ]
