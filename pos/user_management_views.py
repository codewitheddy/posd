"""
User Management Views
Complete user and role management for businesses
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from .models import Branch, Business, BusinessMembership, UserProfile, ActivityLog, PERMISSION_CODES, DEFAULT_PERMISSIONS
from .decorators import business_required


# Manager required decorator (inline)
def manager_required(view_func):
    """Decorator to check if user is a manager, owner, or superuser"""
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        if hasattr(request, 'business') and request.business:
            membership = request.business.memberships.filter(
                user=request.user, 
                is_active=True
            ).first()
            
            if membership and membership.role in ['owner', 'admin', 'manager']:
                return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You need manager permissions to access this page.')
        return redirect('dashboard', slug=request.business.slug if hasattr(request, 'business') else None)
    
    return wrapper


ROLE_CHOICES = [
    ('owner', 'Owner'),
    ('admin', 'Administrator'),
    ('manager', 'Manager'),
    ('stock_manager', 'Stock Manager'),
    ('cashier', 'Cashier'),
    ('sales', 'Sales Associate'),
    ('viewer', 'Viewer'),
]


AUTO_REGISTER_EMPLOYEE_ROLES = {'admin', 'manager', 'stock_manager', 'cashier', 'sales'}


def _get_auto_employee_branch(business, branch_id=None):
    branches = business.branches.filter(is_active=True).order_by('-is_default', 'name', 'pk')
    if branch_id:
        return branches.filter(pk=branch_id).first()
    return branches.filter(is_default=True).first() or branches.first()


def _sync_employee_profile(user, business, role, branch_id=None, profile=None):
    if role not in AUTO_REGISTER_EMPLOYEE_ROLES:
        return None, False, None

    from hr.models import Employee

    employee = Employee.objects.filter(user_account=user, business=business).select_related('branch').first()
    if employee:
        if profile and not profile.employee_id and employee.staff_code:
            profile.employee_id = employee.staff_code
            profile.save(update_fields=['employee_id'])
        return employee, False, None

    branch = _get_auto_employee_branch(business, branch_id)
    if branch is None:
        return None, False, 'No active branch is available for HR auto-registration.'

    employee = Employee.objects.create(
        user_account=user,
        first_name=user.first_name,
        last_name=user.last_name,
        business=business,
        branch=branch,
        job_title=dict(ROLE_CHOICES).get(role, role.replace('_', ' ').title()),
        hire_date=timezone.localdate(),
        status='active',
    )

    if profile and not profile.employee_id and employee.staff_code:
        profile.employee_id = employee.staff_code
        profile.save(update_fields=['employee_id'])

    return employee, True, None


@business_required
@manager_required
def user_list_view(request, slug=None):
    """List all users in this business"""
    memberships = request.business.memberships.filter(is_active=True).select_related('user')
    
    # Add statistics for each membership
    for membership in memberships:
        from .models import Sale
        from django.db.models import Sum
        
        membership.total_sales = Sale.objects.filter(
            cashier=membership.user, 
            business=request.business
        ).count()
        
        membership.total_revenue = Sale.objects.filter(
            cashier=membership.user, 
            business=request.business
        ).aggregate(total=Sum('total'))['total'] or 0
    
    context = {
        'memberships': memberships,
    }
    return render(request, 'pos/user_management_list.html', context)


@business_required
@manager_required
def user_create_view(request, slug=None):
    """Create a new user and add to business"""
    branches = request.business.branches.filter(is_active=True).order_by('-is_default', 'name', 'pk')
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        role = request.POST.get('role')
        phone = request.POST.get('phone', '')
        employee_id = request.POST.get('employee_id', '')
        branch_id = request.POST.get('branch_id', '').strip()
        
        # Validation
        if not username or not password:
            messages.error(request, 'Username and password are required!')
            return redirect('user_management_create', slug=request.business.slug)
        
        if password != password_confirm:
            messages.error(request, 'Passwords do not match!')
            return redirect('user_management_create', slug=request.business.slug)
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists!')
            return redirect('user_management_create', slug=request.business.slug)
        
        if not role:
            messages.error(request, 'Please select a role!')
            return redirect('user_management_create', slug=request.business.slug)
        
        try:
            with transaction.atomic():
                # Create user
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=True
                )
                
                # Create or update profile
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.phone = phone
                profile.employee_id = employee_id if employee_id else None
                profile.save()
                
                # Create business membership
                BusinessMembership.objects.create(
                    user=user,
                    business=request.business,
                    role=role,
                    is_active=True,
                    joined_at=timezone.now()
                )

                employee, employee_created, employee_warning = _sync_employee_profile(
                    user=user,
                    business=request.business,
                    role=role,
                    branch_id=branch_id or None,
                    profile=profile,
                )
                
                # Log activity
                ActivityLog.log_activity(
                    user=request.user,
                    action_type='create',
                    model_name='User',
                    object_id=user.id,
                    description=f'Created user: {username} with role: {role}',
                    request=request
                )

                if employee_created:
                    ActivityLog.log_activity(
                        user=request.user,
                        action_type='create',
                        model_name='Employee',
                        object_id=employee.id,
                        description=f'Auto-registered employee profile for user: {username}',
                        request=request
                    )
                
                messages.success(request, f'User "{username}" created successfully with role: {dict(ROLE_CHOICES)[role]}')
                if employee_created:
                    messages.info(request, f'Employee profile {employee.staff_code} was created in HR and assigned to {employee.branch.name}.')
                elif employee_warning:
                    messages.warning(request, f'User created, but HR auto-registration was skipped: {employee_warning}')
                return redirect('user_management_list', slug=request.business.slug)
                
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
    
    context = {
        'branches': branches,
        'roles': ROLE_CHOICES,
    }
    return render(request, 'pos/user_management_form.html', context)


@business_required
@manager_required
def user_edit_view(request, slug=None, pk=None):
    """Edit existing user"""
    membership = get_object_or_404(
        BusinessMembership, 
        user_id=pk, 
        business=request.business
    )
    user = membership.user
    branches = request.business.branches.filter(is_active=True).order_by('-is_default', 'name', 'pk')
    
    # Prevent editing owner if not owner
    is_requester_owner = (request.user.is_superuser or 
                          (hasattr(request, 'business_membership') and 
                           request.business_membership and 
                           request.business_membership.role == 'owner'))
    if membership.role == 'owner' and not is_requester_owner:
        messages.error(request, 'Only the business owner can edit owner accounts!')
        return redirect('user_management_list', slug=request.business.slug)
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email', '')
        role = request.POST.get('role')
        phone = request.POST.get('phone', '')
        employee_id = request.POST.get('employee_id', '')
        branch_id = request.POST.get('branch_id', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        try:
            with transaction.atomic():
                # Update user
                user.first_name = first_name
                user.last_name = last_name
                user.email = email
                user.is_active = is_active
                user.save()
                
                # Update profile
                profile, created = UserProfile.objects.get_or_create(user=user)
                profile.phone = phone
                profile.employee_id = employee_id if employee_id else None
                profile.save()
                
                # Update membership role (only if not changing owner)
                if role and membership.role != 'owner':
                    old_role = membership.role
                    membership.role = role
                    membership.save()
                    
                    ActivityLog.log_activity(
                        user=request.user,
                        action_type='update',
                        model_name='User',
                        object_id=user.id,
                        description=f'Changed role from {old_role} to {role} for user: {user.username}',
                        request=request
                    )
                
                # Update granular permissions
                submitted_perms = request.POST.getlist('permissions')
                valid_perms = [p for p in submitted_perms if p in PERMISSION_CODES]
                if valid_perms or 'permissions' in request.POST:
                    old_perms = list(membership.permissions)
                    BusinessMembership.objects.filter(pk=membership.pk).update(permissions=valid_perms)
                    if old_perms != valid_perms:
                        ActivityLog.log_activity(
                            user=request.user,
                            action_type='update',
                            model_name='BusinessMembership',
                            object_id=membership.pk,
                            description=f'Permissions updated for {user.username}: {old_perms} → {valid_perms}',
                            request=request
                        )

                effective_role = membership.role
                employee, employee_created, employee_warning = _sync_employee_profile(
                    user=user,
                    business=request.business,
                    role=effective_role,
                    branch_id=branch_id or None,
                    profile=profile,
                )

                if employee_created:
                    ActivityLog.log_activity(
                        user=request.user,
                        action_type='create',
                        model_name='Employee',
                        object_id=employee.id,
                        description=f'Auto-registered employee profile for user: {user.username}',
                        request=request
                    )

                # Update max discount
                max_disc_str = request.POST.get('max_discount_pct', '').strip()
                if max_disc_str:
                    from decimal import Decimal
                    try:
                        max_disc = Decimal(max_disc_str)
                        if 0 <= max_disc <= 100:
                            BusinessMembership.objects.filter(pk=membership.pk).update(max_discount_pct=max_disc)
                    except Exception:
                        pass

                messages.success(request, f'User "{user.username}" updated successfully!')
                if employee_created:
                    messages.info(request, f'Employee profile {employee.staff_code} was created in HR and assigned to {employee.branch.name}.')
                elif employee_warning:
                    messages.warning(request, f'HR auto-registration was skipped: {employee_warning}')
                return redirect('user_management_list', slug=request.business.slug)
                
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
    
    PERMISSION_LABELS = {
        'can_refund_sale': 'Process Refunds',
        'can_void_sale': 'Void Sales',
        'can_edit_price': 'Override Item Price',
        'can_view_cost_price': 'View Cost Price',
        'can_apply_discount': 'Apply Discounts',
        'can_exceed_max_discount': 'Exceed Discount Limit',
        'can_manage_users': 'Manage Team Members',
        'can_view_reports': 'View Reports',
        'can_manage_stock': 'Manage Stock & Purchases',
    }
    permission_list = [(code, PERMISSION_LABELS.get(code, code)) for code in PERMISSION_CODES]
    profile, _ = UserProfile.objects.get_or_create(user=user)
    linked_employee = getattr(user, 'employee_profile', None)

    context = {
        'branches': branches,
        'linked_employee': linked_employee,
        'user': user,
        'membership': membership,
        'roles': ROLE_CHOICES,
        'is_edit': True,
        'permission_list': permission_list,
        'profile': profile,
    }
    return render(request, 'pos/user_management_form.html', context)


@business_required
@manager_required
def user_delete_view(request, slug=None, pk=None):
    """Remove user from business"""
    membership = get_object_or_404(
        BusinessMembership, 
        user_id=pk, 
        business=request.business
    )
    user = membership.user
    
    # Prevent deleting owner
    if membership.role == 'owner':
        messages.error(request, 'Cannot remove the business owner!')
        return redirect('user_management_list', slug=request.business.slug)
    
    # Prevent deleting self
    if user == request.user:
        messages.error(request, 'You cannot remove yourself!')
        return redirect('user_management_list', slug=request.business.slug)
    
    if request.method == 'POST':
        try:
            username = user.username
            membership.is_active = False
            membership.save()
            
            ActivityLog.log_activity(
                user=request.user,
                action_type='delete',
                model_name='User',
                object_id=user.id,
                description=f'Removed user: {username} from business',
                request=request
            )
            
            messages.success(request, f'User "{username}" removed from business successfully!')
            return redirect('user_management_list', slug=request.business.slug)
            
        except Exception as e:
            messages.error(request, f'Error removing user: {str(e)}')
    
    context = {
        'user': user,
        'membership': membership,
    }
    return render(request, 'pos/user_management_delete.html', context)


@business_required
@manager_required
def user_change_role_view(request, slug=None, pk=None):
    """Quick role change for a user"""
    membership = get_object_or_404(
        BusinessMembership, 
        user_id=pk, 
        business=request.business
    )
    
    if membership.role == 'owner':
        messages.error(request, 'Cannot change owner role!')
        return redirect('user_management_list', slug=request.business.slug)
    
    if request.method == 'POST':
        new_role = request.POST.get('role')
        
        if new_role and new_role in dict(ROLE_CHOICES):
            old_role = membership.role
            membership.role = new_role
            membership.save()
            
            ActivityLog.log_activity(
                user=request.user,
                action_type='update',
                model_name='User',
                object_id=membership.user.id,
                description=f'Changed role from {old_role} to {new_role} for user: {membership.user.username}',
                request=request
            )
            
            messages.success(
                request, 
                f'Role changed from {dict(ROLE_CHOICES)[old_role]} to {dict(ROLE_CHOICES)[new_role]}'
            )
        else:
            messages.error(request, 'Invalid role selected!')
    
    return redirect('user_management_list', slug=request.business.slug)
