"""
Company and Branch Scoping Engine
Provides reusable queryset and view scoping mixins for multi-tenancy and multi-branch data isolation.
"""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from core.models.organization import Company, Branch, CompanyMembership, BranchMembership


def get_current_company(request) -> Company:
    """
    Resolve the active Company from the request object.
    Falls back to user's first active company membership or default active company.
    """
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        company = Company.objects.filter(is_active=True).first()
        return company

    # Check request attribute attached by middleware
    if hasattr(request, 'company') and request.company:
        return request.company

    user = request.user
    if user.is_superuser:
        company = Company.objects.filter(is_active=True).first()
        if company:
            request.company = company
        return company

    # Check active company membership
    membership = CompanyMembership.objects.filter(
        user=user, is_active=True, company__is_active=True
    ).select_related('company').first()

    if membership:
        request.company = membership.company
        return membership.company

    # Fallback to any active company
    company = Company.objects.filter(is_active=True).first()
    if company:
        request.company = company
    return company



def get_current_branch(request) -> Branch:
    """
    Resolve the active Branch from session, user preferences, or HQ default.
    """
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return None

    if hasattr(request, 'branch') and request.branch:
        return request.branch

    company = get_current_company(request)
    if not company:
        return None

    # Check session override if session middleware is present
    session_branch_id = request.session.get('active_branch_id') if hasattr(request, 'session') else None
    if session_branch_id:
        branch = Branch.objects.filter(id=session_branch_id, company=company, is_active=True).first()
        if branch:
            request.branch = branch
            return branch

    # Check user's primary branch assignment
    bm = BranchMembership.objects.filter(
        user=request.user, branch__company=company, is_active=True
    ).select_related('branch').order_by('-is_primary').first()

    if bm:
        request.branch = bm.branch
        return bm.branch

    # Fallback to HQ branch
    hq = company.get_headquarters()
    request.branch = hq
    return hq


def get_user_branches(user, company):
    """Return all active branches a user has access to within a company."""
    if not user or not user.is_authenticated or not company:
        return Branch.objects.none()

    if user.is_superuser:
        return company.branches.filter(is_active=True)

    # Check if user is Company Owner / Admin
    membership = CompanyMembership.objects.filter(user=user, company=company, is_active=True).first()
    if membership and membership.is_admin_or_owner:
        return company.branches.filter(is_active=True)

    # Return specifically assigned branches
    return Branch.objects.filter(
        memberships__user=user,
        memberships__is_active=True,
        company=company,
        is_active=True,
    )


class CompanyBranchScopeMixin:
    """
    Reusable View Mixin for Django Class-Based Views.
    Automatically scopes querysets to the active company and user's permitted branches.
    """
    company_field = 'company'
    branch_field = 'branch'
    user_field = 'created_by'
    allow_company_wide = True  # If True, records with branch=NULL (HQ-wide) are visible

    def get_company(self):
        return get_current_company(self.request)

    def get_branch(self):
        return get_current_branch(self.request)

    def get_scoped_queryset(self, queryset=None):
        if queryset is None:
            queryset = super().get_queryset()

        company = self.get_company()
        if not company:
            return queryset.none()

        # Enforce Company isolation
        if self.company_field:
            filter_kwargs = {self.company_field: company}
            queryset = queryset.filter(**filter_kwargs)

        user = self.request.user
        if not user or not user.is_authenticated:
            return queryset.none()

        if user.is_superuser:
            return queryset

        # Check if user is Company Owner or Administrator
        membership = CompanyMembership.objects.filter(user=user, company=company, is_active=True).first()
        if membership and membership.is_admin_or_owner:
            # Full company visibility
            return queryset

        # Scope by User's Assigned Branches
        if self.branch_field:
            user_branch_ids = get_user_branches(user, company).values_list('id', flat=True)
            branch_q = Q(**{f"{self.branch_field}__in": user_branch_ids})
            if self.allow_company_wide:
                branch_q |= Q(**{f"{self.branch_field}__isnull": True})
            queryset = queryset.filter(branch_q)

        return queryset

    def get_queryset(self):
        """Override standard CBV get_queryset to apply scoping."""
        return self.get_scoped_queryset()

    def form_valid(self, form):
        """Auto-populate company and created_by fields on new model instances."""
        instance = form.instance
        company = self.get_company()

        if hasattr(instance, self.company_field) and not getattr(instance, self.company_field, None):
            setattr(instance, self.company_field, company)

        if hasattr(instance, 'created_by') and not getattr(instance, 'created_by', None):
            instance.created_by = self.request.user

        if hasattr(instance, 'updated_by'):
            instance.updated_by = self.request.user

        return super().form_valid(form)
