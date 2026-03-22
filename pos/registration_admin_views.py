"""
Registration Admin Views
Manage invitation codes and registration approvals
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, F
from datetime import timedelta
import secrets

from .models import InvitationCode, BusinessRegistration, RegistrationSettings
from .services.registration_service import RegistrationService


@staff_member_required
def invitation_codes_list(request):
    """List all invitation codes"""
    codes = InvitationCode.objects.all().select_related('created_by')
    
    # Filter by status
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'active':
        codes = codes.filter(is_active=True, uses_count__lt=F('max_uses'))
    elif status_filter == 'expired':
        codes = codes.filter(Q(valid_until__lt=timezone.now()) | Q(uses_count__gte=F('max_uses')))
    elif status_filter == 'inactive':
        codes = codes.filter(is_active=False)
    
    context = {
        'codes': codes,
        'status_filter': status_filter,
    }
    return render(request, 'pos/admin/invitation_codes_list.html', context)


@staff_member_required
def invitation_code_create(request):
    """Create new invitation codes"""
    if request.method == 'POST':
        count = int(request.POST.get('count', 1))
        max_uses = int(request.POST.get('max_uses', 1))
        valid_days = request.POST.get('valid_days', '')
        allowed_domains = request.POST.get('allowed_domains', '').strip()
        notes = request.POST.get('notes', '').strip()
        
        try:
            # Calculate expiry
            valid_until = None
            if valid_days:
                valid_until = timezone.now() + timedelta(days=int(valid_days))
            
            # Generate codes
            codes_created = []
            for _ in range(count):
                code = secrets.token_urlsafe(12)[:12].upper()
                
                invitation = InvitationCode.objects.create(
                    code=code,
                    created_by=request.user,
                    max_uses=max_uses,
                    valid_until=valid_until,
                    allowed_email_domains=allowed_domains,
                    notes=notes
                )
                codes_created.append(code)
            
            messages.success(request, f'Successfully created {count} invitation code(s)')
            
            # Store codes in session to display
            request.session['new_codes'] = codes_created
            return redirect('invitation_codes_list')
            
        except Exception as e:
            messages.error(request, f'Error creating codes: {str(e)}')
    
    context = {}
    return render(request, 'pos/admin/invitation_code_create.html', context)


@staff_member_required
def invitation_code_toggle(request, code_id):
    """Toggle invitation code active status"""
    code = get_object_or_404(InvitationCode, id=code_id)
    code.is_active = not code.is_active
    code.save()
    
    status = "activated" if code.is_active else "deactivated"
    messages.success(request, f'Invitation code {code.code} has been {status}')
    return redirect('invitation_codes_list')


@staff_member_required
def registrations_list(request):
    """List all registration requests"""
    registrations = BusinessRegistration.objects.all().select_related(
        'invitation_code', 'reviewed_by', 'user', 'business'
    )
    
    # Filter by status
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        registrations = registrations.filter(status=status_filter)
    
    context = {
        'registrations': registrations,
        'status_filter': status_filter,
        'status_choices': BusinessRegistration.STATUS_CHOICES,
    }
    return render(request, 'pos/admin/registrations_list.html', context)


@staff_member_required
def registration_approve(request, registration_id):
    """Approve a registration request"""
    registration = get_object_or_404(BusinessRegistration, id=registration_id)
    
    if request.method == 'POST':
        success, message = RegistrationService.approve_registration(registration, request.user)
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('registrations_list')
    
    context = {
        'registration': registration,
    }
    return render(request, 'pos/admin/registration_approve.html', context)


@staff_member_required
def registration_reject(request, registration_id):
    """Reject a registration request"""
    registration = get_object_or_404(BusinessRegistration, id=registration_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        
        if not reason:
            messages.error(request, 'Please provide a reason for rejection')
            return render(request, 'pos/admin/registration_reject.html', {'registration': registration})
        
        success, message = RegistrationService.reject_registration(registration, request.user, reason)
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('registrations_list')
    
    context = {
        'registration': registration,
    }
    return render(request, 'pos/admin/registration_reject.html', context)


@staff_member_required
def registration_settings_view(request):
    """Manage registration settings"""
    settings_obj = RegistrationSettings.get_settings()
    
    if request.method == 'POST':
        try:
            # Update settings
            settings_obj.registration_enabled = request.POST.get('registration_enabled') == 'on'
            settings_obj.require_invitation_code = request.POST.get('require_invitation_code') == 'on'
            settings_obj.require_email_verification = request.POST.get('require_email_verification') == 'on'
            settings_obj.require_admin_approval = request.POST.get('require_admin_approval') == 'on'
            settings_obj.require_kra_pin = request.POST.get('require_kra_pin') == 'on'
            settings_obj.require_phone_verification = request.POST.get('require_phone_verification') == 'on'
            
            settings_obj.max_registrations_per_ip_per_day = int(request.POST.get('max_registrations_per_ip_per_day', 3))
            settings_obj.max_registrations_per_email_domain_per_day = int(request.POST.get('max_registrations_per_email_domain_per_day', 10))
            
            settings_obj.blocked_email_domains = request.POST.get('blocked_email_domains', '').strip()
            settings_obj.allowed_email_domains = request.POST.get('allowed_email_domains', '').strip()
            
            settings_obj.notify_admin_on_registration = request.POST.get('notify_admin_on_registration') == 'on'
            settings_obj.admin_notification_emails = request.POST.get('admin_notification_emails', '').strip()
            
            settings_obj.registration_closed_message = request.POST.get('registration_closed_message', '').strip()
            
            settings_obj.save()
            
            messages.success(request, 'Registration settings updated successfully')
            return redirect('registration_settings')
            
        except Exception as e:
            messages.error(request, f'Error updating settings: {str(e)}')
    
    context = {
        'settings': settings_obj,
    }
    return render(request, 'pos/admin/registration_settings.html', context)
