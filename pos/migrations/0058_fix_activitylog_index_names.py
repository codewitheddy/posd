# Generated migration to fix ActivityLog index names (must be <=30 chars)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0057_enhance_activitylog'),
    ]

    operations = [
        # Remove old indexes with long names
        migrations.RemoveIndex(
            model_name='activitylog',
            name='pos_activitylog_bus_time_idx',
        ),
        migrations.RemoveIndex(
            model_name='activitylog',
            name='pos_activitylog_bus_op_time_idx',
        ),
        migrations.RemoveIndex(
            model_name='activitylog',
            name='pos_activitylog_bus_usr_time_idx',
        ),
        
        # Add new indexes with shorter names
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['business', 'timestamp'], name='pos_actlog_bus_time_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['business', 'operation_type', 'timestamp'], name='pos_actlog_bus_op_tm_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['business', 'user', 'timestamp'], name='pos_actlog_bus_usr_tm_idx'),
        ),
    ]
