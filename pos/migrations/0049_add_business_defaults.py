"""
Migration to add default payment method, unit, and category to existing businesses
"""
from django.db import migrations


def create_defaults_for_existing_businesses(apps, schema_editor):
    """Create default data for all existing businesses"""
    Business = apps.get_model('pos', 'Business')
    PaymentMethod = apps.get_model('pos', 'PaymentMethod')
    UnitOfMeasurement = apps.get_model('pos', 'UnitOfMeasurement')
    Category = apps.get_model('pos', 'Category')
    
    for business in Business.objects.all():
        # Create default payment method: CASH
        PaymentMethod.objects.get_or_create(
            business=business,
            name='CASH',
            defaults={
                'is_active': True,
                'requires_reference': False,
            }
        )
        
        # Create default unit: Pieces
        UnitOfMeasurement.objects.get_or_create(
            business=business,
            name='Pieces',
            defaults={
                'abbreviation': 'pcs',
                'is_active': True,
            }
        )
        
        # Create default category: GENERAL
        Category.objects.get_or_create(
            business=business,
            name='GENERAL',
        )


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0048_add_loyalty_settings'),
    ]

    operations = [
        migrations.RunPython(
            create_defaults_for_existing_businesses,
            reverse_code=migrations.RunPython.noop
        ),
    ]
