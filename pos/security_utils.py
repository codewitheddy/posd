"""
Security utilities for high-privilege operations in V2POS.
Enforces admin password confirmation and mandatory audit reasons for all bulk actions and deletions.
"""
import json
from .models import BusinessMembership, ActivityLog


def verify_admin_password_and_reason(
    request,
    user=None,
    password_field='admin_password',
    reason_field='reason',
    min_reason_length=3,
    action_name='action'
):
    """
    Validate that the requesting user (or business owner/admin) supplied their valid login password
    and a non-empty audit reason for committing sensitive operations (deletions, bulk updates, etc.).

    Returns:
        (is_valid: bool, error_message: str or None, clean_reason: str)
    """
    acting_user = user or getattr(request, 'user', None)
    if not acting_user or not acting_user.is_authenticated:
        return False, "Authentication required to perform this action.", ""

    # Extract password and reason from POST or JSON payload
    raw_password = ""
    raw_reason = ""

    if getattr(request, 'content_type', '') == 'application/json' and getattr(request, 'body', None):
        try:
            body_data = json.loads(request.body.decode('utf-8'))
            raw_password = str(body_data.get(password_field, '') or body_data.get('password', '')).strip()
            raw_reason = str(body_data.get(reason_field, '') or body_data.get('deletion_reason', '') or body_data.get('action_reason', '')).strip()
        except Exception:
            pass

    if not raw_password:
        raw_password = str(request.POST.get(password_field, '') or request.POST.get('password', '')).strip()
    if not raw_reason:
        raw_reason = str(request.POST.get(reason_field, '') or request.POST.get('deletion_reason', '') or request.POST.get('action_reason', '')).strip()

    # 1. Validate Password Presence & Correctness
    if not raw_password:
        return False, "Admin password is required to authorize this action.", ""

    password_ok = acting_user.check_password(raw_password)

    # If current user's password failed, check if business owner password was provided
    if not password_ok and hasattr(request, 'business') and request.business:
        business = request.business
        if getattr(business, 'owner', None) and business.owner.check_password(raw_password):
            password_ok = True
        else:
            # Check other owner members
            owner_memberships = BusinessMembership.objects.filter(
                business=business,
                role__in=['owner', 'admin']
            ).select_related('user')
            for bm in owner_memberships:
                if bm.user and bm.user.check_password(raw_password):
                    password_ok = True
                    break

    if not password_ok:
        return False, "Invalid admin password. Authorization failed.", ""

    # 2. Validate Reason Presence & Length
    if not raw_reason or len(raw_reason) < min_reason_length:
        return False, f"A valid reason (at least {min_reason_length} characters) is required to commit this {action_name}.", ""

    return True, None, raw_reason


def is_user_supervisor(user, business=None):
    """
    Check if a given user has manager, admin, or owner privileges for the given business.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if business:
        if getattr(business, 'owner', None) and user.id == business.owner_id:
            return True
        membership = BusinessMembership.objects.filter(
            business=business,
            user=user,
            is_active=True,
            role__in=['owner', 'admin', 'manager', 'chief_cashier']
        ).first()
        return bool(membership)
    return False


def verify_supervisor_credentials(request, credential):
    """
    Verify whether the provided credential (PIN or Password) belongs to an authorized
    supervisor/manager/owner in the current store/business.

    Returns:
        (is_valid: bool, supervisor_user: User or None, error_message: str or None)
    """
    raw = str(credential or '').strip()
    if not raw:
        return False, None, "Admin password or Supervisor PIN is required."

    business = getattr(request, 'business', None)
    if not business:
        return False, None, "No active business context found."

    from .models import UserProfile

    # 1. Try checking as a Supervisor PIN (4-6 digits)
    if raw.isdigit() and 4 <= len(raw) <= 6:
        profile = UserProfile.find_by_pin(raw, business=business)
        if profile and profile.user and profile.user.is_active:
            if is_user_supervisor(profile.user, business):
                return True, profile.user, None
            else:
                return False, None, "The entered PIN belongs to a cashier, not an authorized supervisor."

    # 2. Try checking as a Password against Owner, Admins, and Managers
    # Check business owner
    if business.owner and business.owner.is_active and business.owner.check_password(raw):
        return True, business.owner, None

    # Check superuser if acting user is superuser
    if request.user.is_authenticated and request.user.is_superuser and request.user.check_password(raw):
        return True, request.user, None

    # Check managers and admins in the business
    supervisor_memberships = BusinessMembership.objects.filter(
        business=business,
        is_active=True,
        role__in=['owner', 'admin', 'manager', 'chief_cashier']
    ).select_related('user')

    for bm in supervisor_memberships:
        if bm.user and bm.user.is_active and bm.user.check_password(raw):
            return True, bm.user, None

    return False, None, "Invalid supervisor password or PIN. Authorization denied."

