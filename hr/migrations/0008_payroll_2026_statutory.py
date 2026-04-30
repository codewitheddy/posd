"""
Migration: 2026 Kenyan statutory compliance updates.
- Rename Payroll.nhif → Payroll.shif  (NHIF replaced by SHIF at 2.75% of gross)
- Add Payroll.housing_levy             (Affordable Housing Levy at 1.5% of gross)
- Update NSSF limits (Feb 2026)
"""
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0007_rename_salary_to_basic_salary'),
    ]

    operations = [
        migrations.RenameField(
            model_name='payroll',
            old_name='nhif',
            new_name='shif',
        ),
        migrations.AlterField(
            model_name='payroll',
            name='shif',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=12,
                verbose_name='SHIF (Social Health Insurance Fund)',
            ),
        ),
        migrations.AddField(
            model_name='payroll',
            name='housing_levy',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=12,
                verbose_name='Affordable Housing Levy (1.5%)',
            ),
        ),
    ]
