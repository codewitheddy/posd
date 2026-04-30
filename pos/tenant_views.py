"""
Multi-tenancy views for business registration and management
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages, auth
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from datetime import timedelta, datetime
from django.views.decorators.http import require_POST
from django.core.cache import cache
from .models import Business, BusinessMembership, ActivityLog, RegistrationSettings
from .services.registration_service import RegistrationService

logger = logging.getLogger(__name__)


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
    
    from decimal import Decimal
    from .models import BusinessSettings

    if request.method == 'POST':
        # Update business details
        business.address = request.POST.get('address', '')
        business.phone = request.POST.get('phone', '')
        business.email = request.POST.get('email', '')
        business.tax_id = request.POST.get('tax_id', '')
        business.setup_completed = True
        business.save()

        # Save working hours / attendance policy
        bsettings = BusinessSettings.get_settings(business)
        start_raw = request.POST.get('workday_start_time', '')
        end_raw = request.POST.get('workday_end_time', '')
        if start_raw:
            from datetime import datetime as _dt
            bsettings.workday_start_time = _dt.strptime(start_raw, '%H:%M').time()
        if end_raw:
            from datetime import datetime as _dt
            bsettings.workday_end_time = _dt.strptime(end_raw, '%H:%M').time()
        grace_raw = request.POST.get('late_grace_minutes', '')
        if grace_raw.isdigit():
            bsettings.late_grace_minutes = int(grace_raw)
        multiplier_raw = request.POST.get('overtime_rate_multiplier', '')
        if multiplier_raw:
            try:
                bsettings.overtime_rate_multiplier = Decimal(multiplier_raw)
            except Exception:
                pass
        bsettings.save()

        # Clear the credentials from session after setup
        if 'new_user_credentials' in request.session:
            del request.session['new_user_credentials']

        messages.success(request, 'Business setup completed!')
        return redirect('dashboard', slug=business.slug)

    bsettings = BusinessSettings.get_settings(business)
    context = {
        'business': business,
        'settings': bsettings,
    }
    return render(request, 'pos/business_setup.html', context)


@login_required
def business_settings(request, slug):
    """
    Unified business settings — single view, single template.
    Handles all form_type submissions: all-in-one (main form), working_hours,
    loyalty_settings, mpesa_settings.
    """
    from decimal import Decimal
    from .models import BusinessSettings, ActivityLog

    business = get_object_or_404(Business, slug=slug)

    # Permission check
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

    settings = BusinessSettings.get_settings(business)

    if request.method == 'POST':
        form_type = request.POST.get('form_type', '')

        # ── Main all-in-one form (no form_type) ──────────────────────────
        if not form_type:
            try:
                # Business info (stored on BusinessSettings for receipts)
                settings.business_name = request.POST.get('business_name', '').strip() or business.name
                settings.business_address = request.POST.get('business_address', '')
                settings.business_phone = request.POST.get('business_phone', '')
                settings.business_email = request.POST.get('business_email', '')
                settings.business_website = request.POST.get('business_website', '')
                settings.tax_id = request.POST.get('tax_id', '')

                # Logo
                if 'logo' in request.FILES:
                    settings.logo = request.FILES['logo']
                if request.POST.get('remove_logo') == 'true':
                    settings.logo = None

                # Tax
                settings.vat_rate = Decimal(request.POST.get('vat_rate', 16))
                settings.vat_enabled = request.POST.get('vat_enabled') == 'on'

                # Currency
                settings.currency_symbol = request.POST.get('currency_symbol', 'KES')
                settings.currency_position = request.POST.get('currency_position', 'before')

                # Receipt
                settings.receipt_header = request.POST.get('receipt_header', '')
                settings.receipt_footer = request.POST.get('receipt_footer', '')
                settings.show_logo_on_receipt = request.POST.get('show_logo_on_receipt') == 'on'

                # Thermal printer
                settings.thermal_receipt_width = int(request.POST.get('thermal_receipt_width', 80))
                settings.thermal_font_size = request.POST.get('thermal_font_size', 'medium')
                settings.thermal_print_logo = request.POST.get('thermal_print_logo') == 'on'
                settings.thermal_print_barcode = request.POST.get('thermal_print_barcode') == 'on'
                settings.thermal_auto_cut = request.POST.get('thermal_auto_cut') == 'on'
                settings.thermal_copies = int(request.POST.get('thermal_copies', 1))
                settings.thermal_show_tax_breakdown = request.POST.get('thermal_show_tax_breakdown') == 'on'

                # Stock
                settings.default_low_stock_threshold = int(request.POST.get('default_low_stock_threshold', 10))
                settings.enable_low_stock_alerts = request.POST.get('enable_low_stock_alerts') == 'on'
                settings.default_expiry_alert_days = int(request.POST.get('default_expiry_alert_days', 7))
                settings.enable_expiry_alerts = request.POST.get('enable_expiry_alerts') == 'on'

                # Theme
                settings.theme_primary = request.POST.get('theme_primary', '#224195')
                settings.theme_dark = request.POST.get('theme_dark', '#1a1514')
                settings.theme_light = request.POST.get('theme_light', '#d5d3d4')
                settings.theme_accent = request.POST.get('theme_accent', '#cd8a4c')

                # System
                settings.allow_negative_stock = request.POST.get('allow_negative_stock') == 'on'
                settings.require_product_code = request.POST.get('require_product_code') == 'on'
                settings.auto_generate_product_code = request.POST.get('auto_generate_product_code') == 'on'

                # M-Pesa (also in main form)
                settings.mpesa_enabled = request.POST.get('mpesa_enabled') == 'on'
                settings.mpesa_type = request.POST.get('mpesa_type', 'paybill')
                settings.mpesa_shortcode = request.POST.get('mpesa_shortcode', '').strip()
                settings.mpesa_phone = request.POST.get('mpesa_phone', '').strip()
                settings.mpesa_account_name = request.POST.get('mpesa_account_name', '').strip()
                settings.mpesa_account_reference = request.POST.get('mpesa_account_reference', '').strip()

                settings.updated_by = request.user
                settings.save()

                ActivityLog.log_activity(
                    user=request.user, action_type='settings',
                    model_name='BusinessSettings', object_id=settings.id,
                    description='Updated business settings', request=request,
                    business=business,
                )
                messages.success(request, 'Settings saved successfully!')
                return redirect('business_settings', slug=business.slug)
            except Exception as e:
                messages.error(request, f'Error saving settings: {str(e)}')

        # ── Attendance / Working Hours ────────────────────────────────────
        elif form_type == 'working_hours':
            try:
                settings.workday_start_time = datetime.strptime(
                    request.POST.get('workday_start_time', '08:00'), '%H:%M').time()
                settings.workday_end_time = datetime.strptime(
                    request.POST.get('workday_end_time', '17:00'), '%H:%M').time()
                settings.late_grace_minutes = int(request.POST.get('late_grace_minutes', 15))
                settings.overtime_rate_multiplier = Decimal(request.POST.get('overtime_rate_multiplier', '1.5'))
                settings.updated_by = request.user
                settings.save()
                ActivityLog.log_activity(
                    user=request.user, action_type='settings',
                    model_name='BusinessSettings', object_id=settings.id,
                    description='Updated attendance / working hours', request=request,
                    business=business,
                )
                messages.success(request, 'Attendance policy saved.')
                return redirect('business_settings', slug=business.slug)
            except ValueError:
                messages.error(request, 'Invalid time format. Use HH:MM.')
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')

        # ── Loyalty Program ───────────────────────────────────────────────
        elif form_type == 'loyalty_settings':
            try:
                settings.loyalty_enabled = request.POST.get('loyalty_enabled') == 'on'
                settings.loyalty_points_per_currency = Decimal(request.POST.get('loyalty_points_per_currency', 100))
                settings.loyalty_regular_multiplier = Decimal(request.POST.get('loyalty_regular_multiplier', 1.0))
                settings.loyalty_silver_multiplier = Decimal(request.POST.get('loyalty_silver_multiplier', 1.5))
                settings.loyalty_gold_multiplier = Decimal(request.POST.get('loyalty_gold_multiplier', 2.0))
                settings.loyalty_platinum_multiplier = Decimal(request.POST.get('loyalty_platinum_multiplier', 3.0))
                settings.loyalty_silver_threshold = Decimal(request.POST.get('loyalty_silver_threshold', 10000))
                settings.loyalty_gold_threshold = Decimal(request.POST.get('loyalty_gold_threshold', 50000))
                settings.loyalty_platinum_threshold = Decimal(request.POST.get('loyalty_platinum_threshold', 100000))
                settings.loyalty_points_value = Decimal(request.POST.get('loyalty_points_value', 1))
                settings.loyalty_min_points_redeem = int(request.POST.get('loyalty_min_points_redeem', 100))
                settings.loyalty_max_redeem_percentage = Decimal(request.POST.get('loyalty_max_redeem_percentage', 50))
                settings.loyalty_points_expire = request.POST.get('loyalty_points_expire') == 'on'
                settings.loyalty_points_expiry_months = int(request.POST.get('loyalty_points_expiry_months', 12))
                settings.updated_by = request.user
                settings.save()
                ActivityLog.log_activity(
                    user=request.user, action_type='settings',
                    model_name='BusinessSettings', object_id=settings.id,
                    description='Updated loyalty program settings', request=request,
                    business=business,
                )
                messages.success(request, 'Loyalty settings saved.')
                return redirect('business_settings', slug=business.slug)
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')

        # ── M-Pesa ────────────────────────────────────────────────────────
        elif form_type == 'mpesa_settings':
            try:
                settings.mpesa_enabled = request.POST.get('mpesa_enabled') == 'on'
                settings.mpesa_type = request.POST.get('mpesa_type', 'paybill')
                settings.mpesa_shortcode = request.POST.get('mpesa_shortcode', '').strip()
                settings.mpesa_phone = request.POST.get('mpesa_phone', '').strip()
                settings.mpesa_account_name = request.POST.get('mpesa_account_name', '').strip()
                settings.mpesa_account_reference = request.POST.get('mpesa_account_reference', '').strip()
                settings.updated_by = request.user
                settings.save()
                from .models import PaymentMethod
                PaymentMethod.objects.get_or_create(
                    business=business, code='MPESA',
                    defaults={'name': 'M-Pesa', 'is_active': True,
                              'requires_reference': True, 'icon': 'bi-phone'},
                )
                ActivityLog.log_activity(
                    user=request.user, action_type='settings',
                    model_name='BusinessSettings', object_id=settings.id,
                    description='Updated M-Pesa configuration', request=request,
                    business=business,
                )
                messages.success(request, 'M-Pesa settings saved.')
                return redirect('business_settings', slug=business.slug)
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')

    context = {
        'business': business,
        'settings': settings,
    }
    return render(request, 'pos/business_settings_enhanced.html', context)


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


@login_required
def edit_member(request, slug, member_id):
    """Edit a team member's role, permissions, discount ceiling, and PIN."""
    from .models import PERMISSION_CODES, UserProfile
    from decimal import Decimal
    from django.core.exceptions import ValidationError
    from django.db import transaction as db_transaction

    business = get_object_or_404(Business, slug=slug)

    # Only owner/admin can edit members
    if not request.user.is_superuser:
        requester_membership = get_object_or_404(
            BusinessMembership, user=request.user, business=business, is_active=True
        )
        if requester_membership.role not in ('owner', 'admin'):
            messages.error(request, 'You do not have permission to edit members.')
            return redirect('business_members', slug=slug)

    member = get_object_or_404(BusinessMembership, id=member_id, business=business)
    profile, _ = UserProfile.objects.get_or_create(user=member.user)

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
    # Build list of (code, label) tuples for template
    permission_list = [(code, PERMISSION_LABELS.get(code, code)) for code in PERMISSION_CODES]

    if request.method == 'POST':
        errors = {}

        # --- PIN ---
        new_pin = request.POST.get('new_pin', '').strip()
        clear_pin = request.POST.get('clear_pin') == '1'

        # --- Permissions ---
        submitted_perms = request.POST.getlist('permissions')
        invalid_perms = [p for p in submitted_perms if p not in PERMISSION_CODES]
        if invalid_perms:
            errors['permissions'] = f"Unknown permission codes: {', '.join(invalid_perms)}"

        # --- Max discount ---
        max_disc_str = request.POST.get('max_discount_pct', '').strip()
        max_disc = None
        if max_disc_str:
            try:
                max_disc = Decimal(max_disc_str)
                if max_disc < 0 or max_disc > 100:
                    errors['max_discount_pct'] = 'Discount limit must be between 0 and 100.'
            except Exception:
                errors['max_discount_pct'] = 'Invalid discount limit value.'

        # --- PIN validation ---
        if new_pin and not clear_pin:
            import re
            if not re.fullmatch(r'\d{4,6}', new_pin):
                errors['pin'] = 'PIN must be 4 to 6 digits.'

        if errors:
            context = {
                'business': business,
                'member': member,
                'profile': profile,
                'permission_list': permission_list,
                'errors': errors,
            }
            return render(request, 'pos/member_edit.html', context)

        try:
            with db_transaction.atomic():
                # Apply permissions
                if not invalid_perms:
                    old_perms = list(member.permissions)
                    member.permissions = submitted_perms
                    if max_disc is not None:
                        member.max_discount_pct = max_disc
                    # Use update_fields to avoid triggering save() role-reset logic
                    update_fields = ['permissions', 'updated_at']
                    if max_disc is not None:
                        update_fields.append('max_discount_pct')
                    BusinessMembership.objects.filter(pk=member.pk).update(
                        permissions=submitted_perms,
                        **({'max_discount_pct': max_disc} if max_disc is not None else {}),
                    )
                    member.refresh_from_db()

                    # Log permission change
                    if old_perms != submitted_perms:
                        ActivityLog.log_activity(
                            user=request.user,
                            action_type='update',
                            description=(
                                f'Permissions updated for {member.user.username}: '
                                f'{old_perms} → {submitted_perms}'
                            ),
                            model_name='BusinessMembership',
                            object_id=member.pk,
                            business=business,
                            operation_type='permission_change',
                            entity_type='BusinessMembership',
                            entity_id=str(member.pk),
                        )

                # Apply PIN changes
                if clear_pin:
                    profile.clear_pin()
                    ActivityLog.log_activity(
                        user=request.user,
                        action_type='update',
                        description=f'PIN cleared for {member.user.username}',
                        model_name='UserProfile',
                        object_id=profile.pk,
                        business=business,
                        operation_type='pin_cleared',
                        entity_type='UserProfile',
                        entity_id=str(profile.pk),
                    )
                elif new_pin:
                    profile.set_pin(new_pin)
                    ActivityLog.log_activity(
                        user=request.user,
                        action_type='update',
                        description=f'PIN set for {member.user.username}',
                        model_name='UserProfile',
                        object_id=profile.pk,
                        business=business,
                        operation_type='pin_set',
                        entity_type='UserProfile',
                        entity_id=str(profile.pk),
                    )

            messages.success(request, f'{member.user.get_full_name() or member.user.username} updated successfully.')
            return redirect('business_members', slug=slug)

        except ValidationError as ve:
            errors['pin'] = str(ve.message)
        except Exception as e:
            errors['general'] = f'Error saving changes: {str(e)}'

        context = {
            'business': business,
            'member': member,
            'profile': profile,
            'permission_list': permission_list,
            'errors': errors,
        }
        return render(request, 'pos/member_edit.html', context)

    # GET
    context = {
        'business': business,
        'member': member,
        'profile': profile,
        'permission_list': permission_list,
        'errors': {},
    }
    return render(request, 'pos/member_edit.html', context)


@require_POST
def pos_pin_login(request, slug):
    """PIN-based quick login for POS terminals."""
    from .models import UserProfile

    business = get_object_or_404(Business, slug=slug)
    employee_id = request.POST.get('employee_id', '').strip()
    pin = request.POST.get('pin', '').strip()

    if not employee_id or not pin:
        messages.error(request, 'Employee ID and PIN are required.')
        return redirect('login')

    # Look up user by employee_id within this business
    try:
        profile = UserProfile.objects.select_related('user').get(employee_id=employee_id)
        # Verify user is a member of this business
        BusinessMembership.objects.get(
            user=profile.user, business=business, is_active=True
        )
    except (UserProfile.DoesNotExist, BusinessMembership.DoesNotExist):
        messages.error(request, 'Invalid credentials.')
        return redirect('login')

    user = profile.user
    lockout_key = f'pin_lockout_{user.id}'
    attempts_key = f'pin_attempts_{user.id}'

    # Check lockout
    lockout_until = cache.get(lockout_key)
    if lockout_until:
        remaining = max(0, int((lockout_until - timezone.now()).total_seconds() / 60))
        messages.error(request, f'Account locked. Try again in {remaining} minute(s).')
        return redirect('login')

    # Check PIN set
    if not profile.has_pin_set:
        messages.error(request, 'PIN login is not enabled for this account.')
        return redirect('login')

    # Verify PIN
    if profile.check_pin(pin):
        # Success — reset attempts, log in
        cache.delete(attempts_key)
        auth.login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        ActivityLog.log_activity(
            user=user,
            action_type='login',
            description=f'PIN login for {user.username} at business {business.name}',
            model_name='UserProfile',
            object_id=profile.pk,
            request=request,
            business=business,
            operation_type='pin_login',
            entity_type='UserProfile',
            entity_id=str(profile.pk),
        )
        return redirect('dashboard', slug=slug)
    else:
        # Failure — increment counter
        attempts = cache.get(attempts_key, 0) + 1
        if attempts >= 5:
            # Lock for 15 minutes
            lockout_until = timezone.now() + timedelta(seconds=900)
            cache.set(lockout_key, lockout_until, 900)
            cache.delete(attempts_key)
            ActivityLog.log_activity(
                user=user,
                action_type='login',
                description=f'PIN login locked for {user.username} after 5 failed attempts',
                model_name='UserProfile',
                object_id=profile.pk,
                request=request,
                business=business,
                operation_type='pin_lockout',
                entity_type='UserProfile',
                entity_id=str(profile.pk),
                status='failure',
            )
            messages.error(request, 'Too many failed attempts. Account locked for 15 minutes.')
        else:
            cache.set(attempts_key, attempts, 900)
            messages.error(request, 'Invalid credentials.')
        return redirect('login')


# ==================== DATA BACKUP VIEWS ====================

@login_required
def backup_data(request, slug):
    """
    Data backup page — shows backup mode settings, sync status, snapshot history,
    and the legacy download/restore options.
    """
    business = get_object_or_404(Business, slug=slug)

    # Permission check
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

    # Handle POST actions
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'save_settings':
            try:
                from backup.models import TenantBackupSettings
                from backup.tasks import register_scheduled_backup, revoke_scheduled_backup
                settings_obj, _ = TenantBackupSettings.objects.get_or_create(
                    tenant=business,
                    defaults={'backup_mode': 'automatic', 'retention_days': 30, 'storage_mode': 'hybrid'},
                )
                settings_obj.backup_mode             = request.POST.get('backup_mode', 'automatic')
                settings_obj.storage_mode            = request.POST.get('storage_mode', 'hybrid')
                settings_obj.retention_days          = int(request.POST.get('retention_days', 30))
                interval = request.POST.get('schedule_interval_hours')
                settings_obj.schedule_interval_hours = int(interval) if interval else None
                settings_obj.full_clean()
                settings_obj.save()

                if settings_obj.backup_mode == 'scheduled':
                    register_scheduled_backup(business)
                else:
                    revoke_scheduled_backup(business)

                messages.success(request, 'Backup settings saved.')
            except Exception as exc:
                messages.error(request, f'Error saving settings: {exc}')
            return redirect('backup_data', slug=slug)

        elif action == 'manual_snapshot':
            try:
                from backup.services import BackupService
                snap = BackupService.create_snapshot(business, triggered_by=request.user)
                messages.success(
                    request,
                    f'Backup snapshot v{snap.version} created successfully '
                    f'({snap.event_count} events, {snap.file_size_bytes} bytes).'
                )
            except Exception as exc:
                messages.error(request, f'Backup failed: {exc}')
            return redirect('backup_data', slug=slug)

    # ── Build context ─────────────────────────────────────────────────────────

    # Backup settings
    try:
        from backup.models import BackupSnapshot, TenantBackupSettings
        backup_settings = TenantBackupSettings.objects.filter(tenant=business).first()
        snapshots = BackupSnapshot.objects.filter(tenant=business).exclude(
            status='deleted'
        ).order_by('-version')[:20]
        valid_intervals = TenantBackupSettings.VALID_INTERVALS
    except Exception:
        backup_settings = None
        snapshots = []
        valid_intervals = [6, 12, 24]

    # Sync status
    try:
        from sync.models import SyncStatus
        sync_statuses = list(SyncStatus.objects.filter(tenant=business))
    except Exception:
        sync_statuses = []

    # Pending events count
    try:
        from events.models import EventLog
        pending_events = EventLog.objects.filter(
            tenant=business, sync_status=EventLog.SYNC_STATUS_PENDING
        ).count()
    except Exception:
        pending_events = 0

    # Legacy backup history (ActivityLog)
    backups = ActivityLog.objects.filter(
        action_type='backup',
        description__icontains=business.name
    ).order_by('-timestamp')[:10]

    # Data stats
    stats = {
        'products':  business.products.count(),
        'customers': business.customers.count(),
        'sales':     business.sales.count(),
        'suppliers': business.suppliers.count(),
    }

    context = {
        'business':        business,
        'backup_settings': backup_settings,
        'snapshots':       snapshots,
        'valid_intervals': valid_intervals,
        'sync_statuses':   sync_statuses,
        'pending_events':  pending_events,
        'backups':         backups,
        'stats':           stats,
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


@login_required
def restore_backup(request, slug):
    """
    Restore business data from an uploaded JSON backup file.
    """
    import json
    import tempfile
    import os
    from django.core.management import call_command

    business = get_object_or_404(Business, slug=slug)

    if not request.user.is_superuser:
        membership = get_object_or_404(
            BusinessMembership,
            user=request.user,
            business=business,
            is_active=True
        )
        if membership.role not in ['owner', 'admin']:
            messages.error(request, 'You do not have permission to restore data.')
            return redirect('dashboard', slug=business.slug)

    if request.method != 'POST':
        return redirect('backup_data', slug=slug)

    backup_file = request.FILES.get('backup_file')
    if not backup_file:
        messages.error(request, 'Please select a backup file to restore.')
        return redirect('backup_data', slug=slug)

    if not backup_file.name.endswith('.json'):
        messages.error(request, 'Invalid file type. Please upload a .json backup file.')
        return redirect('backup_data', slug=slug)

    temp_path = None
    temp_dir = None
    try:
        content = backup_file.read()
        data = json.loads(content)
        if 'metadata' not in data or 'business' not in data:
            messages.error(request, 'Invalid backup file format.')
            return redirect('backup_data', slug=slug)

        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, backup_file.name)
        with open(temp_path, 'wb') as f:
            f.write(content)

        call_command('restore_business', temp_path, confirm=True)

        ActivityLog.log_activity(
            user=request.user,
            action_type='restore',
            model_name='Business',
            object_id=business.id,
            description=f'Restored backup for {business.name} from file: {backup_file.name}',
            request=request
        )

        messages.success(request, 'Data restored successfully from backup.')

    except json.JSONDecodeError:
        messages.error(request, 'Backup file is corrupted or not valid JSON.')
    except Exception as e:
        logger.error(f'Restore failed for {business.name}: {e}')
        messages.error(request, f'Restore failed: {str(e)}')
    finally:
        try:
            if temp_path:
                os.remove(temp_path)
            if temp_dir:
                os.rmdir(temp_dir)
        except Exception:
            pass

    return redirect('backup_data', slug=slug)


@login_required
def skip_setup(request, slug):
    """Mark setup as completed (skipped) so the redirect never fires again."""
    business = get_object_or_404(Business, slug=slug)
    if request.user.is_superuser or BusinessMembership.objects.filter(
        user=request.user, business=business, is_active=True, role__in=['owner', 'admin']
    ).exists():
        business.setup_completed = True
        business.save(update_fields=['setup_completed'])
    return redirect('dashboard', slug=business.slug)


def verify_email(request, token):
    """Verify email address with token"""
    success, message = RegistrationService.verify_email(token)
    
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    
    return redirect('login')
