"""
Migration to add BackupAuditLog model for backup audit trail
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0087_heldorder'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='BackupAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation', models.CharField(choices=[('backup_database', 'Database Backup'), ('backup_media', 'Media Backup'), ('backup_business', 'Business Backup'), ('restore_database', 'Database Restore'), ('restore_media', 'Media Restore'), ('restore_business', 'Business Restore'), ('verify_backup', 'Backup Verification'), ('delete_backup', 'Backup Deletion')], max_length=30)),
                ('status', models.CharField(choices=[('success', 'Success'), ('failed', 'Failed'), ('warning', 'Warning'), ('in_progress', 'In Progress')], default='in_progress', max_length=20)),
                ('backup_file', models.CharField(help_text='Path or name of backup file', max_length=255)),
                ('backup_size_mb', models.DecimalField(blank=True, decimal_places=2, help_text='Size of backup in MB', max_digits=12, null=True)),
                ('backup_checksum', models.CharField(blank=True, help_text='SHA-256 checksum', max_length=64)),
                ('is_encrypted', models.BooleanField(default=True, help_text='Whether backup was encrypted')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('duration_seconds', models.IntegerField(blank=True, null=True)),
                ('details', models.JSONField(blank=True, default=dict, help_text='Additional operation details')),
                ('error_message', models.TextField(blank=True, help_text='If failed, the error details')),
                ('business', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='backup_audit_logs', to='pos.business')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='backup_operations', to='auth.user')),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
        migrations.AddIndex(
            model_name='backupauditlog',
            index=models.Index(fields=['user', '-started_at'], name='pos_backupa_user_id_f4c3a1_idx'),
        ),
        migrations.AddIndex(
            model_name='backupauditlog',
            index=models.Index(fields=['business', '-started_at'], name='pos_backupa_business_f4c3a1_idx'),
        ),
        migrations.AddIndex(
            model_name='backupauditlog',
            index=models.Index(fields=['status'], name='pos_backupa_status_f4c3a1_idx'),
        ),
    ]
