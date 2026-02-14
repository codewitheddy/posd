# Generated migration for license management

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0031_add_unit_of_measurement'),
    ]

    operations = [
        migrations.AddField(
            model_name='business',
            name='license_expires_at',
            field=models.DateTimeField(null=True, blank=True, help_text='License expiration date'),
        ),
        migrations.AddField(
            model_name='business',
            name='license_status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('active', 'Active'),
                    ('expired', 'Expired'),
                    ('suspended', 'Suspended'),
                ],
                default='active',
                help_text='Current license status'
            ),
        ),
    ]
