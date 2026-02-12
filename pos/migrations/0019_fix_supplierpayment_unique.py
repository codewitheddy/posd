# Fix SupplierPayment unique constraint for multi-tenancy

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0018_fix_sale_invoice_unique'),
    ]

    operations = [
        # Add unique_together constraint for business + payment_number
        migrations.AlterUniqueTogether(
            name='supplierpayment',
            unique_together={('business', 'payment_number')},
        ),
    ]
