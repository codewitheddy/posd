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

from .models import Business, BusinessMembership, UserProfile, ActivityLog
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
                
                # Log activity
                ActivityLog.log_activity(
                    user=request.user,
                    action_type='create',
                    model_name='User',
                    object_id=user.id,
                    description=f'Created user: {username} with role: {role}',
                    request=request
                )
                
                messages.success(request, f'User "{username}" created successfully with role: {dict(ROLE_CHOICES)[role]}')
                return redirect('user_management_list', slug=request.business.slug)
                
        except Exception as e:
            messages.error(request, f'Error creating user: {str(e)}')
    
    context = {
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
                
                messages.success(request, f'User "{user.username}" updated successfully!')
                return redirect('user_management_list', slug=request.business.slug)
                
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
    
    context = {
        'user': user,
        'membership': membership,
        'roles': ROLE_CHOICES,
        'is_edit': True,
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
