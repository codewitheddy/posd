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
from .models import Business, BusinessMembership, ActivityLog, RegistrationSettings
from .services.registration_service import RegistrationService


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def register_business(request):
    """
    Business registration page with validation and control
    """
    # Check if user is already logged in and owns a business
    if request.user.is_authenticated and not request.user.is_superuser:
        existing_business = Business.objects.filter(owner=request.user).first()
        if existing_business:
            messages.warning(request, 'You already have a business registered. Only one business per license is allowed.')
            return redirect('business_list')
    
    # Get registration settings
    settings_obj = RegistrationSettings.get_settings()
    
    # Check if registration is enabled
    if not settings_obj.registration_enabled:
        messages.error(request, settings_obj.registration_closed_message)
        return render(request, 'pos/register_business.html', {
            'registration_closed': True,
            'settings': settings_obj
        })
    
    if request.method == 'POST':
        # Prepare registration data
        data = {
            'business_name': request.POST.get('business_name', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'first_name': request.POST.get('first_name', '').strip(),
            'last_name': request.POST.get('last_name', '').strip(),
            'phone': request.POST.get('phone', '').strip(),
            'business_type': request.POST.get('business_type', '').strip(),
            'kra_pin': request.POST.get('kra_pin', '').strip(),
            'invitation_code': request.POST.get('invitation_code', '').strip(),
        }
        
        # Get client info
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        # Create registration request
        registration, errors = RegistrationService.create_registration_request(
            data, ip_address, user_agent
        )
        
        if registration:
            # Success - check if it's instant registration (dict with credentials) or pending (object)
            if isinstance(registration, dict):
                # Instant registration - show credentials on screen
                return render(request, 'pos/registration_success.html', {
                    'credentials': registration,
                    'instant_registration': True
                })
            else:
                # Email verification or approval required
                if settings_obj.require_email_verification:
                    messages.success(request, 
                        f'Registration submitted! Please check your email ({data["email"]}) to verify your account.')
                elif settings_obj.require_admin_approval:
                    messages.success(request, 
                        'Registration submitted! Your request is pending admin approval. You will receive an email once approved.')
                else:
                    messages.success(request, 
                        'Registration completed! Check your email for login credentials.')
                
                return redirect('login')
        else:
            # Show errors
            if '_general' in errors:
                messages.error(request, errors['_general'])
            for field, error in errors.items():
                if field != '_general':
                    messages.error(request, f'{field.replace("_", " ").title()}: {error}')
    
    context = {
        'settings': settings_obj,
        'registration_closed': False,
    }
    return render(request, 'pos/register_business.html', context)


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
    Business settings page - handles business info and loyalty program settings
    """
    from decimal import Decimal
    from .models import BusinessSettings, ActivityLog
    
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
    
    # Get or create BusinessSettings
    settings = BusinessSettings.get_settings(business)
    
    if request.method == 'POST':
        form_type = request.POST.get('form_type', 'business_info')
        
        if form_type == 'business_info':
            # Update business details
            business.name = request.POST.get('name', business.name)
            business.description = request.POST.get('description', '')
            business.address = request.POST.get('address', '')
            business.phone = request.POST.get('phone', '')
            business.email = request.POST.get('email', '')
            business.website = request.POST.get('website', '')
            business.tax_id = request.POST.get('tax_id', '')
            
            try:
                business.save()
                
                # Log activity
                ActivityLog.log_activity(
                    user=request.user,
                    action_type='update',
                    model_name='Business',
                    object_id=business.id,
                    description='Updated business information',
                    request=request
                )
                
                messages.success(request, 'Business information updated successfully!')
                return redirect('business_settings', slug=business.slug)
            except Exception as e:
                messages.error(request, f'Error updating business info: {str(e)}')
        
        elif form_type == 'loyalty_settings':
            # Loyalty Program Settings
            try:
                settings.loyalty_enabled = request.POST.get('loyalty_enabled') == 'on'
                
                # Points Earning
                settings.loyalty_points_per_currency = Decimal(request.POST.get('loyalty_points_per_currency', 100))
                
                # Tier Multipliers
                settings.loyalty_regular_multiplier = Decimal(request.POST.get('loyalty_regular_multiplier', 1.0))
                settings.loyalty_silver_multiplier = Decimal(request.POST.get('loyalty_silver_multiplier', 1.5))
                settings.loyalty_gold_multiplier = Decimal(request.POST.get('loyalty_gold_multiplier', 2.0))
                settings.loyalty_platinum_multiplier = Decimal(request.POST.get('loyalty_platinum_multiplier', 3.0))
                
                # Tier Thresholds
                settings.loyalty_silver_threshold = Decimal(request.POST.get('loyalty_silver_threshold', 10000))
                settings.loyalty_gold_threshold = Decimal(request.POST.get('loyalty_gold_threshold', 50000))
                settings.loyalty_platinum_threshold = Decimal(request.POST.get('loyalty_platinum_threshold', 100000))
                
                # Points Redemption
                settings.loyalty_points_value = Decimal(request.POST.get('loyalty_points_value', 1))
                settings.loyalty_min_points_redeem = int(request.POST.get('loyalty_min_points_redeem', 100))
                settings.loyalty_max_redeem_percentage = Decimal(request.POST.get('loyalty_max_redeem_percentage', 50))
                
                # Points Expiry
                settings.loyalty_points_expire = request.POST.get('loyalty_points_expire') == 'on'
                settings.loyalty_points_expiry_months = int(request.POST.get('loyalty_points_expiry_months', 12))
                
                settings.updated_by = request.user
                settings.save()
                
                # Log activity
                ActivityLog.log_activity(
                    user=request.user,
                    action_type='settings',
                    model_name='BusinessSettings',
                    object_id=settings.id,
                    description='Updated loyalty program settings',
                    request=request
                )
                
                messages.success(request, 'Loyalty program settings updated successfully!')
                return redirect('business_settings', slug=business.slug)
                
            except Exception as e:
                messages.error(request, f'Error updating loyalty settings: {str(e)}')
        
        elif form_type == 'theme_colors':
            # Theme Color Settings
            try:
                settings.theme_primary = request.POST.get('theme_primary', '#224195')
                settings.theme_dark = request.POST.get('theme_dark', '#1a1514')
                settings.theme_light = request.POST.get('theme_light', '#d5d3d4')
                settings.theme_accent = request.POST.get('theme_accent', '#cd8a4c')
                
                settings.updated_by = request.user
                settings.save()
                
                # Log activity
                ActivityLog.log_activity(
                    user=request.user,
                    action_type='settings',
                    model_name='BusinessSettings',
                    object_id=settings.id,
                    description='Updated theme colors',
                    request=request
                )
                
                messages.success(request, 'Theme colors updated successfully! Refresh the page to see changes.')
                return redirect('business_settings', slug=business.slug)
                
            except Exception as e:
                messages.error(request, f'Error updating theme colors: {str(e)}')
    
    context = {
        'business': business,
        'settings': settings,
    }
    return render(request, 'pos/business_settings_tenant.html', context)


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


# ==================== DATA BACKUP VIEWS ====================

@login_required
def backup_data(request, slug):
    """
    Data backup page - allows business owners to download their data
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
            messages.error(request, 'You do not have permission to access backup data.')
            return redirect('dashboard', slug=business.slug)
    
    # Get backup history from activity log
    backups = ActivityLog.objects.filter(
        action_type='backup',
        description__icontains=business.name
    ).order_by('-timestamp')[:20]
    
    # Calculate data statistics
    stats = {
        'products': business.products.count(),
        'categories': business.categories.count(),
        'customers': business.customers.count(),
        'suppliers': business.suppliers.count(),
        'sales': business.sales.count(),
        'purchases': business.purchases.count(),
    }
    
    context = {
        'business': business,
        'backups': backups,
        'stats': stats,
    }
    return render(request, 'pos/backup_data.html', context)


@login_required
def download_backup(request, slug):
    """
    Generate and download business data backup
    """
    from django.http import HttpResponse, JsonResponse
    from django.core.management import call_command
    import os
    import tempfile
    import logging
    
    logger = logging.getLogger(__name__)
    
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
            messages.error(request, 'You do not have permission to download backup.')
            return redirect('dashboard', slug=business.slug)
    
    try:
        # Generate backup file
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        backup_file = os.path.join(temp_dir, f'{business.slug}_backup_{timestamp}.json')
        
        # Call backup command
        call_command('backup_business', business.id, output=backup_file)
        
        # Read file and serve for download
        if os.path.exists(backup_file):
            with open(backup_file, 'rb') as f:
                response = HttpResponse(f.read(), content_type='application/json')
                response['Content-Disposition'] = f'attachment; filename="{business.slug}_backup_{timestamp}.json"'
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='backup',
                model_name='Business',
                object_id=business.id,
                description=f'Downloaded backup for {business.name}',
                request=request
            )
            
            # Clean up temp file
            try:
                os.remove(backup_file)
                os.rmdir(temp_dir)
            except Exception:
                pass
            
            return response
        else:
            messages.error(request, 'Backup file generation failed. Please try again.')
            return redirect('backup_data', slug=slug)
    
    except Exception as e:
        logger.error(f'Backup download failed for {business.name}: {e}')
        messages.error(request, f'Backup failed: {str(e)}. Please contact support if this persists.')
        return redirect('backup_data', slug=slug)



def verify_email(request, token):
    """Verify email address with token"""
    success, message = RegistrationService.verify_email(token)
    
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    
    return redirect('login')
