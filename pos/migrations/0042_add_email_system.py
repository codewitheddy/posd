from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0041_add_performance_indexes'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessEmailSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('use_custom_smtp', models.BooleanField(default=False, help_text='Use custom SMTP settings instead of global')),
                ('smtp_host', models.CharField(blank=True, max_length=200)),
                ('smtp_port', models.IntegerField(default=587)),
                ('smtp_username', models.CharField(blank=True, max_length=200)),
                ('smtp_password', models.CharField(blank=True, max_length=200)),
                ('from_email', models.EmailField(blank=True, max_length=254)),
                ('send_purchase_orders', models.BooleanField(default=True, help_text='Send purchase orders to suppliers')),
                ('send_grn_notifications', models.BooleanField(default=True, help_text='Send GRN notifications to suppliers')),
                ('send_payment_confirmations', models.BooleanField(default=True, help_text='Send payment confirmations to suppliers')),
                ('send_license_reminders', models.BooleanField(default=True, help_text='Send license expiry reminders')),
                ('send_low_stock_alerts', models.BooleanField(default=True, help_text='Send low stock alerts')),
                ('send_daily_summaries', models.BooleanField(default=False, help_text='Send daily sales summaries')),
                ('admin_emails', models.TextField(blank=True, help_text='Comma-separated admin emails')),
                ('manager_emails', models.TextField(blank=True, help_text='Comma-separated manager emails')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='email_settings', to='pos.business')),
            ],
            options={
                'verbose_name': 'Business Email Settings',
                'verbose_name_plural': 'Business Email Settings',
            },
        ),
        migrations.CreateModel(
            name='EmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('template_type', models.CharField(choices=[
                    ('purchase_order', 'Purchase Order'),
                    ('grn', 'Goods Returned Note'),
                    ('payment_confirmation', 'Payment Confirmation'),
                    ('license_expiry', 'License Expiry'),
                    ('sale_receipt', 'Sale Receipt'),
                    ('low_stock', 'Low Stock Alert'),
                    ('daily_summary', 'Daily Summary'),
                ], max_length=50)),
                ('subject', models.CharField(max_length=200)),
                ('body_html', models.TextField(help_text='HTML email body with {variable} placeholders')),
                ('body_text', models.TextField(help_text='Plain text email body with {variable} placeholders')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_templates', to='pos.business')),
            ],
            options={
                'verbose_name': 'Email Template',
                'verbose_name_plural': 'Email Templates',
                'ordering': ['template_type', 'name'],
            },
        ),
        migrations.CreateModel(
            name='EmailLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('template_type', models.CharField(max_length=50)),
                ('recipient', models.EmailField(max_length=254)),
                ('subject', models.CharField(max_length=200)),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending'),
                    ('sent', 'Sent'),
                    ('failed', 'Failed'),
                ], default='pending', max_length=20)),
                ('error_message', models.TextField(blank=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='email_logs', to='pos.business')),
            ],
            options={
                'verbose_name': 'Email Log',
                'verbose_name_plural': 'Email Logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='emaillog',
            index=models.Index(fields=['business', 'status', '-created_at'], name='pos_emaillo_busines_idx'),
        ),
        migrations.AddIndex(
            model_name='emaillog',
            index=models.Index(fields=['template_type', '-created_at'], name='pos_emaillo_templat_idx'),
        ),
    ]
