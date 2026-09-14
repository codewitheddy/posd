"""
Branch management views for Marid POS multi-branch feature.
"""
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User

from .decorators import business_required
from .models import (
    Branch, BranchMembership, BranchStock, BranchPriceOverride,
    StockTransfer, Product, StockRequisition, StockRequisitionItem,
    StockTransferRequest, StockTransferItem, Dispatch, DispatchItem,
    StockMovement,
)
from .branch_services import (
    BranchStockService, StockTransferService, ConsolidatedReportService,
    DistributionService, is_owner_or_admin, is_branch_manager, get_user_branches,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_owner_admin(request):
    return is_owner_or_admin(request.user, request.business)


# ── Branch CRUD ───────────────────────────────────────────────────────────────

@login_required
@business_required
def branch_list(request, *args, **kwargs):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()

        if not name or not address:
            messages.error(request, 'Branch name and address are required.')
        else:
            try:
                branch = Branch.objects.create(
                    business=request.business,
                    name=name, address=address,
                    phone=phone, email=email,
                )
                messages.success(request, f'Branch "{name}" created successfully.')
            except Exception as e:
                if 'UNIQUE' in str(e).upper():
                    messages.error(request, f'A branch named "{name}" already exists.')
                else:
                    messages.error(request, f'Error creating branch: {e}')
        return redirect('branch_list')

    branches = list(Branch.objects.filter(business=request.business).prefetch_related('memberships', 'terminals').order_by('name'))
    active_branches_count = sum(1 for b in branches if b.is_active)
    hq_branch = next((b for b in branches if b.is_hq), None)
    return render(request, 'pos/branches/branch_list.html', {
        'branches': branches,
        'active_branches_count': active_branches_count,
        'hq_branch': hq_branch,
    })


@login_required
@business_required
def branch_detail(request, branch_id=None, *args, **kwargs):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('branch_list')

    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    if request.method == 'POST':
        branch.name = request.POST.get('name', branch.name).strip()
        branch.address = request.POST.get('address', branch.address).strip()
        branch.phone = request.POST.get('phone', branch.phone).strip()
        branch.email = request.POST.get('email', branch.email).strip()
        branch.is_active = request.POST.get('is_active') == '1'
        branch.is_default = request.POST.get('is_default') == '1'
        branch.save()
        messages.success(request, 'Branch updated.')
        return redirect('branch_detail', branch_id=branch_id)

    memberships = BranchMembership.objects.filter(branch=branch).select_related('user')
    return render(request, 'pos/branches/branch_detail.html', {
        'branch': branch,
        'memberships': memberships,
    })


# ── Branch Stock ──────────────────────────────────────────────────────────────

@login_required
@business_required
def branch_stock(request, branch_id=None, *args, **kwargs):
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    # Check access
    if not _require_owner_admin(request):
        if not BranchMembership.objects.filter(
            user=request.user, branch=branch, is_active=True
        ).exists():
            messages.error(request, 'Permission denied.')
            return redirect('branch_list')

    stock_records = BranchStock.objects.filter(branch=branch).select_related(
        'product', 'product__category'
    ).order_by('product__name')

    return render(request, 'pos/branches/branch_stock.html', {
        'branch': branch,
        'stock_records': stock_records,
    })


# ── Stock Transfers ───────────────────────────────────────────────────────────

@login_required
@business_required
def transfer_list(request, branch_id=None, *args, **kwargs):
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    if not _require_owner_admin(request):
        if not BranchMembership.objects.filter(
            user=request.user, branch=branch, is_active=True,
            role__in=['manager', 'stock_manager'],
        ).exists():
            messages.error(request, 'Permission denied.')
            return redirect('branch_list')

    transfers = StockTransfer.objects.filter(
        business=request.business
    ).filter(
        Q(source_branch=branch) | Q(destination_branch=branch)
    ).select_related('product', 'source_branch', 'destination_branch').order_by('-created_at')[:50]

    return render(request, 'pos/branches/transfer_list.html', {
        'branch': branch,
        'transfers': transfers,
    })


@login_required
@business_required
def transfer_create(request, branch_id=None, *args, **kwargs):
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    if not _require_owner_admin(request):
        if not BranchMembership.objects.filter(
            user=request.user, branch=branch, is_active=True,
            role__in=['manager', 'stock_manager'],
        ).exists():
            messages.error(request, 'Permission denied.')
            return redirect('branch_list')

    other_branches = Branch.objects.filter(
        business=request.business, is_active=True
    ).exclude(pk=branch.pk)

    if request.method == 'POST':
        dest_id = request.POST.get('destination_branch')
        product_id = request.POST.get('product')
        qty = request.POST.get('quantity', '0')
        note = request.POST.get('note', '')

        try:
            destination = Branch.objects.get(pk=dest_id, business=request.business)
            product = Product.objects.get(pk=product_id, business=request.business)
            from decimal import Decimal
            transfer = StockTransferService.create(
                source=branch,
                destination=destination,
                product=product,
                qty=Decimal(qty),
                note=note,
                initiated_by=request.user,
            )
            # Auto-confirm immediately
            StockTransferService.confirm(transfer)
            messages.success(
                request,
                f'Transferred {qty} × {product.name} to {destination.name}.'
            )
        except Exception as e:
            messages.error(request, str(e))

        return redirect('transfer_list', branch_id=branch_id)

    products = Product.objects.filter(business=request.business, is_active=True).order_by('name')
    return render(request, 'pos/branches/transfer_form.html', {
        'branch': branch,
        'other_branches': other_branches,
        'products': products,
    })


@login_required
@business_required
def business_transfer_list(request, *args, **kwargs):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard')

    transfers = StockTransfer.objects.filter(
        business=request.business
    ).select_related(
        'product', 'source_branch', 'destination_branch', 'initiated_by'
    ).order_by('-created_at')[:100]

    return render(request, 'pos/branches/business_transfer_list.html', {
        'transfers': transfers,
    })


# ── Branch Memberships ────────────────────────────────────────────────────────

@login_required
@business_required
def branch_membership_list(request, branch_id=None, *args, **kwargs):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('branch_list')

    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            username = request.POST.get('username', '').strip()
            role = request.POST.get('role', 'cashier')
            try:
                user = User.objects.get(username=username)
                BranchMembership.objects.update_or_create(
                    user=user, branch=branch,
                    defaults={'role': role, 'is_active': True},
                )
                messages.success(request, f'{username} added to {branch.name}.')
            except User.DoesNotExist:
                messages.error(request, f'User "{username}" not found.')
        elif action == 'create_and_add':
            new_username = request.POST.get('new_username', '').strip()
            new_password = request.POST.get('new_password', '').strip()
            new_email = request.POST.get('new_email', '').strip()
            new_first = request.POST.get('new_first_name', '').strip()
            new_last = request.POST.get('new_last_name', '').strip()
            role = request.POST.get('new_role', 'cashier')
            if not new_username or not new_password:
                messages.error(request, 'Username and password are required.')
            elif User.objects.filter(username=new_username).exists():
                messages.error(request, f'Username "{new_username}" is already taken.')
            else:
                from django.contrib.auth.password_validation import validate_password
                from django.core.exceptions import ValidationError as DjangoValidationError
                from .models import BusinessMembership
                try:
                    validate_password(new_password)
                    new_user = User.objects.create_user(
                        username=new_username, password=new_password,
                        email=new_email, first_name=new_first, last_name=new_last,
                    )
                    BusinessMembership.objects.get_or_create(
                        user=new_user, business=branch.business,
                        defaults={'role': role, 'is_active': True},
                    )
                    BranchMembership.objects.create(
                        user=new_user, branch=branch, role=role, is_active=True
                    )
                    messages.success(request, f'User "{new_username}" created and assigned to {branch.name} as {role}.')
                except DjangoValidationError as ve:
                    messages.error(request, 'Password: ' + ' '.join(ve.messages))
                except Exception as e:
                    messages.error(request, f'Error: {e}')
        elif action == 'deactivate':
            membership_id = request.POST.get('membership_id')
            BranchMembership.objects.filter(
                pk=membership_id, branch=branch
            ).update(is_active=False)
            messages.success(request, 'Staff access revoked.')
        return redirect('branch_membership_list', branch_id=branch_id)

    memberships = BranchMembership.objects.filter(branch=branch).select_related('user')
    return render(request, 'pos/branches/membership_list.html', {
        'branch': branch,
        'memberships': memberships,
        'role_choices': BranchMembership.ROLE_CHOICES,
    })


# ── Price Overrides ───────────────────────────────────────────────────────────

@login_required
@business_required
def price_override_list(request, branch_id=None, *args, **kwargs):
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    can_edit = _require_owner_admin(request) or BranchMembership.objects.filter(
        user=request.user, branch=branch, is_active=True, role='manager'
    ).exists()

    if not can_edit:
        messages.error(request, 'Permission denied.')
        return redirect('branch_list')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            product_id = request.POST.get('product')
            price = request.POST.get('price', '0')
            try:
                from decimal import Decimal
                product = Product.objects.get(pk=product_id, business=request.business)
                BranchPriceOverride.objects.update_or_create(
                    branch=branch, product=product,
                    defaults={'price': Decimal(price)},
                )
                messages.success(request, f'Price override set for {product.name}.')
            except Exception as e:
                messages.error(request, str(e))
        elif action == 'delete':
            override_id = request.POST.get('override_id')
            BranchPriceOverride.objects.filter(pk=override_id, branch=branch).delete()
            messages.success(request, 'Price override removed.')
        return redirect('price_override_list', branch_id=branch_id)

    overrides = BranchPriceOverride.objects.filter(branch=branch).select_related('product')
    products = Product.objects.filter(business=request.business, is_active=True).order_by('name')
    return render(request, 'pos/branches/price_override_list.html', {
        'branch': branch,
        'overrides': overrides,
        'products': products,
    })


# ── Consolidated Report ───────────────────────────────────────────────────────

@login_required
@business_required
def consolidated_report(request, *args, **kwargs):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard')

    today = timezone.now().date()
    date_from_str = request.GET.get('date_from', str(today.replace(day=1)))
    date_to_str = request.GET.get('date_to', str(today))
    branch_ids_raw = request.GET.getlist('branch_ids')

    try:
        from datetime import datetime
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
    except ValueError:
        date_from = today.replace(day=1)
        date_to = today

    branch_ids = [int(b) for b in branch_ids_raw if b.isdigit()] or None

    sales = ConsolidatedReportService.sales_summary(
        request.business, date_from, date_to, branch_ids
    )
    stock = ConsolidatedReportService.stock_valuation(request.business, branch_ids)
    top_products = ConsolidatedReportService.top_products(
        request.business, date_from, date_to, branch_ids
    )
    all_branches = Branch.objects.filter(business=request.business, is_active=True)

    return render(request, 'pos/branches/consolidated_report.html', {
        'sales': sales,
        'stock': stock,
        'top_products': top_products,
        'all_branches': all_branches,
        'date_from': date_from_str,
        'date_to': date_to_str,
        'selected_branch_ids': branch_ids_raw,
    })


# ── Branch switcher (AJAX & Direct Redirect) ──────────────────────────────────

@login_required
@business_required
def set_active_branch(request, *args, **kwargs):
    """POST: set session['active_branch_id']. branch_id='' clears it (HQ mode)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    branch_id = request.POST.get('branch_id', '').strip()
    if branch_id and branch_id not in ('all', 'hq', '0'):
        try:
            branch = Branch.objects.get(
                pk=branch_id, business=request.business, is_active=True
            )
            # Verify access
            if not is_owner_or_admin(request.user, request.business):
                if not BranchMembership.objects.filter(
                    user=request.user, branch=branch, is_active=True
                ).exists():
                    return JsonResponse({'error': 'Access denied'}, status=403)
            request.session['active_branch_id'] = branch.pk
            return JsonResponse({'branch_id': branch.pk, 'branch_name': branch.name})
        except Branch.DoesNotExist:
            return JsonResponse({'error': 'Branch not found'}, status=404)
    else:
        request.session['active_branch_id'] = 'hq'
        return JsonResponse({'branch_id': None, 'branch_name': 'All Branches (HQ)'})


@login_required
@business_required
def switch_active_branch(request, branch_id=None, *args, **kwargs):
    """
    1-click branch switch from header dropdown.
    branch_id=0 or '0' means switch to HQ / All Branches.
    Redirects back to previous page or dashboard.
    """
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/dashboard/'
    
    if not branch_id or str(branch_id) in ('0', 'hq', 'all'):
        request.session['active_branch_id'] = 'hq'
        messages.info(request, 'Switched to HQ / All Branches view.')
    else:
        try:
            branch = Branch.objects.get(
                pk=branch_id, business=request.business, is_active=True
            )
            if not is_owner_or_admin(request.user, request.business):
                if not BranchMembership.objects.filter(
                    user=request.user, branch=branch, is_active=True
                ).exists():
                    messages.error(request, 'You do not have access to this branch.')
                    return redirect(next_url)
            request.session['active_branch_id'] = branch.pk
            messages.success(request, f'Active branch set to: {branch.name}')
        except Branch.DoesNotExist:
            messages.error(request, 'Branch not found or inactive.')

    return redirect(next_url)


# ── Branch login ──────────────────────────────────────────────────────────────

def branch_login(request, branch_id=None, *args, **kwargs):
    """
    Branch-specific direct login page.
    On success, sets the active branch in session.
    """
    from django.contrib.auth import authenticate, login as auth_login
    from .models import Business, BusinessMembership

    business = getattr(request, 'business', None) or Business.objects.first()
    branch = get_object_or_404(Branch, pk=branch_id, business=business, is_active=True)

    error = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)
        if user is None:
            from django.contrib.auth.models import User as AuthUser
            try:
                u = AuthUser.objects.get(email=username)
                user = authenticate(request, username=u.username, password=password)
            except AuthUser.DoesNotExist:
                pass

        if user is None:
            error = 'Invalid username or password.'
        else:
            has_branch_access = BranchMembership.objects.filter(
                user=user, branch=branch, is_active=True
            ).exists()
            has_business_access = is_owner_or_admin(user, business)

            if not has_branch_access and not has_business_access:
                error = 'You do not have access to this branch.'
            else:
                auth_login(request, user)
                BusinessMembership.objects.get_or_create(
                    user=user, business=business,
                    defaults={'role': 'cashier', 'is_active': True},
                )
                request.session['active_branch_id'] = branch.pk
                messages.success(request, f'Logged in to {branch.name}.')
                return redirect('dashboard')

    return render(request, 'pos/branches/branch_login.html', {
        'branch': branch,
        'business': business,
        'error': error,
    })


# ============================================================================
# HQ DISTRIBUTION & REQUISITIONS VIEWS
# ============================================================================

@login_required
@business_required
def requisition_list(request, *args, **kwargs):
    """List stock requisitions, scoped by user branch unless owner/admin/HQ."""
    user_branches = get_user_branches(request.user, request.business)
    is_hq = is_owner_or_admin(request.user, request.business)

    qs = StockRequisition.objects.filter(business=request.business).select_related(
        'requesting_branch', 'requested_by', 'approved_by'
    )
    if not is_hq:
        qs = qs.filter(requesting_branch__in=user_branches)

    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    requisitions = qs.order_by('-created_at')[:100]
    return render(request, 'pos/branches/requisition_list.html', {
        'requisitions': requisitions,
        'is_hq': is_hq,
        'status_filter': status_filter,
    })


@login_required
@business_required
def requisition_create(request, *args, **kwargs):
    """Branch manager or cashier raises a stock requisition to HQ."""
    user_branches = get_user_branches(request.user, request.business)
    products = Product.objects.filter(business=request.business, is_active=True).order_by('name')

    if request.method == 'POST':
        branch_id = request.POST.get('requesting_branch')
        notes = request.POST.get('notes', '').strip()
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')

        branch = get_object_or_404(Branch, pk=branch_id, business=request.business)
        items_data = []
        for p_id, qty in zip(product_ids, quantities):
            if p_id and qty:
                try:
                    q_dec = Decimal(str(qty))
                    if q_dec > 0:
                        items_data.append({'product_id': int(p_id), 'quantity': q_dec})
                except Exception:
                    pass

        if not items_data:
            messages.error(request, 'Please add at least one item with a quantity greater than zero.')
        else:
            try:
                req = DistributionService.create_requisition(
                    business=request.business,
                    requesting_branch=branch,
                    items_data=items_data,
                    user=request.user,
                    notes=notes,
                )
                messages.success(request, f'Requisition {req.reference_number} submitted to HQ.')
                return redirect('requisition_detail', pk=req.pk)
            except Exception as e:
                messages.error(request, f'Error creating requisition: {e}')

    return render(request, 'pos/branches/requisition_form.html', {
        'user_branches': user_branches,
        'products': products,
    })


@login_required
@business_required
def requisition_detail(request, pk=None, *args, **kwargs):
    """View details of a stock requisition."""
    req = get_object_or_404(
        StockRequisition.objects.select_related('requesting_branch', 'requested_by', 'approved_by').prefetch_related('items__product'),
        pk=pk, business=request.business
    )
    is_hq = is_owner_or_admin(request.user, request.business)
    dispatches = req.dispatches.select_related('source_branch', 'destination_branch', 'dispatched_by', 'received_by').prefetch_related('items__product').all()

    return render(request, 'pos/branches/requisition_detail.html', {
        'requisition': req,
        'is_hq': is_hq,
        'dispatches': dispatches,
    })


@login_required
@business_required
def requisition_approve(request, pk=None, *args, **kwargs):
    """HQ Admin approves requisition and specifies approved quantities."""
    if not is_owner_or_admin(request.user, request.business):
        messages.error(request, 'Permission denied. Only HQ Admins can approve requisitions.')
        return redirect('requisition_list')

    req = get_object_or_404(StockRequisition, pk=pk, business=request.business)
    if request.method == 'POST':
        approved_items = {}
        for item in req.items.all():
            appr_val = request.POST.get(f'approved_qty_{item.id}')
            if appr_val is not None:
                try:
                    approved_items[item.id] = Decimal(str(appr_val))
                except Exception:
                    approved_items[item.id] = item.requested_quantity
        try:
            DistributionService.approve_requisition(req, approved_items, request.user)
            messages.success(request, f'Requisition {req.reference_number} approved.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return redirect('requisition_detail', pk=pk)


@login_required
@business_required
def requisition_reject(request, pk=None, *args, **kwargs):
    """HQ Admin rejects requisition."""
    if not is_owner_or_admin(request.user, request.business):
        messages.error(request, 'Permission denied.')
        return redirect('requisition_list')

    req = get_object_or_404(StockRequisition, pk=pk, business=request.business)
    if request.method == 'POST':
        reason = request.POST.get('rejection_reason', '').strip()
        try:
            DistributionService.reject_requisition(req, request.user, reason)
            messages.success(request, f'Requisition {req.reference_number} rejected.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return redirect('requisition_detail', pk=pk)


@login_required
@business_required
def requisition_dispatch(request, pk=None, *args, **kwargs):
    """HQ Admin dispatches approved goods to the branch."""
    if not is_owner_or_admin(request.user, request.business):
        messages.error(request, 'Permission denied.')
        return redirect('requisition_list')

    req = get_object_or_404(StockRequisition, pk=pk, business=request.business)
    if request.method == 'POST':
        items_data = []
        for item in req.items.all():
            qty_val = request.POST.get(f'dispatch_qty_{item.id}')
            if qty_val:
                try:
                    q_dec = Decimal(str(qty_val))
                    if q_dec > 0:
                        items_data.append({'item_id': item.id, 'quantity': q_dec})
                except Exception:
                    pass
        notes = request.POST.get('dispatch_notes', '').strip()
        try:
            dispatch_rec = DistributionService.dispatch(req, items_data, request.user, notes)
            messages.success(request, f'Dispatched {dispatch_rec.reference_number} to {req.requesting_branch.name}.')
            return redirect('dispatch_detail', pk=dispatch_rec.pk)
        except Exception as e:
            messages.error(request, f'Error dispatching: {e}')

    return redirect('requisition_detail', pk=pk)


# ============================================================================
# INTER-BRANCH TRANSFERS VIEWS
# ============================================================================

@login_required
@business_required
def transfer_request_list(request, *args, **kwargs):
    """List inter-branch transfer requests."""
    user_branches = get_user_branches(request.user, request.business)
    is_hq = is_owner_or_admin(request.user, request.business)

    qs = StockTransferRequest.objects.filter(business=request.business).select_related(
        'source_branch', 'destination_branch', 'requested_by', 'approved_by'
    )
    if not is_hq:
        qs = qs.filter(Q(source_branch__in=user_branches) | Q(destination_branch__in=user_branches))

    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    transfer_requests = qs.order_by('-created_at')[:100]
    return render(request, 'pos/branches/transfer_request_list.html', {
        'transfer_requests': transfer_requests,
        'is_hq': is_hq,
        'status_filter': status_filter,
    })


@login_required
@business_required
def transfer_request_create(request, *args, **kwargs):
    """Create a new inter-branch transfer request."""
    user_branches = get_user_branches(request.user, request.business)
    all_branches = Branch.objects.filter(business=request.business, is_active=True).order_by('name')
    products = Product.objects.filter(business=request.business, is_active=True).order_by('name')

    if request.method == 'POST':
        source_id = request.POST.get('source_branch')
        dest_id = request.POST.get('destination_branch')
        reason = request.POST.get('reason', '').strip()
        product_ids = request.POST.getlist('product_id[]')
        quantities = request.POST.getlist('quantity[]')

        if source_id == dest_id:
            messages.error(request, 'Source and destination branch must be different.')
        else:
            source = get_object_or_404(Branch, pk=source_id, business=request.business)
            destination = get_object_or_404(Branch, pk=dest_id, business=request.business)
            items_data = []
            for p_id, qty in zip(product_ids, quantities):
                if p_id and qty:
                    try:
                        q_dec = Decimal(str(qty))
                        if q_dec > 0:
                            items_data.append({'product_id': int(p_id), 'quantity': q_dec})
                    except Exception:
                        pass

            if not items_data:
                messages.error(request, 'Please add at least one product with quantity > 0.')
            else:
                try:
                    trf = DistributionService.create_transfer_request(
                        business=request.business,
                        source_branch=source,
                        dest_branch=destination,
                        items_data=items_data,
                        user=request.user,
                        reason=reason,
                    )
                    messages.success(request, f'Transfer request {trf.reference_number} created.')
                    return redirect('transfer_request_detail', pk=trf.pk)
                except Exception as e:
                    messages.error(request, str(e))

    return render(request, 'pos/branches/transfer_request_form.html', {
        'user_branches': user_branches,
        'all_branches': all_branches,
        'products': products,
    })


@login_required
@business_required
def transfer_request_detail(request, pk=None, *args, **kwargs):
    """View details of a transfer request."""
    trf = get_object_or_404(
        StockTransferRequest.objects.select_related('source_branch', 'destination_branch', 'requested_by', 'approved_by').prefetch_related('items__product'),
        pk=pk, business=request.business
    )
    can_approve = is_owner_or_admin(request.user, request.business) or is_branch_manager(request.user, trf.source_branch)
    dispatches = trf.dispatches.select_related('source_branch', 'destination_branch', 'dispatched_by', 'received_by').prefetch_related('items__product').all()

    return render(request, 'pos/branches/transfer_request_detail.html', {
        'transfer_request': trf,
        'can_approve': can_approve,
        'dispatches': dispatches,
    })


@login_required
@business_required
def transfer_request_approve(request, pk=None, *args, **kwargs):
    """Source branch manager or HQ admin approves transfer request."""
    trf = get_object_or_404(StockTransferRequest, pk=pk, business=request.business)
    if not (is_owner_or_admin(request.user, request.business) or is_branch_manager(request.user, trf.source_branch)):
        messages.error(request, 'Permission denied. Only source branch managers or HQ Admins can approve.')
        return redirect('transfer_request_detail', pk=pk)

    if request.method == 'POST':
        approved_items = {}
        for item in trf.items.all():
            appr_val = request.POST.get(f'approved_qty_{item.id}')
            if appr_val is not None:
                try:
                    approved_items[item.id] = Decimal(str(appr_val))
                except Exception:
                    approved_items[item.id] = item.requested_quantity
        try:
            DistributionService.approve_transfer_request(trf, approved_items, request.user)
            messages.success(request, f'Transfer request {trf.reference_number} approved.')
        except Exception as e:
            messages.error(request, str(e))

    return redirect('transfer_request_detail', pk=pk)


@login_required
@business_required
def transfer_request_reject(request, pk=None, *args, **kwargs):
    """Reject transfer request."""
    trf = get_object_or_404(StockTransferRequest, pk=pk, business=request.business)
    if not (is_owner_or_admin(request.user, request.business) or is_branch_manager(request.user, trf.source_branch)):
        messages.error(request, 'Permission denied.')
        return redirect('transfer_request_detail', pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('rejection_reason', '').strip()
        try:
            DistributionService.reject_transfer_request(trf, request.user, reason)
            messages.success(request, f'Transfer request {trf.reference_number} rejected.')
        except Exception as e:
            messages.error(request, str(e))

    return redirect('transfer_request_detail', pk=pk)


@login_required
@business_required
def transfer_request_dispatch(request, pk=None, *args, **kwargs):
    """Dispatch stock for an approved transfer request."""
    trf = get_object_or_404(StockTransferRequest, pk=pk, business=request.business)
    if not (is_owner_or_admin(request.user, request.business) or is_branch_manager(request.user, trf.source_branch)):
        messages.error(request, 'Permission denied.')
        return redirect('transfer_request_detail', pk=pk)

    if request.method == 'POST':
        items_data = []
        for item in trf.items.all():
            qty_val = request.POST.get(f'dispatch_qty_{item.id}')
            if qty_val:
                try:
                    q_dec = Decimal(str(qty_val))
                    if q_dec > 0:
                        items_data.append({'item_id': item.id, 'quantity': q_dec})
                except Exception:
                    pass
        notes = request.POST.get('dispatch_notes', '').strip()
        try:
            dispatch_rec = DistributionService.dispatch(trf, items_data, request.user, notes)
            messages.success(request, f'Dispatched {dispatch_rec.reference_number} to {trf.destination_branch.name}.')
            return redirect('dispatch_detail', pk=dispatch_rec.pk)
        except Exception as e:
            messages.error(request, f'Error dispatching: {e}')

    return redirect('transfer_request_detail', pk=pk)


# ============================================================================
# DISPATCH & RECEIPT CONFIRMATION VIEWS
# ============================================================================

@login_required
@business_required
def dispatch_list(request, *args, **kwargs):
    """List all dispatches."""
    user_branches = get_user_branches(request.user, request.business)
    is_hq = is_owner_or_admin(request.user, request.business)

    qs = Dispatch.objects.filter(business=request.business).select_related(
        'source_branch', 'destination_branch', 'dispatched_by', 'received_by'
    )
    if not is_hq:
        qs = qs.filter(Q(source_branch__in=user_branches) | Q(destination_branch__in=user_branches))

    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    dispatches = qs.order_by('-dispatched_at')[:100]
    return render(request, 'pos/branches/dispatch_list.html', {
        'dispatches': dispatches,
        'is_hq': is_hq,
        'status_filter': status_filter,
    })


@login_required
@business_required
def dispatch_detail(request, pk=None, *args, **kwargs):
    """View details of a dispatch."""
    dispatch_rec = get_object_or_404(
        Dispatch.objects.select_related('source_branch', 'destination_branch', 'dispatched_by', 'received_by').prefetch_related('items__product'),
        pk=pk, business=request.business
    )
    can_receive = (
        is_owner_or_admin(request.user, request.business)
        or is_branch_manager(request.user, dispatch_rec.destination_branch)
        or BranchMembership.objects.filter(user=request.user, branch=dispatch_rec.destination_branch, is_active=True).exists()
    )
    return render(request, 'pos/branches/dispatch_detail.html', {
        'dispatch': dispatch_rec,
        'can_receive': can_receive,
    })


@login_required
@business_required
def dispatch_receive(request, pk=None, *args, **kwargs):
    """Confirm receipt of goods at the destination branch (full or partial with discrepancy reason)."""
    dispatch_rec = get_object_or_404(Dispatch, pk=pk, business=request.business)
    if not (is_owner_or_admin(request.user, request.business) or is_branch_manager(request.user, dispatch_rec.destination_branch) or BranchMembership.objects.filter(user=request.user, branch=dispatch_rec.destination_branch, is_active=True).exists()):
        messages.error(request, 'Permission denied. Only destination branch staff can confirm receipt.')
        return redirect('dispatch_detail', pk=pk)

    if request.method == 'POST':
        received_items_data = {}
        for item in dispatch_rec.items.all():
            recv_qty_val = request.POST.get(f'recv_qty_{item.id}', item.dispatched_quantity)
            disc_reason = request.POST.get(f'disc_reason_{item.id}', '')
            try:
                recv_dec = Decimal(str(recv_qty_val))
                received_items_data[item.id] = {
                    'received_qty': recv_dec,
                    'discrepancy_reason': disc_reason,
                }
            except Exception:
                received_items_data[item.id] = {
                    'received_qty': item.dispatched_quantity,
                    'discrepancy_reason': '',
                }

        try:
            DistributionService.confirm_receipt(dispatch_rec, received_items_data, request.user)
            messages.success(request, f'Receipt confirmed for {dispatch_rec.reference_number}. Stock added to {dispatch_rec.destination_branch.name}.')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    return redirect('dispatch_detail', pk=pk)


# ============================================================================
# UNIFIED STOCK LEDGER & LOW STOCK VIEWS
# ============================================================================

@login_required
@business_required
def stock_ledger(request, *args, **kwargs):
    """
    Searchable, filterable audit log of every stock movement.
    """
    user_branches = get_user_branches(request.user, request.business)
    is_hq = is_owner_or_admin(request.user, request.business)

    qs = StockMovement.objects.filter(business=request.business).select_related(
        'branch', 'product', 'performed_by'
    )
    if not is_hq:
        qs = qs.filter(branch__in=user_branches)

    branch_id = request.GET.get('branch_id')
    if branch_id and branch_id.isdigit():
        qs = qs.filter(branch_id=int(branch_id))

    product_id = request.GET.get('product_id')
    if product_id and product_id.isdigit():
        qs = qs.filter(product_id=int(product_id))

    movement_type = request.GET.get('movement_type')
    if movement_type:
        qs = qs.filter(movement_type=movement_type)

    date_from = request.GET.get('date_from')
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)

    date_to = request.GET.get('date_to')
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    movements = qs.order_by('-created_at')[:200]
    all_products = Product.objects.filter(business=request.business, is_active=True).order_by('name')
    all_branches = user_branches if not is_hq else Branch.objects.filter(business=request.business, is_active=True)

    return render(request, 'pos/branches/stock_ledger.html', {
        'movements': movements,
        'all_branches': all_branches,
        'all_products': all_products,
        'selected_branch': branch_id,
        'selected_product': product_id,
        'selected_movement_type': movement_type,
        'date_from': date_from,
        'date_to': date_to,
        'movement_types': StockMovement.MOVEMENT_TYPE_CHOICES,
    })


@login_required
@business_required
def branch_low_stock(request, branch_id=None, *args, **kwargs):
    """View low stock items for a specific branch derived from BranchStock.reorder_level."""
    if branch_id:
        branch = get_object_or_404(Branch, pk=branch_id, business=request.business)
    else:
        branch = getattr(request, 'branch', None) or Branch.objects.filter(business=request.business, is_hq=True).first() or Branch.objects.filter(business=request.business).first()

    low_stocks = BranchStockService.get_low_stock_for_branch(branch) if branch else []
    all_branches = get_user_branches(request.user, request.business)

    return render(request, 'pos/branches/branch_low_stock.html', {
        'branch': branch,
        'low_stocks': low_stocks,
        'all_branches': all_branches,
    })

