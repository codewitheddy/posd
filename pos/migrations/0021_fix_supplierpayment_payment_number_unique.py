# Fix SupplierPayment payment_number unique constraint for multi-tenancy
# Remove global unique constraint, keep only unique_together with business

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0020_convert_businesssettings_to_per_business'),
    ]

    operations = [
        # Remove global unique constraint from payment_number field
        migrations.AlterField(
            model_name='supplierpayment',
            name='payment_number',
            field=models.CharField(editable=False, max_length=20),
        ),
    ]
