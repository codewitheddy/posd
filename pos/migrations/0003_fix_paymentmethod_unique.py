# Generated migration to fix PaymentMethod unique constraint

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0002_multi_tenancy'),
    ]

    operations = [
        # Remove old unique constraint on code field if it exists
        migrations.AlterField(
            model_name='paymentmethod',
            name='code',
            field=models.CharField(max_length=20),
        ),
        # Ensure unique_together is properly set
        migrations.AlterUniqueTogether(
            name='paymentmethod',
            unique_together={('business', 'code')},
        ),
    ]
