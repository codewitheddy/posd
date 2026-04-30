from decimal import Decimal

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0091_businesssettings_working_hours'),
    ]

    operations = [
        migrations.AddField(
            model_name='businesssettings',
            name='overtime_rate_multiplier',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('1.50'),
                help_text='Overtime pay rate multiplier against hourly rate (e.g. 1.5 = time-and-a-half)',
                max_digits=4,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('1.00')),
                    django.core.validators.MaxValueValidator(Decimal('5.00')),
                ],
            ),
        ),
    ]
