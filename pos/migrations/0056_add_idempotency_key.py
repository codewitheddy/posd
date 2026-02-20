# Generated migration for idempotency key management

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0055_update_expiry_alert_days_default'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdempotencyKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(db_index=True, max_length=255, unique=True)),
                ('operation_type', models.CharField(max_length=50)),
                ('request_data', models.JSONField()),
                ('response_data', models.JSONField(blank=True, null=True)),
                ('status', models.CharField(
                    choices=[
                        ('processing', 'Processing'),
                        ('completed', 'Completed'),
                        ('failed', 'Failed')
                    ],
                    max_length=20
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pos.business')),
            ],
            options={
                'indexes': [
                    models.Index(fields=['business', 'operation_type', 'created_at'], name='pos_idempot_busines_idx'),
                    models.Index(fields=['expires_at'], name='pos_idempot_expires_idx'),
                ],
            },
        ),
    ]
