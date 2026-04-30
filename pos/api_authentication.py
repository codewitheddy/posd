"""
DRF authentication backend for long-lived API keys.
Accepts: Authorization: Bearer <64-char-hex-token>
"""
import re

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import APIKey


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
            raise AuthenticationFailed('Invalid or revoked API key.')

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
