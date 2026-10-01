"""
Attachments Storage & Validation Service
"""
import os
from typing import Optional
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from core.models.attachments import Attachment
from core.models.organization import Company

ALLOWED_EXTENSIONS = {
    'pdf', 'png', 'jpg', 'jpeg', 'gif', 'csv', 'xlsx', 'xls', 'docx', 'doc', 'txt'
}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15MB


def validate_attachment(file_obj):
    """Validate uploaded file size and extension."""
    if file_obj.size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File size exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f}MB.")

    ext = os.path.splitext(file_obj.name)[1].lower().lstrip('.')
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"File type '.{ext}' is not permitted. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}")


def attach_file(
    instance,
    file_obj,
    user=None,
    company: Optional[Company] = None,
    description: str = '',
    is_public: bool = False,
) -> Attachment:
    """
    Attach an uploaded file to any platform model instance.
    """
    validate_attachment(file_obj)

    content_type = ContentType.objects.get_for_model(instance)
    object_id = str(instance.pk)

    if not company and hasattr(instance, 'company'):
        company = getattr(instance, 'company', None)
    if not company:
        raise ValueError("Attachment requires a valid Company context.")

    return Attachment.objects.create(
        company=company,
        content_type=content_type,
        object_id=object_id,
        file=file_obj,
        original_filename=file_obj.name,
        file_size_bytes=file_obj.size,
        mime_type=getattr(file_obj, 'content_type', 'application/octet-stream'),
        uploaded_by=user,
        description=description,
        is_public=is_public,
    )


def get_attachments_for_object(instance) -> QuerySet:
    """Retrieve all attachments belonging to a model instance."""
    content_type = ContentType.objects.get_for_model(instance)
    return Attachment.objects.filter(content_type=content_type, object_id=str(instance.pk))
