"""
Base Abstract Models and QuerySets for Platform Core
"""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that excludes soft-deleted records by default."""

    def delete(self):
        """Soft-delete all records in queryset."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Permanently delete all records in queryset."""
        return super().delete()

    def active(self):
        """Filter only active (non-deleted) records."""
        return self.filter(is_deleted=False)

    def deleted(self):
        """Filter only soft-deleted records."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager that excludes soft-deleted records by default."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)

    def all_with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db)

    def deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=True)


class TimeStampedModel(models.Model):
    """Abstract model adding auto-managed timestamps."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditedModel(models.Model):
    """Abstract model tracking user creation and modifications."""
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created_set",
        db_index=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_updated_set",
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Abstract model providing soft-delete capabilities with audit trail."""
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_deleted_set",
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, deleted_by=None):
        """Perform soft-delete."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if deleted_by:
            self.deleted_by = deleted_by
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])

    def hard_delete(self, using=None, keep_parents=False):
        """Perform permanent database deletion."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """Restore soft-deleted instance."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])


class CompanyScopedModel(models.Model):
    """
    Abstract model that enforces multi-company tenancy isolation.
    All business records must inherit or include this model.
    """
    company = models.ForeignKey(
        'core.Company',
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_company_set",
        db_index=True,
        help_text="Tenant company owning this entity",
    )

    class Meta:
        abstract = True


class BranchScopedModel(models.Model):
    """
    Abstract model for entities that can be scoped to a specific branch/outlet.
    If branch is NULL, the record is considered company-wide (HQ).
    """
    branch = models.ForeignKey(
        'core.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_branch_set",
        db_index=True,
        help_text="Branch/Outlet this entity belongs to (NULL for company-wide)",
    )

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Abstract model using UUID as primary key."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
