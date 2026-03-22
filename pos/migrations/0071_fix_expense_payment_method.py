from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0070_financial_suite'),
    ]

    operations = [
        # Remove the old FK column
        migrations.RemoveField(
            model_name='expense',
            name='payment_method',  # this is the old FK (payment_method_id in DB)
        ),
        # Rename the char field to payment_method
        migrations.RenameField(
            model_name='expense',
            old_name='payment_method_str',
            new_name='payment_method',
        ),
    ]
