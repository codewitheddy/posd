# Generated migration to fix Category name unique constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0015_fix_paymentmethod_name_unique'),
    ]

    operations = [
        # Remove unique constraint on name field if it exists
        migrations.AlterField(
            model_name='category',
            name='name',
            field=models.CharField(max_length=100),  # No unique=True
        ),
    ]
