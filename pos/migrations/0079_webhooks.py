from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0078_business_setup_completed'),
    ]

    operations = [
        migrations.CreateModel(
            name='Webhook',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('url', models.URLField(max_length=500)),
                ('secret', models.CharField(max_length=100, blank=True, help_text='HMAC-SHA256 signing secret')),
                ('events', models.JSONField(default=list, help_text='List of event types to subscribe to')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='webhooks',
                    to='pos.business',
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='WebhookDelivery',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False)),
                ('event', models.CharField(max_length=100)),
                ('payload', models.JSONField()),
                ('response_status', models.IntegerField(null=True, blank=True)),
                ('response_body', models.TextField(blank=True)),
                ('success', models.BooleanField(default=False)),
                ('attempt', models.IntegerField(default=1)),
                ('delivered_at', models.DateTimeField(auto_now_add=True)),
                ('webhook', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='deliveries',
                    to='pos.webhook',
                )),
            ],
            options={'ordering': ['-delivered_at']},
        ),
    ]
