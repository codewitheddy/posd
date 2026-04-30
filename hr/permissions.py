from rest_framework.permissions import BasePermission
from pos.models import BusinessMembership, Business


def _get_membership(request):
    """Resolve the caller's BusinessMembership from the request.
    Looks for business slug in URL kwargs or query params."""
    slug = (
        request.resolver_match.kwargs.get('slug') or
        request.query_params.get('slug') or
        request.data.get('slug')
    )
    if not slug:
        return None
    try:
        business = Business.objects.get(slug=slug)
        return BusinessMembership.objects.get(
            user=request.user,
            business=business,
            is_active=True
        )
    except (Business.DoesNotExist, BusinessMembership.DoesNotExist):
        return None


class IsHRAdmin(BasePermission):
    """Allows access only to owner or admin roles."""
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        membership = _get_membership(request)
        if not membership:
            return False
        return membership.role in ('owner', 'admin')


class IsHRManagerOrAdmin(BasePermission):
    """Allows access only to owner or admin roles."""
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        membership = _get_membership(request)
        if not membership:
            return False
        return membership.role in ('owner', 'admin')


class IsOwnEmployeeOrAdmin(BasePermission):
    """Restrict HR module access to owner or admin roles only."""
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        membership = _get_membership(request)
        if not membership:
            return False
        return membership.role in ('owner', 'admin')

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        membership = _get_membership(request)
        if not membership:
            return False
        return membership.role in ('owner', 'admin')
