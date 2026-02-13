# Generated migration to make phone required and add index

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0030_add_barcode_field'),
    ]

    operations = [
        # Make phone field required (remove blank=True)
        migrations.AlterField(
            model_name='customer',
            name='phone',
            field=models.CharField(max_length=20, help_text="Phone number (required for loyalty lookup)"),
        ),
        # Add index on phone for faster lookups
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['business', 'phone'], name='pos_customer_phone_idx'),
        ),
        # Add index on customer_code for faster lookups
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['business', 'customer_code'], name='pos_customer_code_idx'),
        ),
    ]
