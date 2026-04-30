from django.apps import AppConfig


class PosConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pos'

    def ready(self):
        import pos.signals  # noqa: F401 — registers webhook signals

        # Clear all sessions on server startup so restarting the server
        # forces all users to log in again (security for shared POS terminals)
        try:
            from django.contrib.sessions.models import Session
            from django.utils import timezone
            # Only delete expired sessions on startup — don't force-logout everyone
            # (superuser needs to stay logged in to manage the system)
            Session.objects.filter(expire_date__lt=timezone.now()).delete()
        except Exception:
            pass  # DB might not be ready yet (e.g. first migration)
