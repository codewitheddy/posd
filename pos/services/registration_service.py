"""
Registration Service
Handles business registration validation and workflow
"""

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from datetime import timedelta
import re
import secrets

from ..models import (
    Business, BusinessMembership, InvitationCode, 
    BusinessRegistration, RegistrationSettings, ActivityLog
)


class RegistrationService:
    """Service for handling business registration"""
    
    @staticmethod
    def validate_registration_data(data, ip_address=None):
        """
        Validate registration data against all rules
        Returns: (is_valid, errors_dict)
        """
        errors = {}
        settings_obj = RegistrationSettings.get_settings()
        
        # Check if registration is enabled
        if not settings_obj.registration_enabled:
            errors['_general'] = settings_obj.registration_closed_message
            return False, errors
        
        # Validate required fields
        required_fields = ['business_name', 'email', 'first_name', 'last_name', 'phone']
        for field in required_fields:
            if not data.get(field, '').strip():
                errors[field] = f'{field.replace("_", " ").title()} is required'
        
        # Validate email format
        email = data.get('email', '').strip().lower()
        if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors['email'] = 'Invalid email format'
        
        # Check if email already exists in User table
        if email and User.objects.filter(email=email).exists():
            errors['email'] = 'This email is already registered. Please login instead.'
        
        # Check if email has a pending registration
        if email:
            from django.db.models import Q
            existing_registration = BusinessRegistration.objects.filter(
                email=email
            ).filter(
                Q(status='pending') | 
                Q(status='email_verified') | 
                Q(status='pending_approval')
            ).first()
            
            if existing_registration:
                if existing_registration.status == 'pending':
                    errors['email'] = 'A registration with this email is pending. Please check your email for verification link.'
                elif existing_registration.status == 'email_verified':
                    errors['email'] = 'This email is verified and pending admin approval.'
                elif existing_registration.status == 'pending_approval':
                    errors['email'] = 'Your registration is pending admin approval.'
        
        # Check if email domain is allowed
        if email:
            is_allowed, message = settings_obj.is_email_allowed(email)
            if not is_allowed:
                errors['email'] = message
        
        # Check rate limits
        if ip_address:
            is_allowed, message = settings_obj.check_rate_limit_ip(ip_address)
            if not is_allowed:
                errors['_general'] = message
            
            if email:
                is_allowed, message = settings_obj.check_rate_limit_domain(email)
                if not is_allowed:
                    errors['_general'] = message
        
        # Validate invitation code if required
        if settings_obj.require_invitation_code:
            code = data.get('invitation_code', '').strip()
            if not code:
                errors['invitation_code'] = 'Invitation code is required'
            else:
                try:
                    invitation = InvitationCode.objects.get(code=code)
                    is_valid, message = invitation.is_valid()
                    if not is_valid:
                        errors['invitation_code'] = message
                    elif email:
                        can_use, message = invitation.can_use_with_email(email)
                        if not can_use:
                            errors['invitation_code'] = message
                except InvitationCode.DoesNotExist:
                    errors['invitation_code'] = 'Invalid invitation code'
        
        # Validate KRA PIN if required
        if settings_obj.require_kra_pin:
            kra_pin = data.get('kra_pin', '').strip()
            if not kra_pin:
                errors['kra_pin'] = 'KRA PIN is required'
            elif not re.match(r'^[A-Z]\d{9}[A-Z]$', kra_pin):
                errors['kra_pin'] = 'Invalid KRA PIN format (e.g., A123456789Z)'
        
        # Validate phone number
        phone = data.get('phone', '').strip()
        if phone and not re.match(r'^\+?[0-9]{10,15}$', phone.replace(' ', '')):
            errors['phone'] = 'Invalid phone number format'
        
        return len(errors) == 0, errors
    
    @staticmethod
    def create_registration_request(data, ip_address=None, user_agent=None):
        """
        Create a registration request
        Returns: (registration_or_credentials, error_message)
        If email verification disabled, returns (credentials_dict, None)
        If email verification enabled, returns (registration, None)
        """
        settings_obj = RegistrationSettings.get_settings()
        
        # Validate data
        is_valid, errors = RegistrationService.validate_registration_data(data, ip_address)
        if not is_valid:
            return None, errors
        
        try:
            with transaction.atomic():
                # Get invitation code if provided
                invitation_code = None
                if data.get('invitation_code'):
                    invitation_code = InvitationCode.objects.get(code=data['invitation_code'].strip())
                
                # If email verification is NOT required, create user immediately
                if not settings_obj.require_email_verification:
                    # Generate username from email
                    username = data['email'].split('@')[0]
                    base_username = username
                    counter = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}{counter}"
                        counter += 1
                    
                    # Generate temporary password
                    temp_password = secrets.token_urlsafe(12)
                    
                    # Create user
                    user = User.objects.create_user(
                        username=username,
                        email=data['email'].strip().lower(),
                        first_name=data['first_name'].strip(),
                        last_name=data['last_name'].strip()
                    )
                    user.set_password(temp_password)
                    user.save()
                    
                    # Create business
                    business = Business.objects.create(
                        name=data['business_name'].strip(),
                        owner=user,
                        is_active=False,  # Pending activation by admin
                        is_trial=True,
                        trial_ends_at=timezone.now() + timedelta(days=30),
                        subscription_plan='free',
                        phone=data['phone'].strip(),
                        tax_id=data.get('kra_pin', '').strip()
                    )
                    
                    # Create membership
                    BusinessMembership.objects.create(
                        user=user,
                        business=business,
                        role='owner',
                        is_active=True
                    )
                    
                    # Create registration record for tracking
                    registration = BusinessRegistration.objects.create(
                        email=data['email'].strip().lower(),
                        first_name=data['first_name'].strip(),
                        last_name=data['last_name'].strip(),
                        phone=data['phone'].strip(),
                        business_name=data['business_name'].strip(),
                        business_type=data.get('business_type', '').strip(),
                        kra_pin=data.get('kra_pin', '').strip(),
                        invitation_code=invitation_code,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        status='completed',
                        user=user,
                        business=business,
                        completed_at=timezone.now()
                    )
                    
                    # Increment invitation code usage
                    if invitation_code:
                        invitation_code.use()
                    
                    # Log activity
                    ActivityLog.log_activity(
                        user=user,
                        action_type='create',
                        model_name='Business',
                        object_id=business.id,
                        description=f'Business registration completed: {business.name}'
                    )
                    
                    # Notify admins (email will fail silently if not configured)
                    if settings_obj.notify_admin_on_registration:
                        try:
                            RegistrationService.notify_admins_new_registration(registration)
                        except:
                            pass  # Don't fail registration if email fails
                    
                    # Return credentials for display
                    return {
                        'username': username,
                        'password': temp_password,
                        'email': data['email'],
                        'business_name': business.name,
                        'business_slug': business.slug,
                        'trial_days': 30
                    }, None
                
                else:
                    # Email verification required - create pending registration
                    registration = BusinessRegistration.objects.create(
                        email=data['email'].strip().lower(),
                        first_name=data['first_name'].strip(),
                        last_name=data['last_name'].strip(),
                        phone=data['phone'].strip(),
                        business_name=data['business_name'].strip(),
                        business_type=data.get('business_type', '').strip(),
                        kra_pin=data.get('kra_pin', '').strip(),
                        invitation_code=invitation_code,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        status='pending'
                    )
                    
                    # Increment invitation code usage
                    if invitation_code:
                        invitation_code.use()
                    
                    # Generate verification token
                    registration.generate_verification_token()
                    
                    # Send verification email
                    RegistrationService.send_verification_email(registration)
                    
                    # Notify admins
                    if settings_obj.notify_admin_on_registration:
                        RegistrationService.notify_admins_new_registration(registration)
                    
                    return registration, None
                
        except Exception as e:
            return None, {'_general': f'Registration failed: {str(e)}'}
        # Validate data
        is_valid, errors = RegistrationService.validate_registration_data(data, ip_address)
        if not is_valid:
            return None, errors
        
        try:
            with transaction.atomic():
                # Get invitation code if provided
                invitation_code = None
                if data.get('invitation_code'):
                    invitation_code = InvitationCode.objects.get(code=data['invitation_code'].strip())
                
                # Create registration request
                registration = BusinessRegistration.objects.create(
                    email=data['email'].strip().lower(),
                    first_name=data['first_name'].strip(),
                    last_name=data['last_name'].strip(),
                    phone=data['phone'].strip(),
                    business_name=data['business_name'].strip(),
                    business_type=data.get('business_type', '').strip(),
                    kra_pin=data.get('kra_pin', '').strip(),
                    invitation_code=invitation_code,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status='pending'
                )
                
                # Increment invitation code usage
                if invitation_code:
                    invitation_code.use()
                
                # Generate verification token
                if settings_obj.require_email_verification:
                    registration.generate_verification_token()
                
                # Send verification email
                if settings_obj.require_email_verification:
                    RegistrationService.send_verification_email(registration)
                
                # Notify admins
                if settings_obj.notify_admin_on_registration:
                    RegistrationService.notify_admins_new_registration(registration)
                
                return registration, None
                
        except Exception as e:
            return None, {'_general': f'Registration failed: {str(e)}'}
    
    @staticmethod
    def send_verification_email(registration):
        """Send email verification link"""
        try:
            verification_url = f"{settings.SITE_URL}/verify-email/{registration.email_verification_token}/"
            
            subject = 'Verify Your Email - Marid POS'
            message = f"""
Hello {registration.first_name},

Thank you for registering your business "{registration.business_name}" with our Marid POS.

Please verify your email address by clicking the link below:
{verification_url}

This link will expire in 24 hours.

If you didn't create this account, please ignore this email.

Need Help?
Email: info@marid.co.ke
Phone/WhatsApp: +254 717 147 700

Best regards,
Marid POS Team
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [registration.email],
                fail_silently=False,
            )
            return True
        except Exception as e:
            print(f"Failed to send verification email: {e}")
            return False
    
    @staticmethod
    def verify_email(token):
        """Verify email with token"""
        try:
            registration = BusinessRegistration.objects.get(
                email_verification_token=token,
                status='pending'
            )
            
            # Check if token is expired (24 hours)
            if registration.created_at < timezone.now() - timedelta(hours=24):
                return False, "Verification link has expired. Please request a new one."
            
            # Mark as verified
            registration.verify_email()
            
            # Check if admin approval is required
            settings_obj = RegistrationSettings.get_settings()
            if settings_obj.require_admin_approval:
                registration.status = 'pending_approval'
                registration.save()
                return True, "Email verified! Your registration is pending admin approval."
            else:
                # Auto-approve and complete registration
                return RegistrationService.complete_registration(registration)
            
        except BusinessRegistration.DoesNotExist:
            return False, "Invalid or expired verification link."
    
    @staticmethod
    def complete_registration(registration):
        """Complete registration by creating user and business"""
        try:
            with transaction.atomic():
                # Generate username from email
                username = registration.email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                # Generate temporary password
                temp_password = secrets.token_urlsafe(12)
                
                # Create user
                user = User.objects.create_user(
                    username=username,
                    email=registration.email,
                    first_name=registration.first_name,
                    last_name=registration.last_name
                )
                user.set_password(temp_password)
                user.save()
                
                # Create business
                business = Business.objects.create(
                    name=registration.business_name,
                    owner=user,
                    is_active=True,
                    is_trial=True,
                    trial_ends_at=timezone.now() + timedelta(days=30),
                    subscription_plan='free',
                    phone=registration.phone,
                    tax_id=registration.kra_pin
                )
                
                # Create membership
                BusinessMembership.objects.create(
                    user=user,
                    business=business,
                    role='owner',
                    is_active=True
                )
                
                # Update registration
                registration.user = user
                registration.business = business
                registration.status = 'completed'
                registration.completed_at = timezone.now()
                registration.save()
                
                # Send welcome email with credentials
                RegistrationService.send_welcome_email(registration, username, temp_password)
                
                # Log activity
                ActivityLog.log_activity(
                    user=user,
                    action_type='create',
                    model_name='Business',
                    object_id=business.id,
                    description=f'Business registration completed: {business.name}'
                )
                
                return True, f"Registration completed! Check your email for login credentials."
                
        except Exception as e:
            return False, f"Failed to complete registration: {str(e)}"
    
    @staticmethod
    def send_welcome_email(registration, username, password):
        """Send welcome email with login credentials"""
        try:
            login_url = f"{settings.SITE_URL}/login/"
            
            subject = 'Welcome to Marid POS - Your Account is Ready!'
            message = f"""
Hello {registration.first_name},

Welcome to Marid POS! Your business "{registration.business_name}" has been successfully registered.

Your Login Credentials:
Username: {username}
Temporary Password: {password}
Login URL: {login_url}

IMPORTANT: Please change your password after your first login.

Your 30-day free trial has started. Explore all features and let us know if you need any help.

Need Support?
Email: info@marid.co.ke
Phone/WhatsApp: +254 717 147 700

Best regards,
Marid POS Team
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [registration.email],
                fail_silently=False,
            )
            return True
        except Exception as e:
            print(f"Failed to send welcome email: {e}")
            return False
    
    @staticmethod
    def notify_admins_new_registration(registration):
        """Notify admins of new registration"""
        try:
            settings_obj = RegistrationSettings.get_settings()
            if not settings_obj.admin_notification_emails:
                return False
            
            admin_emails = [e.strip() for e in settings_obj.admin_notification_emails.split(',')]
            
            subject = f'New Registration: {registration.business_name}'
            message = f"""
New business registration received:

Business Name: {registration.business_name}
Owner: {registration.first_name} {registration.last_name}
Email: {registration.email}
Phone: {registration.phone}
KRA PIN: {registration.kra_pin or 'Not provided'}
IP Address: {registration.ip_address}
Status: {registration.get_status_display()}

Registered at: {registration.created_at}
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                admin_emails,
                fail_silently=True,
            )
            return True
        except Exception as e:
            print(f"Failed to notify admins: {e}")
            return False
    
    @staticmethod
    def approve_registration(registration, admin_user):
        """Approve a pending registration"""
        if registration.status != 'pending_approval' and registration.status != 'email_verified':
            return False, "Registration is not pending approval"
        
        registration.reviewed_by = admin_user
        registration.reviewed_at = timezone.now()
        registration.status = 'approved'
        registration.save()
        
        # Complete registration
        return RegistrationService.complete_registration(registration)
    
    @staticmethod
    def reject_registration(registration, admin_user, reason):
        """Reject a pending registration"""
        if registration.status != 'pending_approval' and registration.status != 'email_verified':
            return False, "Registration is not pending approval"
        
        registration.reviewed_by = admin_user
        registration.reviewed_at = timezone.now()
        registration.status = 'rejected'
        registration.rejection_reason = reason
        registration.save()
        
        # Send rejection email
        try:
            subject = 'Registration Update - Marid POS'
            message = f"""
Hello {registration.first_name},

Thank you for your interest in our Marid POS.

Unfortunately, your registration for "{registration.business_name}" has not been approved at this time.

Reason: {reason}

If you have any questions, please contact our support team:
Email: info@marid.co.ke
Phone/WhatsApp: +254 717 147 700

Best regards,
Marid POS Team
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [registration.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Failed to send rejection email: {e}")
        
        return True, "Registration rejected successfully"
