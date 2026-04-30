from datetime import time

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0090_remove_product_product_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='late_grace_minutes',
            field=models.PositiveIntegerField(
                default=15,
                help_text='Grace period in minutes after start time before marking late',
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(180),
                ],
            ),
        ),
        migrations.AddField(
            model_name='businesssettings',
            name='workday_end_time',
            field=models.TimeField(
                default=time(17, 0),
                help_text='Official workday end time used to determine overtime',
            ),
        ),
        migrations.AddField(
            model_name='businesssettings',
            name='workday_start_time',
            field=models.TimeField(
                default=time(8, 0),
                help_text='Official workday start time used to determine lateness',
            ),
        ),
    ]
