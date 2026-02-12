# Convert BusinessSettings from singleton to per-business model

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def migrate_settings_to_per_business(apps, schema_editor):
    """Migrate existing singleton settings to per-business settings"""
    Business = apps.get_model('pos', 'Business')
    BusinessSettings = apps.get_model('pos', 'BusinessSettings')
    
    # Get the old singleton settings if it exists
    try:
        old_settings = BusinessSettings.objects.get(pk=1)
        
        # Create settings for each business based on the old singleton
        for business in Business.objects.all():
            # Check if settings already exist for this business
            if not BusinessSettings.objects.filter(business=business).exists():
                BusinessSettings.objects.create(
                    business=business,
                    business_name=old_settings.business_name if hasattr(old_settings, 'business_name') else business.name,
                    business_address=old_settings.business_address if hasattr(old_settings, 'business_address') else '',
                    business_phone=old_settings.business_phone if hasattr(old_settings, 'business_phone') else '',
                    business_email=old_settings.business_email if hasattr(old_settings, 'business_email') else '',
                    vat_rate=old_settings.vat_rate if hasattr(old_settings, 'vat_rate') else 16,
                    vat_enabled=old_settings.vat_enabled if hasattr(old_settings, 'vat_enabled') else True,
                    currency_symbol=old_settings.currency_symbol if hasattr(old_settings, 'currency_symbol') else 'KES',
                    default_low_stock_threshold=old_settings.default_low_stock_threshold if hasattr(old_settings, 'default_low_stock_threshold') else 10,
                )
        
        # Delete the old singleton settings
        old_settings.delete()
        
    except BusinessSettings.DoesNotExist:
        # No existing settings, create default settings for each business
        for business in Business.objects.all():
            if not BusinessSettings.objects.filter(business=business).exists():
                BusinessSettings.objects.create(
                    business=business,
                    business_name=business.name,
                    business_address=business.address if hasattr(business, 'address') else '',
                    business_phone=business.phone if hasattr(business, 'phone') else '',
                    business_email=business.email if hasattr(business, 'email') else '',
                )


def reverse_migration(apps, schema_editor):
    """Reverse migration - not fully reversible"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0019_fix_supplierpayment_unique'),
    ]

    operations = [
        # Remove the old pk=1 constraint by dropping and recreating the table
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS pos_businesssettings_old;',
            reverse_sql='',
        ),
        migrations.RunSQL(
            sql='ALTER TABLE pos_businesssettings RENAME TO pos_businesssettings_old;',
            reverse_sql='',
        ),
        
        # Create new BusinessSettings table with business FK
        migrations.CreateModel(
            name='BusinessSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('business_name', models.CharField(blank=True, help_text='Override business name for receipts', max_length=200)),
                ('business_address', models.TextField(blank=True)),
                ('business_phone', models.CharField(blank=True, max_length=20)),
                ('business_email', models.EmailField(blank=True, max_length=254)),
                ('business_website', models.URLField(blank=True)),
                ('tax_id', models.CharField(blank=True, help_text='Tax/VAT registration number', max_length=50)),
                ('logo', models.ImageField(blank=True, help_text='Company logo (will be automatically optimized)', null=True, upload_to='business/logos/')),
                ('vat_rate', models.DecimalField(decimal_places=2, default=16, help_text='VAT/Tax rate in percentage', max_digits=5)),
                ('vat_enabled', models.BooleanField(default=True, help_text='Enable VAT calculation')),
                ('receipt_header', models.TextField(blank=True, help_text='Custom header text for receipts')),
                ('receipt_footer', models.TextField(blank=True, help_text='Custom footer text for receipts')),
                ('show_logo_on_receipt', models.BooleanField(default=False)),
                ('thermal_receipt_width', models.IntegerField(choices=[(58, '58mm'), (80, '80mm')], default=80, help_text='Thermal printer paper width')),
                ('thermal_font_size', models.CharField(choices=[('small', 'Small'), ('medium', 'Medium'), ('large', 'Large')], default='medium', help_text='Font size for thermal receipts', max_length=10)),
                ('thermal_print_logo', models.BooleanField(default=True, help_text='Print logo on thermal receipts')),
                ('thermal_print_barcode', models.BooleanField(default=True, help_text='Print barcode on thermal receipts')),
                ('thermal_auto_cut', models.BooleanField(default=True, help_text='Auto-cut paper after printing')),
                ('thermal_copies', models.IntegerField(default=1, help_text='Number of receipt copies to print')),
                ('thermal_show_tax_breakdown', models.BooleanField(default=True, help_text='Show VAT breakdown on receipt')),
                ('currency_symbol', models.CharField(default='KES', max_length=10)),
                ('currency_position', models.CharField(choices=[('before', 'Before Amount'), ('after', 'After Amount')], default='before', max_length=10)),
                ('default_low_stock_threshold', models.IntegerField(default=10)),
                ('enable_low_stock_alerts', models.BooleanField(default=True)),
                ('default_expiry_alert_days', models.IntegerField(default=3)),
                ('enable_expiry_alerts', models.BooleanField(default=True)),
                ('allow_negative_stock', models.BooleanField(default=False, help_text='Allow sales when stock is 0')),
                ('require_product_code', models.BooleanField(default=False, help_text='Make product code mandatory')),
                ('auto_generate_product_code', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='settings', to='pos.business')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
            options={
                'verbose_name': 'Business Settings',
                'verbose_name_plural': 'Business Settings',
            },
        ),
        
        # Migrate data from old table to new table
        migrations.RunPython(migrate_settings_to_per_business, reverse_migration),
        
        # Drop old table
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS pos_businesssettings_old;',
            reverse_sql='',
        ),
    ]
