# Generated migration for Cash Float Management

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0049_add_business_defaults'),
    ]

    operations = [
        migrations.CreateModel(
            name='CashFloat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('float_number', models.CharField(max_length=50, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('float_type', models.CharField(
                    choices=[('opening', 'Opening Float'), ('additional', 'Additional Float')],
                    default='opening',
                    max_length=20
                )),
                ('status', models.CharField(
                    choices=[('active', 'Active'), ('returned', 'Returned'), ('reconciled', 'Reconciled')],
                    default='active',
                    max_length=20
                )),
                ('given_at', models.DateTimeField(auto_now_add=True)),
                ('returned_at', models.DateTimeField(blank=True, null=True)),
                ('returned_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('variance', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, help_text='Difference between expected and returned amount')),
                ('notes', models.TextField(blank=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cash_floats', to='pos.business')),
                ('cashier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cash_floats', to=settings.AUTH_USER_MODEL)),
                ('given_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='floats_given', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-given_at'],
                'indexes': [
                    models.Index(fields=['business', 'cashier', '-given_at'], name='pos_cashflo_busines_idx'),
                    models.Index(fields=['business', 'status'], name='pos_cashflo_busines_status_idx'),
                ],
            },
        ),
    ]
