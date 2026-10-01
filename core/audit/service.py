"""
Unified Audit Logging Service
Captures immutable audit trail records with before/after field diffs.
"""
from typing import Any, Dict, Optional
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
import json
from core.models.audit import AuditLog
from core.security import get_client_ip
from core.scoping import get_current_company


def serialize_field_value(val: Any) -> Any:
    """Safely convert model field values to JSON-serializable primitives."""
    if val is None:
        return None
    if hasattr(val, 'pk'):
        return val.pk
    try:
        json.dumps(val, cls=DjangoJSONEncoder)
        return val
    except Exception:
        return str(val)


def log_audit(
    action: str,
    instance=None,
    user=None,
    changes: Optional[Dict[str, Any]] = None,
    request=None,
    company=None,
    metadata: Optional[Dict[str, Any]] = None,
    object_repr: str = '',
) -> AuditLog:
    """
    Create an append-only AuditLog record.
    """
    content_type = None
    object_id = ''

    if instance is not None:
        content_type = ContentType.objects.get_for_model(instance)
        object_id = str(instance.pk) if instance.pk else ''
        if not object_repr:
            object_repr = str(instance)[:255]

        if not company and hasattr(instance, 'company'):
            company = getattr(instance, 'company', None)

    if request:
        if not user and hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user
        if not company:
            company = get_current_company(request)
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
    else:
        ip_address = None
        user_agent = ''

    return AuditLog.objects.create(
        company=company,
        user=user,
        action=action,
        content_type=content_type,
        object_id=object_id,
        object_repr=object_repr,
        changes=changes or {},
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata or {},
    )


class AuditedModelMixin:
    """
    Model mixin that tracks field changes and automatically records audit logs on save.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_state = self._capture_state()

    def _capture_state(self) -> Dict[str, Any]:
        """Capture current field values for diffing."""
        state = {}
        if not self.pk:
            return state
        for field in self._meta.fields:
            if field.name in ('updated_at', 'created_at'):
                continue
            val = getattr(self, field.attname, None)
            state[field.name] = serialize_field_value(val)
        return state

    def save(self, *args, **kwargs):
        is_new = self._state.adding or not self.pk
        old_state = self._initial_state
        super().save(*args, **kwargs)

        new_state = self._capture_state()
        changes = {}

        if is_new:
            action = AuditLog.ACTION_CREATE
            changes = {k: {'old': None, 'new': v} for k, v in new_state.items()}
        else:
            action = AuditLog.ACTION_UPDATE
            for k, new_val in new_state.items():
                old_val = old_state.get(k)
                if old_val != new_val:
                    changes[k] = {'old': old_val, 'new': new_val}

        if changes or is_new:
            log_audit(
                action=action,
                instance=self,
                changes=changes,
                user=getattr(self, 'updated_by', None) or getattr(self, 'created_by', None),
            )

        self._initial_state = new_state
