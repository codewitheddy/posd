"""
Multi-tenancy views for business registration and management
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import Business, BusinessMembership, ActivityLog


def register_business(request):
    """
    Business registration page - allows users to create a new business
    Only accessible to users who don't already own a business (one license per user)
    """
    # Check if user is already logged in and owns a business
    if request.user.is_authenticated and not request.user.is_superuser:
        # Check if user already owns a business
        existing_business = Business.objects.filter(owner=request.user).first()
        if existing_business:
            messages.warning(request, 'You already have a business registered. Only one business per license is allowed.')
            return redirect('business_list')
    
    if request.method == 'POST':
        # Get form data
        business_name = request.POST.get('business_name', '').strip()
        user_email = request.POST.get('email', '').strip()
        user_username = request.POST.get('username', '').strip()
        user_password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        user_first_name = request.POST.get('first_name', '').strip()
        user_last_name = request.POST.get('last_name', '').strip()
        
        # Validation
        if not all([business_name, user_email, user_username, user_password, confirm_password, user_first_name, user_last_name]):
            messages.error(request, 'All fields are required.')
            return render(request, 'pos/register_business.html')
        
        # Username validation
        import re
        if not re.match(r'^[a-zA-Z0-9_]{4,20}$', user_username):
            messages.error(request, 'Username must be 4-20 characters and contain only letters, numbers, and underscores.')
            return render(request, 'pos/register_business.html')
        
        # Password validation
        if user_password != confirm_password:
            messages.error(request, 'Passwords do not match. Please try again.')
            return render(request, 'pos/register_business.html')
        
        if len(user_password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'pos/register_business.html')
        
        # Check if username already exists
        if User.objects.filter(username=user_username).exists():
            messages.error(request, 'Username already taken. Please choose a different username.')
            return render(request, 'pos/register_business.html')
        
        # Check if email already exists
        if User.objects.filter(email=user_email).exists():
            messages.error(request, 'Email already registered. Please login instead.')
            return render(request, 'pos/register_business.html')
        
        try:
            with transaction.atomic():
                # Create user with the provided username
                user = User.objects.create_user(
                    username=user_username,
                    email=user_email,
                    first_name=user_first_name,
                    last_name=user_last_name
                )
                # Set password explicitly to ensure proper hashing
                user.set_password(user_password)
                user.save()
                
                # Create business
                business = Business.objects.create(
                    name=business_name,
                    owner=user,
                    is_active=True,
                    is_trial=True,
                    trial_ends_at=timezone.now() + timedelta(days=30),  # 30-day trial
                    subscription_plan='free'
                )
                
                # Create membership
                BusinessMembership.objects.create(
                    user=user,
                    business=business,
                    role='owner',
                    is_active=True
                )
                
                # Store credentials in session for display on next page
                request.session['new_user_credentials'] = {
                    'username': user_username,
                    'email': user_email,
                    'business_name': business_name
                }
                
                # Log the user in
                login(request, user)
                
                messages.success(request, f'Welcome! Your business "{business_name}" has been created successfully.')
                return redirect('business_setup', slug=business.slug)
                
        except Exception as e:
            messages.error(request, f'Error creating business: {str(e)}')
            return render(request, 'pos/register_business.html')
    
    return render(request, 'pos/register_business.html')


@login_required
def business_list(request):
    """
    List all businesses the user has access to
    Superusers can see all businesses
    """
    if request.user.is_superuser:
        # Superusers see all businesses
        businesses = Business.objects.filter(is_active=True).select_related('owner').order_by('-created_at')
        # Create a membership-like structure for template compatibility
        memberships = []
        for business in businesses:
            # Create a pseudo-membership object
            class PseudoMembership:
                def __init__(self, business):
                    self.business = business
                    self.role = 'superuser'
                    self.joined_at = business.created_at
                    self.is_active = True
                
                def get_role_display(self):
                    return 'Platform Admin'
            
            memberships.append(PseudoMembership(business))
    else:
        # Regular users see only their businesses
        memberships = BusinessMembership.objects.filter(
            user=request.user,
            is_active=True,
            business__is_active=True
        ).select_related('business').order_by('-joined_at')
    
    context = {
        'memberships': memberships,
    }
    return render(request, 'pos/business_list.html', context)


@login_required
@login_required
def business_setup(request, slug):
    """
    Initial business setup wizard
    """
    business = get_object_or_404(Business, slug=slug)
    
    # Verify user has access
    if not request.user.is_superuser:
        membership = get_object_or_404(
            BusinessMembership,
            user=request.user,
            business=business,
            is_active=True
        )
        if membership.role not in ['owner', 'admin']:
            messages.error(request, 'You do not have permission to setup this business.')
            return redirect('business_list')
    
    if request.method == 'POST':
        # Update business details
        business.address = request.POST.get('address', '')
        business.phone = request.POST.get('phone', '')
        business.email = request.POST.get('email', '')
        business.tax_id = request.POST.get('tax_id', '')
        business.save()
        
        # Clear the credentials from session after setup
        if 'new_user_credentials' in request.session:
            del request.session['new_user_credentials']
        
        messages.success(request, 'Business setup completed!')
        return redirect('dashboard', slug=business.slug)
    
    context = {
        'business': business,
    }
    return render(request, 'pos/business_setup.html', context)


@login_required
def business_settings(request, slug):
    """
    Business settings page
    """
    business = get_object_or_404(Business, slug=slug)
    
    # Verify user has access
    if not request.user.is_superuser:
        membership = get_object_or_404(
            BusinessMembership,
            user=request.user,
            business=business,
            is_active=True
        )
        if membership.role not in ['owner', 'admin']:
            messages.error(request, 'You do not have permission to manage business settings.')
            return redirect('dashboard', slug=business.slug)
    
    if request.method == 'POST':
        # Update business details
        business.name = request.POST.get('name', business.name)
        business.description = request.POST.get('description', '')
        business.address = request.POST.get('address', '')
        business.phone = request.POST.get('phone', '')
        business.email = request.POST.get('email', '')
        business.website = request.POST.get('website', '')
        business.tax_id = request.POST.get('tax_id', '')
        business.save()
        
        messages.success(request, 'Business settings updated successfully!')
        return redirect('business_settings', slug=business.slug)
    
    context = {
        'business': business,
    }
    return render(request, 'pos/business_settings.html', context)


@login_required
def business_members(request, slug):
    """
    Manage business members
    """
    business = get_object_or_404(Business, slug=slug)
    
    # Verify user has access
    if not request.user.is_superuser:
        membership = get_object_or_404(
            BusinessMembership,
            user=request.user,
            business=business,
            is_active=True
        )
        if membership.role not in ['owner', 'admin', 'manager']:
            messages.error(request, 'You do not have permission to manage members.')
            return redirect('dashboard', slug=business.slug)
    
    # Get all members
    members = BusinessMembership.objects.filter(
        business=business
    ).select_related('user').order_by('-joined_at')
    
    context = {
        'business': business,
        'members': members,
    }
    return render(request, 'pos/business_members.html', context)


@login_required
def invite_member(request, slug):
    """
    Invite a new member to the business
    """
    business = get_object_or_404(Business, slug=slug)
    
    # Verify user has access
    if not request.user.is_superuser:
        membership = get_object_or_404(
            BusinessMembership,
            user=request.user,
            business=business,
            is_active=True
        )
        if membership.role not in ['owner', 'admin', 'manager']:
            messages.error(request, 'You do not have permission to invite members.')
            return redirect('business_members', slug=business.slug)
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', 'cashier')
        
        if not email:
            messages.error(request, 'Email is required.')
            return redirect('business_members', slug=business.slug)
        
        try:
            # Check if user exists
            user = User.objects.filter(email=email).first()
            
            if not user:
                messages.error(request, 'User with this email does not exist. They need to register first.')
                return redirect('business_members', slug=business.slug)
            
            # Check if already a member
            if BusinessMembership.objects.filter(user=user, business=business).exists():
                messages.error(request, 'User is already a member of this business.')
                return redirect('business_members', slug=business.slug)
            
            # Create membership
            BusinessMembership.objects.create(
                user=user,
                business=business,
                role=role,
                is_active=True
            )
            
            messages.success(request, f'{user.get_full_name() or user.username} has been added to your business.')
            return redirect('business_members', slug=business.slug)
            
        except Exception as e:
            messages.error(request, f'Error inviting member: {str(e)}')
            return redirect('business_members', slug=business.slug)
    
    return redirect('business_members', slug=business.slug)


@login_required
def remove_member(request, slug, member_id):
    """
    Remove a member from the business
    """
    business = get_object_or_404(Business, slug=slug)
    
    # Verify user has access
    if not request.user.is_superuser:
        membership = get_object_or_404(
            BusinessMembership,
            user=request.user,
            business=business,
            is_active=True
        )
        if membership.role not in ['owner', 'admin']:
            messages.error(request, 'You do not have permission to remove members.')
            return redirect('business_members', slug=business.slug)
    
    # Get member to remove
    member = get_object_or_404(BusinessMembership, id=member_id, business=business)
    
    # Prevent removing the owner
    if member.role == 'owner':
        messages.error(request, 'Cannot remove the business owner.')
        return redirect('business_members', slug=business.slug)
    
    # Remove member
    member.delete()
    messages.success(request, f'{member.user.get_full_name() or member.user.username} has been removed from your business.')
    
    return redirect('business_members', slug=business.slug)
