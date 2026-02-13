# Fix SupplierPayment records missing business_id before making field required

from django.db import migrations


def fix_supplierpayment_business(apps, schema_editor):
    """Set business_id from supplier for SupplierPayment records missing it"""
    SupplierPayment = apps.get_model('pos', 'SupplierPayment')
    
    # Get all payments without business
    payments_without_business = SupplierPayment.objects.filter(business__isnull=True)
    
    fixed_count = 0
    for payment in payments_without_business:
        if payment.supplier and payment.supplier.business:
            payment.business = payment.supplier.business
            payment.save()
            fixed_count += 1
    
    print(f"Fixed {fixed_count} SupplierPayment records")


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0023_remove_unused_business_fields'),
    ]

    operations = [
        migrations.RunPython(fix_supplierpayment_business, migrations.RunPython.noop),
    ]
