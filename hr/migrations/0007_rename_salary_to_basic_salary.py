from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hr', '0006_employee_other_allowances_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='employee',
            old_name='salary',
            new_name='basic_salary',
        ),
    ]
