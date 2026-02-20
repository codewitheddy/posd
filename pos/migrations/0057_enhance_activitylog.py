# Generated migration for enhancing ActivityLog model

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0056_add_idempotency_key'),
    ]

    operations = [
        # Add business field for multi-tenant support
        migrations.AddField(
            model_name='activitylog',
            name='business',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=models.CASCADE,
                related_name='activity_logs',
                to='pos.business'
            ),
        ),
        
        # Add operation_type field
        migrations.AddField(
            model_name='activitylog',
            name='operation_type',
            field=models.CharField(max_length=50, db_index=True, default='unknown'),
            preserve_default=False,
        ),
        
        # Add entity_type field
        migrations.AddField(
            model_name='activitylog',
            name='entity_type',
            field=models.CharField(max_length=100, db_index=True, default=''),
        ),
        
        # Add entity_id field
        migrations.AddField(
            model_name='activitylog',
            name='entity_id',
            field=models.CharField(max_length=100, db_index=True, default=''),
        ),
        
        # Add status field
        migrations.AddField(
            model_name='activitylog',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('success', 'Success'),
                    ('failure', 'Failure'),
                    ('rollback', 'Rollback')
                ],
                default='success',
                db_index=True
            ),
        ),
        
        # Add correlation_id field
        migrations.AddField(
            model_name='activitylog',
            name='correlation_id',
            field=models.UUIDField(default=uuid.uuid4, db_index=True),
        ),
        
        # Add user_agent field
        migrations.AddField(
            model_name='activitylog',
            name='user_agent',
            field=models.TextField(blank=True, default=''),
        ),
        
        # Add request_data field
        migrations.AddField(
            model_name='activitylog',
            name='request_data',
            field=models.JSONField(null=True, blank=True),
        ),
        
        # Add response_data field
        migrations.AddField(
            model_name='activitylog',
            name='response_data',
            field=models.JSONField(null=True, blank=True),
        ),
        
        # Add error_details field
        migrations.AddField(
            model_name='activitylog',
            name='error_details',
            field=models.JSONField(null=True, blank=True),
        ),
        
        # Add execution_time_ms field
        migrations.AddField(
            model_name='activitylog',
            name='execution_time_ms',
            field=models.IntegerField(null=True, blank=True),
        ),
        
        # Add new indexes for efficient querying
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['business', 'timestamp'], name='pos_activitylog_bus_time_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['business', 'operation_type', 'timestamp'], name='pos_activitylog_bus_op_time_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['business', 'entity_type', 'entity_id'], name='pos_activitylog_bus_ent_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['business', 'user', 'timestamp'], name='pos_activitylog_bus_usr_time_idx'),
        ),
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['correlation_id'], name='pos_activitylog_corr_idx'),
        ),
    ]
