from decimal import Decimal
import django.core.validators
from django.db import migrations, models


def backfill_membership_permissions(apps, schema_editor):
    from decimal import Decimal
    BusinessMembership = apps.get_model('pos', 'BusinessMembership')

    DEFAULT_PERMISSIONS = {
        'owner':         ['can_refund_sale', 'can_void_sale', 'can_edit_price', 'can_view_cost_price',
                          'can_apply_discount', 'can_exceed_max_discount', 'can_manage_users',
                          'can_view_reports', 'can_manage_stock'],
        'admin':         ['can_refund_sale', 'can_void_sale', 'can_edit_price', 'can_view_cost_price',
                          'can_apply_discount', 'can_exceed_max_discount', 'can_manage_users',
                          'can_view_reports', 'can_manage_stock'],
        'manager':       ['can_refund_sale', 'can_void_sale', 'can_edit_price', 'can_view_cost_price',
                          'can_apply_discount', 'can_exceed_max_discount', 'can_view_reports', 'can_manage_stock'],
        'stock_manager': ['can_manage_stock', 'can_view_reports', 'can_view_cost_price'],
        'cashier':       ['can_apply_discount', 'can_refund_sale'],
        'sales':         ['can_apply_discount'],
        'viewer':        ['can_view_reports'],
    }
    DEFAULT_MAX_DISCOUNT = {
        'owner': Decimal('100.00'), 'admin': Decimal('100.00'),
        'manager': Decimal('50.00'),
        'cashier': Decimal('20.00'), 'sales': Decimal('20.00'),
        'stock_manager': Decimal('0.00'), 'viewer': Decimal('0.00'),
    }

    for membership in BusinessMembership.objects.all():
        membership.permissions = DEFAULT_PERMISSIONS.get(membership.role, [])
        membership.max_discount_pct = DEFAULT_MAX_DISCOUNT.get(membership.role, Decimal('0.00'))
        membership.save(update_fields=['permissions', 'max_discount_pct'])


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0084_merge_20260405_0134'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='pin_hash',
            field=models.CharField(blank=True, max_length=128, null=True, help_text='Hashed PIN for POS quick login'),
        ),
        migrations.AddField(
            model_name='businessmembership',
            name='permissions',
            field=models.JSONField(blank=True, default=list, help_text='Granular permission codes for this member'),
        ),
        migrations.AddField(
            model_name='businessmembership',
            name='max_discount_pct',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0.00'), max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal('0')),
                    django.core.validators.MaxValueValidator(Decimal('100')),
                ],
                help_text='Maximum discount percentage this member can apply at POS',
            ),
        ),
        migrations.RunPython(backfill_membership_permissions, reverse_code=migrations.RunPython.noop),
    ]
