from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Remove the column-level unique=True from ExpenseCategory.name.
    The correct constraint is unique_together = [('business', 'name')]
    which was set in 0070_financial_suite.
    """

    dependencies = [
        ('pos', '0072_crm_enhancements'),
    ]

    operations = [
        migrations.AlterField(
            model_name='expensecategory',
            name='name',
            field=models.CharField(max_length=100),
        ),
    ]
