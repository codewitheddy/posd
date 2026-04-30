from django.apps import AppConfig


class RestoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'restore'
    verbose_name = 'Restore'

    def ready(self):
        from django.db.models.signals import post_migrate
        from restore.wal import check_wal_recovery
        post_migrate.connect(check_wal_recovery, sender=self)
