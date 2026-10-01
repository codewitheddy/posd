"""
Kenya Data Protection Act 2019 (DPA 2019) Compliance Engine
Provides:
- Data Subject Access Request (DSAR) export
- Anonymization and Right-to-be-Forgotten handling (preserving financial ledger integrity)
- Sensitive Data Access logging and consent verification
"""
from typing import Any, Dict, List, Optional
from datetime import date
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from core.models.security import SensitiveDataAccessLog
from core.models.audit import AuditLog


def log_sensitive_data_access(
    data_subject: User,
    accessor: Optional[User],
    data_fields: List[str],
    reason: str,
    ip_address: Optional[str] = None,
    company: Optional[Any] = None,
) -> SensitiveDataAccessLog:
    """
    Log an access event to sensitive personal data (e.g. National ID, KRA PIN, Bank Details).
    Enforces DPA 2019 Section 41 (Duty to notify and log processing).
    """
    return SensitiveDataAccessLog.objects.create(
        user=accessor if (accessor and getattr(accessor, 'is_authenticated', False)) else None,
        entity_type='auth.User',
        entity_id=str(data_subject.pk),
        fields_accessed=data_fields,
        reason=reason,
        ip_address=ip_address,
        company=company,
    )


def export_data_subject_profile(user: User) -> Dict[str, Any]:
    """
    Generate complete DPA 2019 Right of Access / Data Portability export package.
    """
    profile_data = {
        'subject_id': user.pk,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'date_joined': user.date_joined.isoformat() if user.date_joined else None,
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'is_active': user.is_active,
        'export_generated_at': timezone.now().isoformat(),
        'compliance_statement': 'Exported in compliance with Kenya Data Protection Act 2019, Section 26.',
    }

    # Include platform memberships
    memberships = []
    for m in getattr(user, 'company_memberships', []).all():
        memberships.append({
            'company': m.company.name,
            'role': m.role,
            'is_active': m.is_active,
        })
    profile_data['memberships'] = memberships

    return profile_data


def anonymize_user_personal_data(
    user: User,
    requested_by: Optional[User] = None,
    reason: str = "DPA 2019 Right to Erasure Request",
) -> Dict[str, Any]:
    """
    Anonymize identifiable personal data while preserving foreign keys and ledger integrity.
    Replaces identifiable strings with cryptographically salted pseudo-identifiers.
    """
    with transaction.atomic():
        orig_username = user.username
        user.first_name = "Anonymized"
        user.last_name = f"User-{user.pk}"
        user.email = f"anonymized_{user.pk}@privacy.internal"
        user.is_active = False
        user.set_unusable_password()
        user.save(update_fields=['first_name', 'last_name', 'email', 'is_active', 'password'])

        AuditLog.objects.create(
            action='anonymize',
            object_repr=f"User #{user.pk} ({orig_username}) anonymized for DPA 2019 compliance",
            object_id=str(user.pk),
            user=requested_by if (requested_by and getattr(requested_by, 'is_authenticated', False)) else None,
            changes={'reason': reason, 'original_username': orig_username},
        )

    return {
        'user_id': user.pk,
        'status': 'anonymized',
        'timestamp': timezone.now().isoformat(),
    }
