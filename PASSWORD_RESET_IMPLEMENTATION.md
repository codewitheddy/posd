# Password Reset Implementation Guide

## Overview
A secure password reset system that allows users to reset their passwords via email.

## Implementation Steps

### 1. Configure Email Backend

Add to `settings.py`:

```python
# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@yourpos.com')
```

### 2. Create Password Reset Views

```python
# In views.py
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str

def password_reset_request(request):
    """Request password reset"""
    if request.method == 'POST':
        email = request.POST.get('email')
        users = User.objects.filter(email=email)
        
        if users.exists():
            for user in users:
                # Generate token
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                # Build reset URL
                reset_url = request.build_absolute_uri(
                    reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
                )
                
                # Send email
                subject = 'Password Reset Request'
                message = f'''
                Hello {user.get_full_name() or user.username},
                
                You requested a password reset for your POS account.
                
                Click the link below to reset your password:
                {reset_url}
                
                This link will expire in 24 hours.
                
                If you didn't request this, please ignore this email.
                
                Best regards,
                POS System Team
                '''
                
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
        
        # Always show success to prevent email enumeration
        messages.success(request, 'If an account exists with that email, you will receive password reset instructions.')
        return redirect('login')
    
    return render(request, 'pos/password_reset_request.html')

def password_reset_confirm(request, uidb64, token):
    """Confirm password reset with token"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    if user and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            
            if password1 == password2:
                user.set_password(password1)
                user.save()
                messages.success(request, 'Password reset successful! You can now login.')
                return redirect('login')
            else:
                messages.error(request, 'Passwords do not match.')
        
        return render(request, 'pos/password_reset_confirm.html', {'validlink': True})
    else:
        return render(request, 'pos/password_reset_confirm.html', {'validlink': False})
```

### 3. Add URL Patterns

```python
# In urls_multitenant.py
urlpatterns = [
    # ... existing patterns ...
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
]
```

### 4. Create Templates

#### password_reset_request.html
```html
{% extends 'pos/base_simple.html' %}

{% block title %}Reset Password{% endblock %}

{% block content %}
<div class="container">
    <div class="row justify-content-center mt-5">
        <div class="col-md-6">
            <div class="card shadow">
                <div class="card-body p-5">
                    <h2 class="text-center mb-4">Reset Password</h2>
                    <p class="text-muted text-center mb-4">
                        Enter your email address and we'll send you instructions to reset your password.
                    </p>
                    
                    <form method="POST">
                        {% csrf_token %}
                        <div class="mb-3">
                            <label for="email" class="form-label">Email Address</label>
                            <input type="email" class="form-control" id="email" name="email" required>
                        </div>
                        
                        <button type="submit" class="btn btn-primary w-100">
                            Send Reset Link
                        </button>
                    </form>
                    
                    <div class="text-center mt-3">
                        <a href="{% url 'login' %}">Back to Login</a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

#### password_reset_confirm.html
```html
{% extends 'pos/base_simple.html' %}

{% block title %}Set New Password{% endblock %}

{% block content %}
<div class="container">
    <div class="row justify-content-center mt-5">
        <div class="col-md-6">
            <div class="card shadow">
                <div class="card-body p-5">
                    {% if validlink %}
                        <h2 class="text-center mb-4">Set New Password</h2>
                        <p class="text-muted text-center mb-4">
                            Please enter your new password.
                        </p>
                        
                        <form method="POST">
                            {% csrf_token %}
                            <div class="mb-3">
                                <label for="password1" class="form-label">New Password</label>
                                <input type="password" class="form-control" id="password1" name="password1" required>
                            </div>
                            
                            <div class="mb-3">
                                <label for="password2" class="form-label">Confirm Password</label>
                                <input type="password" class="form-control" id="password2" name="password2" required>
                            </div>
                            
                            <button type="submit" class="btn btn-primary w-100">
                                Reset Password
                            </button>
                        </form>
                    {% else %}
                        <h2 class="text-center mb-4 text-danger">Invalid Link</h2>
                        <p class="text-center">
                            This password reset link is invalid or has expired.
                        </p>
                        <div class="text-center mt-4">
                            <a href="{% url 'password_reset_request' %}" class="btn btn-primary">
                                Request New Link
                            </a>
                        </div>
                    {% endif %}
                    
                    <div class="text-center mt-3">
                        <a href="{% url 'login' %}">Back to Login</a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### 5. Update Login Template

Add "Forgot Password?" link to login page:

```html
<!-- In login.html, after password field -->
<div class="text-end mb-3">
    <a href="{% url 'password_reset_request' %}">Forgot Password?</a>
</div>
```

## Email Service Options

### Option 1: Gmail (Development/Small Scale)
```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

**Note**: Use App Password, not regular password. Enable 2FA first.

### Option 2: SendGrid (Recommended for Production)
```env
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=your-sendgrid-api-key
```

### Option 3: AWS SES (Enterprise)
```env
EMAIL_BACKEND=django_ses.SESBackend
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_SES_REGION_NAME=us-east-1
```

### Option 4: Mailgun
```env
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_HOST_USER=postmaster@your-domain.mailgun.org
EMAIL_HOST_PASSWORD=your-mailgun-password
```

## Security Features

✅ **Token-based**: Secure one-time tokens
✅ **Time-limited**: Links expire after 24 hours
✅ **Email verification**: Only sent to registered emails
✅ **No email enumeration**: Same message for all requests
✅ **Secure password hashing**: Django's built-in security

## User Flow

1. User clicks "Forgot Password?" on login page
2. Enters email address
3. Receives email with reset link
4. Clicks link (valid for 24 hours)
5. Enters new password twice
6. Password is reset
7. User can login with new password

## Alternative: Manual Reset (Support)

For clients who can't access email:

1. Client contacts support
2. You verify their identity (security questions, business details)
3. Use Django Admin to reset password:
   - Go to Users
   - Click on user
   - Click "this form" under password field
   - Set new temporary password
   - Send to client securely
4. Client logs in and changes password

## Testing

```bash
# Test email in development (console backend)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Emails will print to console instead of sending
```

## Production Checklist

- [ ] Configure email service (SendGrid recommended)
- [ ] Set up SPF/DKIM records for domain
- [ ] Test email delivery
- [ ] Set appropriate token expiry
- [ ] Add rate limiting to prevent abuse
- [ ] Monitor email bounce rates
- [ ] Set up email templates with branding

## Future Enhancements

1. **SMS Reset**: Alternative to email
2. **Security Questions**: Additional verification
3. **2FA**: Two-factor authentication
4. **Password Strength Meter**: Visual feedback
5. **Password History**: Prevent reuse
6. **Account Lockout**: After failed attempts
7. **Email Verification**: On registration

This provides a complete, secure password reset system for your clients!
