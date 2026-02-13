# Add expiry date and batch tracking to PurchaseItem

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0027_add_cost_price_to_product'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseitem',
            name='expiry_date',
            field=models.DateField(
                blank=True,
                null=True,
                help_text='Expiry date for this batch of products'
            ),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='batch_number',
            field=models.CharField(
                max_length=100,
                blank=True,
                help_text='Batch or lot number for tracking'
            ),
        ),
    ]
