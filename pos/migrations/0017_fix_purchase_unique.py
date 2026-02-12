# Generated migration to fix Purchase purchase_number unique constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0016_fix_category_unique'),
    ]

    operations = [
        # Remove unique constraint on purchase_number field if it exists
        migrations.AlterField(
            model_name='purchase',
            name='purchase_number',
            field=models.CharField(max_length=50),  # No unique=True
        ),
    ]
