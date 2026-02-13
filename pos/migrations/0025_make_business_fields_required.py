# Generated migration to make business fields non-nullable
# Safe because all existing records already have business_id values

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0024_fix_supplierpayment_business'),
    ]

    operations = [
        # Make business field non-nullable on all models that have it
        migrations.AlterField(
            model_name='paymentmethod',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_methods', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='purchase',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='purchases', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='purchaseitem',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='purchase_items', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='sale',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sales', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='saleitem',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sale_items', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='salepayment',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sale_payments', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='stockadjustment',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_adjustments', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='supplier',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suppliers', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='supplierpayment',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supplier_payments', to='pos.business'),
        ),
    ]
