# Generated migration to update expiry_alert_days default from 3 to 7 days

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0054_add_theme_colors'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='expiry_alert_days',
            field=models.IntegerField(default=7, help_text='Alert X days before expiry'),
        ),
        migrations.AlterField(
            model_name='businesssettings',
            name='default_expiry_alert_days',
            field=models.IntegerField(default=7),
        ),
        # Update existing products with default value of 3 to new default of 7
        migrations.RunSQL(
            sql="UPDATE pos_product SET expiry_alert_days = 7 WHERE expiry_alert_days = 3;",
            reverse_sql="UPDATE pos_product SET expiry_alert_days = 3 WHERE expiry_alert_days = 7;",
        ),
        # Update existing business settings with default value of 3 to new default of 7
        migrations.RunSQL(
            sql="UPDATE pos_businesssettings SET default_expiry_alert_days = 7 WHERE default_expiry_alert_days = 3;",
            reverse_sql="UPDATE pos_businesssettings SET default_expiry_alert_days = 3 WHERE default_expiry_alert_days = 7;",
        ),
    ]
