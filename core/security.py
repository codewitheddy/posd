"""
Security Utilities and Data Protection Helpers
Implements access logging, field masking, and login monitoring.
"""
from typing import List, Optional
from core.models.security import SensitiveDataAccessLog, LoginAuditLog
from core.models.organization import UserProfile
from core.scoping import get_current_company


def get_client_ip(request) -> str:
    """Safely extract client IP address from request."""
    if not request:
        return '127.0.0.1'
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


def log_sensitive_access(
    request,
    entity_type: str,
    entity_id: str,
    fields_accessed: List[str],
    action: str = 'view',
    reason: str = '',
) -> Optional[SensitiveDataAccessLog]:
    """
    Log an audit entry whenever sensitive PII or financial fields are accessed.
    Complies with Kenya Data Protection Act 2019 accountability principles.
    """
    if not request:
        return None

    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        user = None

    company = get_current_company(request)
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:500] if request else ''

    return SensitiveDataAccessLog.objects.create(
        company=company,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        fields_accessed=fields_accessed,
        reason=reason,
    )


def record_login_attempt(
    request,
    username: str,
    is_successful: bool,
    failure_reason: str = '',
    user=None,
) -> LoginAuditLog:
    """Record a login attempt and update user profile lockout counters."""
    ip_address = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:500] if request else ''

    log = LoginAuditLog.objects.create(
        username=username,
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        is_successful=is_successful,
        failure_reason=failure_reason,
    )

    if user and hasattr(user, 'core_profile'):
        profile = user.core_profile
        if is_successful:
            profile.reset_failed_attempts()
        else:
            profile.record_failed_attempt()

    return log


def mask_sensitive_value(value: str, visible_end_chars: int = 4) -> str:
    """
    Mask a sensitive string (e.g. National ID, KRA PIN, Bank Account).
    Example: 'A001234567Z' -> '*******567Z'
    """
    if not value:
        return ''
    s = str(value).strip()
    if len(s) <= visible_end_chars:
        return '*' * len(s)
    masked_part = '*' * (len(s) - visible_end_chars)
    visible_part = s[-visible_end_chars:]
    return f"{masked_part}{visible_part}"
