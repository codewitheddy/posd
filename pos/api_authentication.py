"""
DRF authentication backend for long-lived API keys.
Accepts: Authorization: Bearer <64-char-hex-token>
"""
import re

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import APIKey, POSTerminal


class APIKeyAuthentication(BaseAuthentication):
    """
    Authenticate requests using a Bearer API key token.
    Returns (user, api_key) on success so views can access both.
    """

    def authenticate(self, request):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return None  # Let other backends try

        token = auth[7:].strip()
        if not token:
            return None

        # Fail fast for malformed tokens.
        if not re.fullmatch(r'[0-9a-fA-F]{64}', token):
            return None  # Could be another token format (like terminal token)

        try:
            api_key = APIKey.objects.select_related('created_by', 'business').get(
                key=token, is_active=True
            )
        except APIKey.DoesNotExist:
            raise AuthenticationFailed('Invalid or revoked API key.')

        # Update last_used_at without triggering full model save overhead
        APIKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())
        api_key.last_used_at = timezone.now()

        return (api_key.created_by, api_key)

    def authenticate_header(self, request):
        return 'Bearer realm="Marid POS API"'


class POSTerminalAuthentication(BaseAuthentication):
    """
    Authenticate POS terminals using their long-lived device token.
    Accepts:
      - Header: 'X-Terminal-Token: <token>'
      - Header: 'Authorization: Terminal <token>'
      - Header: 'Authorization: Bearer <token>' (if matches a POSTerminal device_token)
    """

    def authenticate(self, request):
        token = request.headers.get('X-Terminal-Token') or request.META.get('HTTP_X_TERMINAL_TOKEN')
        
        if not token:
            auth = request.headers.get('Authorization', '') or request.META.get('HTTP_AUTHORIZATION', '')
            if auth.startswith('Terminal ') or auth.startswith('Device '):
                token = auth.split(' ', 1)[1].strip()
            elif auth.startswith('Bearer '):
                candidate = auth[7:].strip()
                # Check if it matches a POSTerminal token
                if POSTerminal.objects.filter(device_token=candidate).exists():
                    token = candidate

        if not token:
            return None  # Let other auth backends handle it

        try:
            terminal = POSTerminal.objects.select_related(
                'business', 'business__owner', 'branch'
            ).get(device_token=token)
        except POSTerminal.DoesNotExist:
            raise AuthenticationFailed('Invalid or unregistered POS terminal token.')

        if not terminal.is_active:
            raise AuthenticationFailed('This POS terminal has been deactivated.')

        if terminal.branch and not terminal.branch.is_active:
            raise AuthenticationFailed('The branch assigned to this terminal is inactive.')

        if not terminal.business.is_active:
            raise AuthenticationFailed('The business account is inactive.')

        # Update last_active_at timestamp efficiently
        now = timezone.now()
        POSTerminal.objects.filter(pk=terminal.pk).update(last_active_at=now)
        terminal.last_active_at = now

        # Attach helpers directly to request
        request.terminal = terminal
        request.branch = terminal.branch
        request.business = terminal.business

        user = terminal.business.owner or AnonymousUser()
        return (user, terminal)

    def authenticate_header(self, request):
        return 'Terminal realm="Marid POS Terminal Sync"'


# ==================== OpenAPI / DRF-Spectacular Extensions ====================
try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class APIKeyScheme(OpenApiAuthenticationExtension):
        target_class = 'pos.api_authentication.APIKeyAuthentication'
        name = 'apiKeyAuth'

        def get_security_definition(self, auto_schema):
            return {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'APIKey',
                'description': '64-character hex API key token. Header: Authorization: Bearer <token>',
            }

    class POSTerminalScheme(OpenApiAuthenticationExtension):
        target_class = 'pos.api_authentication.POSTerminalAuthentication'
        name = 'terminalTokenAuth'

        def get_security_definition(self, auto_schema):
            return {
                'type': 'apiKey',
                'in': 'header',
                'name': 'X-Terminal-Token',
                'description': 'POS Terminal device token. Header: X-Terminal-Token: <token>',
            }
except ImportError:
    pass


