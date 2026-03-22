from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pos', '0069_add_saleitem_note'),
    ]

    operations = [
        # 1. Add business FK to ExpenseCategory (nullable first)
        migrations.AddField(
            model_name='expensecategory',
            name='business',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='expense_categories',
                to='pos.business',
            ),
        ),
        migrations.AddField(
            model_name='expensecategory',
            name='is_predefined',
            field=models.BooleanField(default=False),
        ),
        # Remove old unique constraint on name alone
        migrations.AlterUniqueTogether(
            name='expensecategory',
            unique_together={('business', 'name')},
        ),

        # 2. Enhance Expense model
        migrations.AddField(
            model_name='expense',
            name='business',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='expenses',
                to='pos.business',
            ),
        ),
        migrations.AddField(
            model_name='expense',
            name='attachment',
            field=models.FileField(blank=True, null=True, upload_to='expenses/attachments/%Y/%m/'),
        ),
        migrations.AddField(
            model_name='expense',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        # Replace payment_method FK with a simple char field
        migrations.AddField(
            model_name='expense',
            name='payment_method_str',
            field=models.CharField(
                max_length=20,
                choices=[('cash','Cash'),('bank','Bank Transfer'),('mpesa','M-Pesa'),('card','Card'),('other','Other')],
                default='cash',
            ),
        ),
        # Make expense_number non-unique globally (unique per business instead)
        migrations.AlterField(
            model_name='expense',
            name='expense_number',
            field=models.CharField(max_length=20, editable=False),
        ),
        migrations.AlterField(
            model_name='expense',
            name='recorded_by',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='recorded_expenses',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='expense',
            name='amount',
            field=models.DecimalField(
                max_digits=10, decimal_places=2,
                validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
            ),
        ),
        migrations.AlterModelOptions(
            name='expense',
            options={'ordering': ['-expense_date', '-created_at']},
        ),
    ]
