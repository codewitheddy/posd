# Generated manually for purchase cancellation tracking

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pos', '0052_merge_20260218_1941'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchase',
            name='cancellation_reason',
            field=models.TextField(blank=True, help_text='Reason for cancelling this purchase order'),
        ),
        migrations.AddField(
            model_name='purchase',
            name='cancelled_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='cancelled_purchases',
                to=settings.AUTH_USER_MODEL,
                help_text='User who cancelled this purchase order'
            ),
        ),
        migrations.AddField(
            model_name='purchase',
            name='cancelled_at',
            field=models.DateTimeField(blank=True, null=True, help_text='When this purchase order was cancelled'),
        ),
    ]
