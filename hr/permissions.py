from rest_framework.permissions import BasePermission
from pos.models import BusinessMembership, Business


def _get_membership(request):
    """Resolve the caller's BusinessMembership from the request.
    Looks for business slug in URL kwargs or query params, with fallbacks."""
    if not request.user or not request.user.is_authenticated:
        return None

    slug = (
        (request.resolver_match.kwargs.get('slug') if request.resolver_match else None) or
        (request.query_params.get('slug') if hasattr(request, 'query_params') else None) or
        (request.data.get('slug') if isinstance(getattr(request, 'data', None), dict) else None)
    )
    if slug:
        try:
            business = Business.objects.get(slug=slug)
            return BusinessMembership.objects.get(
                user=request.user,
                business=business,
                is_active=True
            )
        except (Business.DoesNotExist, BusinessMembership.DoesNotExist):
            return None

    if hasattr(request, 'business_membership') and request.business_membership:
        return request.business_membership

    if hasattr(request, 'business') and request.business:
        m = BusinessMembership.objects.filter(
            user=request.user,
            business=request.business,
            is_active=True
        ).first()
        if m:
            return m

    if hasattr(request, 'session') and request.session.get('business_id'):
        membership = BusinessMembership.objects.filter(
            user=request.user,
            business_id=request.session.get('business_id'),
            is_active=True
        ).first()
        if membership:
            return membership

    return BusinessMembership.objects.filter(
        user=request.user,
        is_active=True
    ).first()


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
