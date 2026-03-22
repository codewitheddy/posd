from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0066_add_goods_received_note'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Expand status field length to accommodate new values
        migrations.AlterField(
            model_name='purchase',
            name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('pending_approval', 'Pending Approval'),
                    ('approved', 'Approved'),
                    ('sent', 'Sent to Supplier'),
                    ('pending', 'Pending'),
                    ('ordered', 'Ordered'),
                    ('partially_received', 'Partially Received'),
                    ('received', 'Received'),
                    ('cancelled', 'Cancelled'),
                    ('closed', 'Closed'),
                ],
                default='draft',
                max_length=20,
            ),
        ),
        # Add discount_amount to Purchase
        migrations.AddField(
            model_name='purchase',
            name='discount_amount',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        # Workflow tracking fields
        migrations.AddField(
            model_name='purchase',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_purchases', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='purchase',
            name='submitted_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='submitted_purchases', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='purchase',
            name='submitted_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchase',
            name='approved_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='approved_purchases', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='purchase',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchase',
            name='sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # PurchaseItem: add description and discount
        migrations.AddField(
            model_name='purchaseitem',
            name='description',
            field=models.CharField(blank=True, help_text='Optional item description / override', max_length=255),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='discount',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Discount percentage (0-100)', max_digits=5),
        ),
    ]
