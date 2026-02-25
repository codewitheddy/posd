"""
Support Access Views
Handles support access requests for platform admins to access business dashboards
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from .models import Business, SupportAccessRequest
from .decorators import business_required


@login_required
def request_support_access(request, business_id):
    """Platform admin requests access to a business"""
    if not request.user.is_superuser:
        messages.error(request, 'Only platform admins can request support access.')
        return redirect('platform_admin_dashboard')
    
    business = get_object_or_404(Business, id=business_id)
    
    # Check if there's already an active or pending request
    existing = SupportAccessRequest.objects.filter(
        business=business,
        requested_by=request.user,
        status__in=['pending', 'approved']
    ).first()
    
    if existing:
        if existing.status == 'approved' and existing.is_active():
            messages.info(request, f'You already have active access to {business.name}.')
            return redirect('dashboard', slug=business.slug)
        elif existing.status == 'pending':
            messages.info(request, f'You already have a pending access request for {business.name}.')
            return redirect('platform_admin_dashboard')
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason for requesting access.')
        else:
            access_request = SupportAccessRequest.objects.create(
                business=business,
                requested_by=request.user,
                reason=reason
            )
            messages.success(
                request,
                f'Access request sent to {business.name}. The business owner will be notified.'
            )
            return redirect('platform_admin_dashboard')
    
    return render(request, 'pos/support_access_request_form.html', {
        'business': business
    })


@login_required
@business_required
def view_support_access_requests(request, slug=None):
    """Business owners view pending support access requests"""
    # Check if user is business owner
    if not request.business_membership or request.business_membership.role != 'owner':
        messages.error(request, 'Only business owners can manage support access requests.')
        return redirect('dashboard', slug=request.business.slug)
    
    pending_requests = SupportAccessRequest.objects.filter(
        business=request.business,
        status='pending'
    )
    
    active_access = SupportAccessRequest.objects.filter(
        business=request.business,
        status='approved'
    )
    
    # Check for expired access
    for access in active_access:
        access.is_active()  # This will update status if expired
    
    # Refresh after checking expiry
    active_access = SupportAccessRequest.objects.filter(
        business=request.business,
        status='approved'
    )
    
    access_history = SupportAccessRequest.objects.filter(
        business=request.business,
        status__in=['denied', 'expired', 'revoked']
    )[:20]
    
    return render(request, 'pos/support_access_requests.html', {
        'pending_requests': pending_requests,
        'active_access': active_access,
        'access_history': access_history
    })


@login_required
@business_required
def approve_support_access(request, request_id, slug=None):
    """Business owner approves a support access request"""
    if not request.business_membership or request.business_membership.role != 'owner':
        messages.error(request, 'Only business owners can approve support access.')
        return redirect('dashboard', slug=request.business.slug)
    
    access_request = get_object_or_404(
        SupportAccessRequest,
        id=request_id,
        business=request.business,
        status='pending'
    )
    
    if request.method == 'POST':
        duration_hours = int(request.POST.get('duration_hours', 24))
        notes = request.POST.get('notes', '').strip()
        
        access_request.notes = notes
        access_request.approve(request.user, duration_hours)
        
        messages.success(
            request,
            f'Access granted to {access_request.requested_by.get_full_name() or access_request.requested_by.username} '
            f'for {duration_hours} hours.'
        )
        return redirect('view_support_access_requests', slug=request.business.slug)
    
    return render(request, 'pos/support_access_approve.html', {
        'access_request': access_request
    })


@login_required
@business_required
def deny_support_access(request, request_id, slug=None):
    """Business owner denies a support access request"""
    if not request.business_membership or request.business_membership.role != 'owner':
        messages.error(request, 'Only business owners can deny support access.')
        return redirect('dashboard', slug=request.business.slug)
    
    access_request = get_object_or_404(
        SupportAccessRequest,
        id=request_id,
        business=request.business,
        status='pending'
    )
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        access_request.deny(request.user, notes)
        
        messages.success(request, 'Access request denied.')
        return redirect('view_support_access_requests', slug=request.business.slug)
    
    return render(request, 'pos/support_access_deny.html', {
        'access_request': access_request
    })


@login_required
@business_required
def revoke_support_access(request, request_id, slug=None):
    """Business owner revokes active support access"""
    if not request.business_membership or request.business_membership.role != 'owner':
        messages.error(request, 'Only business owners can revoke support access.')
        return redirect('dashboard', slug=request.business.slug)
    
    access_request = get_object_or_404(
        SupportAccessRequest,
        id=request_id,
        business=request.business,
        status='approved'
    )
    
    if request.method == 'POST':
        access_request.revoke()
        messages.success(request, 'Support access revoked.')
        return redirect('view_support_access_requests', slug=request.business.slug)
    
    return render(request, 'pos/support_access_revoke.html', {
        'access_request': access_request
    })


@login_required
def my_support_access_requests(request):
    """Platform admin views their support access requests"""
    if not request.user.is_superuser:
        messages.error(request, 'Access denied.')
        return redirect('business_list')
    
    pending = SupportAccessRequest.objects.filter(
        requested_by=request.user,
        status='pending'
    )
    
    active = SupportAccessRequest.objects.filter(
        requested_by=request.user,
        status='approved'
    )
    
    # Check for expired access
    for access in active:
        access.is_active()
    
    # Refresh after checking expiry
    active = SupportAccessRequest.objects.filter(
        requested_by=request.user,
        status='approved'
    )
    
    history = SupportAccessRequest.objects.filter(
        requested_by=request.user,
        status__in=['denied', 'expired', 'revoked']
    )[:20]
    
    return render(request, 'pos/my_support_access_requests.html', {
        'pending': pending,
        'active': active,
        'history': history
    })
