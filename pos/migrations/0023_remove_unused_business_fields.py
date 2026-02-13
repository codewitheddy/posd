# Generated migration to remove business fields from models that don't need them

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0022_fix_business_fields'),
    ]

    operations = [
        # Remove business field from models that don't have it in their model definition
        migrations.RemoveField(
            model_name='expense',
            name='business',
        ),
        migrations.RemoveField(
            model_name='expensecategory',
            name='business',
        ),
        migrations.RemoveField(
            model_name='loyaltyredemption',
            name='business',
        ),
        migrations.RemoveField(
            model_name='loyaltyreward',
            name='business',
        ),
        migrations.RemoveField(
            model_name='loyaltytransaction',
            name='business',
        ),
        migrations.RemoveField(
            model_name='paymentallocation',
            name='business',
        ),
        migrations.RemoveField(
            model_name='promotion',
            name='business',
        ),
        migrations.RemoveField(
            model_name='salereturn',
            name='business',
        ),
        migrations.RemoveField(
            model_name='salereturnitem',
            name='business',
        ),
        migrations.RemoveField(
            model_name='shift',
            name='business',
        ),
    ]
