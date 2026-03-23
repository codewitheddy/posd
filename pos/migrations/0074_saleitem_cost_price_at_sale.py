from django.db import migrations, models


def backfill_cost_price_at_sale(apps, schema_editor):
    """Backfill existing SaleItems with current product cost_price (best effort for historical data)."""
    SaleItem = apps.get_model('pos', 'SaleItem')
    # Bulk update: set cost_price_at_sale = product.cost_price for all existing records
    items = SaleItem.objects.select_related('product').filter(cost_price_at_sale__isnull=True)
    to_update = []
    for item in items:
        if item.product and item.product.cost_price:
            item.cost_price_at_sale = item.product.cost_price
            to_update.append(item)
    if to_update:
        SaleItem.objects.bulk_update(to_update, ['cost_price_at_sale'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0073_fix_expensecategory_name_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='saleitem',
            name='cost_price_at_sale',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Cost price snapshotted at time of sale for accurate COGS reporting',
                max_digits=10,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_cost_price_at_sale, migrations.RunPython.noop),
    ]
