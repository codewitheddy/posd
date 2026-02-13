# Generated migration to add business field to LoyaltyReward

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0033_merge_20260214_0014'),
    ]

    operations = [
        # Add business field (nullable first)
        migrations.AddField(
            model_name='loyaltyreward',
            name='business',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='loyalty_rewards',
                to='pos.business'
            ),
        ),
    ]
