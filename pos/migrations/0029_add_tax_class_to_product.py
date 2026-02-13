# Add tax_class field to Product model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0028_add_expiry_to_purchaseitem'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='tax_class',
            field=models.CharField(
                choices=[
                    ('standard', 'Standard (16% VAT)'),
                    ('zero_rated', 'Zero Rated (0% VAT)'),
                    ('exempt', 'Exempt (No VAT)')
                ],
                default='standard',
                help_text='Tax classification for this product',
                max_length=20
            ),
        ),
    ]
