"""
backup/signals.py — Auto-create TenantBackupSettings when a new Business is created.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='pos.Business')
def create_tenant_backup_settings(sender, instance, created, **kwargs):
    """Create default TenantBackupSettings for every new Business."""
    if not created:
        return
    from backup.models import TenantBackupSettings
    TenantBackupSettings.objects.get_or_create(
        tenant=instance,
        defaults={
            'backup_mode':    TenantBackupSettings.MODE_AUTOMATIC,
            'retention_days': 30,
            'storage_mode':   TenantBackupSettings.STORAGE_HYBRID,
        },
    )
