"""
Data Migration: Seed Default Kenyan SME Chart of Accounts & Fiscal Periods
"""
from django.db import migrations


def seed_existing_companies(apps, schema_editor):
    Company = apps.get_model('core', 'Company')
    Account = apps.get_model('accounting', 'Account')
    FiscalYear = apps.get_model('accounting', 'FiscalYear')
    FiscalPeriod = apps.get_model('accounting', 'FiscalPeriod')

    from accounting.seeders import KENYA_SME_DEFAULT_ACCOUNTS
    from datetime import date
    from django.utils import timezone

    year = timezone.localdate().year

    month_names = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]

    for company in Company.objects.all():
        # 1. Seed Chart of Accounts
        for item in KENYA_SME_DEFAULT_ACCOUNTS:
            Account.objects.get_or_create(
                company=company,
                code=item['code'],
                defaults={
                    'name': item['name'],
                    'account_type': item['type'],
                    'category': item['cat'],
                    'normal_balance': item['norm'],
                    'currency': 'KES',
                    'is_system': item['is_sys'],
                    'system_tag': item['tag'],
                    'is_reconciliation': item['is_rec'],
                    'is_active': True,
                    'description': item['desc'],
                }
            )

        # 2. Seed Fiscal Year & Periods
        fy, _ = FiscalYear.objects.get_or_create(
            company=company,
            name=f"FY {year}",
            defaults={
                'start_date': date(year, 1, 1),
                'end_date': date(year, 12, 31),
                'is_closed': False,
            }
        )

        for month_idx in range(1, 13):
            p_start = date(year, month_idx, 1)
            if month_idx == 12:
                p_end = date(year, 12, 31)
            else:
                p_end = date(year, month_idx + 1, 1) - timezone.timedelta(days=1)

            FiscalPeriod.objects.get_or_create(
                company=company,
                fiscal_year=fy,
                period_number=month_idx,
                defaults={
                    'name': f"{month_names[month_idx - 1]} {year}",
                    'start_date': p_start,
                    'end_date': p_end,
                    'is_closed': False,
                    'is_adjustment_period': False,
                }
            )


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0001_initial'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_existing_companies, reverse_seed),
    ]
