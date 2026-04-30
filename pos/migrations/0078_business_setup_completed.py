from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0077_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='business',
            name='setup_completed',
            field=models.BooleanField(default=False, help_text='Whether initial business setup has been completed'),
        ),
    ]
