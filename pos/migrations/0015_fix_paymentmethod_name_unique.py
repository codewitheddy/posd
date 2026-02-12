# Generated migration to fix PaymentMethod name unique constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0014_merge_20260213_0012'),
    ]

    operations = [
        # Remove unique constraint on name field if it exists
        migrations.AlterField(
            model_name='paymentmethod',
            name='name',
            field=models.CharField(max_length=100),  # No unique=True
        ),
    ]
