# Generated migration for subscription payment tracking

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0044_make_cost_price_required'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, help_text='Payment amount', max_digits=10)),
                ('currency', models.CharField(default='KES', max_length=10)),
                ('payment_method', models.CharField(choices=[('mpesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer'), ('cash', 'Cash'), ('card', 'Card'), ('paypal', 'PayPal'), ('other', 'Other')], default='mpesa', max_length=50)),
                ('payment_reference', models.CharField(blank=True, help_text='Transaction ID or reference number', max_length=200)),
                ('payment_date', models.DateTimeField(help_text='Date payment was received')),
                ('period_start', models.DateField(help_text='Subscription period start date')),
                ('period_end', models.DateField(help_text='Subscription period end date')),
                ('plan', models.CharField(choices=[('free', 'Free'), ('basic', 'Basic'), ('professional', 'Professional'), ('enterprise', 'Enterprise')], max_length=50)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='completed', max_length=20)),
                ('notes', models.TextField(blank=True, help_text='Additional notes about this payment')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscription_payments', to='pos.business')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recorded_payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Subscription Payment',
                'verbose_name_plural': 'Subscription Payments',
                'ordering': ['-payment_date'],
            },
        ),
        migrations.AddIndex(
            model_name='subscriptionpayment',
            index=models.Index(fields=['business', '-payment_date'], name='pos_subscri_busines_idx'),
        ),
        migrations.AddIndex(
            model_name='subscriptionpayment',
            index=models.Index(fields=['status'], name='pos_subscri_status_idx'),
        ),
    ]
