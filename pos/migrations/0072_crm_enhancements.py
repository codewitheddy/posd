from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0071_fix_expense_payment_method'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add credit + tags fields to Customer
        migrations.AddField(
            model_name='customer',
            name='tags',
            field=models.CharField(blank=True, max_length=500, help_text='Comma-separated tags'),
        ),
        migrations.AddField(
            model_name='customer',
            name='credit_limit',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, help_text='Maximum credit allowed'),
        ),
        migrations.AddField(
            model_name='customer',
            name='credit_balance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, help_text='Current outstanding credit balance'),
        ),
        # Add credit fields to Sale
        migrations.AddField(
            model_name='sale',
            name='is_credit_sale',
            field=models.BooleanField(default=False, help_text='Sale made on credit'),
        ),
        migrations.AddField(
            model_name='sale',
            name='credit_paid',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, help_text='Amount paid against credit'),
        ),
        # CustomerPayment model
        migrations.CreateModel(
            name='CustomerPayment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('reference', models.CharField(blank=True, max_length=100, help_text='Cheque/M-Pesa reference')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_payments', to='pos.business')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credit_payments', to='pos.customer')),
                ('payment_method', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='pos.paymentmethod')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        # CustomerSegment model
        migrations.CreateModel(
            name='CustomerSegment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('criteria', models.CharField(choices=[('all', 'All Customers'), ('vip', 'VIP Customers'), ('wholesale', 'Wholesale Customers'), ('high_value', 'High Value (Top Spenders)'), ('inactive', 'Inactive (No purchase in 90 days)'), ('loyalty_tier', 'By Loyalty Tier'), ('credit_overdue', 'Credit Overdue')], default='all', max_length=30)),
                ('criteria_value', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_segments', to='pos.business')),
            ],
            options={'ordering': ['name']},
        ),
        # Campaign model
        migrations.CreateModel(
            name='Campaign',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('subject', models.CharField(blank=True, max_length=300)),
                ('message', models.TextField()),
                ('channel', models.CharField(choices=[('email', 'Email'), ('sms', 'SMS')], default='email', max_length=10)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('scheduled', 'Scheduled'), ('sent', 'Sent'), ('failed', 'Failed')], default='draft', max_length=20)),
                ('scheduled_at', models.DateTimeField(blank=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('recipients_count', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='campaigns', to='pos.business')),
                ('segment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='pos.customersegment')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
