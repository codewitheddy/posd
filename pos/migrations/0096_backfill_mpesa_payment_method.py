from django.db import migrations


def add_mpesa_to_existing_businesses(apps, schema_editor):
    Business = apps.get_model('pos', 'Business')
    PaymentMethod = apps.get_model('pos', 'PaymentMethod')

    for business in Business.objects.all():
        # Skip if any variant of MPESA already exists (case-insensitive)
        if PaymentMethod.objects.filter(business=business, code__iexact='MPESA').exists():
            continue
        PaymentMethod.objects.create(
            business=business,
            name='M-Pesa',
            code='MPESA',
            is_active=True,
            requires_reference=True,
            icon='bi-phone',
        )


def remove_mpesa_backfill(apps, schema_editor):
    # Reverse: remove only the ones we added (those with no shortcode configured)
    # Safe to leave them in place — just a no-op reverse
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0095_mpesa_phone_field'),
    ]

    operations = [
        migrations.RunPython(
            add_mpesa_to_existing_businesses,
            remove_mpesa_backfill,
        ),
    ]
