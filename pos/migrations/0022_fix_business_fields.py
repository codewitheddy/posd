# Generated migration to fix business field inconsistencies

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0021_fix_supplierpayment_payment_number_unique'),
    ]

    operations = [
        # Remove business field from ActivityLog
        migrations.RemoveField(
            model_name='activitylog',
            name='business',
        ),
        
        # Make business field non-nullable on Customer
        migrations.AlterField(
            model_name='customer',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='pos.business'),
        ),
    ]
