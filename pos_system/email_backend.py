"""
Custom SMTP email backend that sends a valid FQDN in the EHLO/HELO greeting.

cPanel mail servers reject connections where the HELO name is a bare hostname
like 'localhost' or a Windows machine name (e.g. 'DESKTOP-XXXXX').
Django uses socket.getfqdn() by default, which returns whatever the OS reports.

This backend overrides local_hostname on the SMTP connection so it always
greets the server with the mail domain, satisfying RFC 2821 §4.1.1.1.

Set in settings.py / .env:
    EMAIL_BACKEND = 'pos_system.email_backend.CpanelEmailBackend'
    EMAIL_HELO_NAME = marid.co.ke   # optional override, defaults to EMAIL_HOST
"""

from django.core.mail.backends.smtp import EmailBackend
from django.conf import settings


class CpanelEmailBackend(EmailBackend):
    def open(self):
        """Open an SMTP connection, injecting a valid local_hostname."""
        if self.connection:
            return False

        # Use explicit override, fall back to the mail host (already a valid FQDN)
        helo_name = getattr(settings, 'EMAIL_HELO_NAME', None) or self.host

        connection_params = {
            'local_hostname': helo_name,
        }

        try:
            self.connection = self.connection_class(
                self.host, self.port, **connection_params
            )
            if self.use_tls:
                import ssl
                self.connection.ehlo()
                self.connection.starttls(
                    context=ssl.create_default_context() if not self.ssl_certfile else
                    ssl.create_default_context(cafile=self.ssl_certfile)
                )
                self.connection.ehlo()
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except Exception:
            if not self.fail_silently:
                raise
