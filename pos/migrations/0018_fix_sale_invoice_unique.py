# Generated migration to fix Sale invoice_number unique constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0017_fix_purchase_unique'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sale',
            name='invoice_number',
            field=models.CharField(editable=False, max_length=20),
        ),
    ]
