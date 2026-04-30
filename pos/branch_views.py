"""
Branch management views for Marid POS multi-branch feature.
"""
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
    StockTransfer, Product,
)
from .branch_services import (
    BranchStockService, StockTransferService, ConsolidatedReportService,
    is_owner_or_admin, get_user_branches,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_owner_admin(request):
    return is_owner_or_admin(request.user, request.business)


# ── Branch CRUD ───────────────────────────────────────────────────────────────

@login_required
@business_required
def branch_list(request, slug=None):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        address = request.POST.get('address', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()

        if not name or not address:
            messages.error(request, 'Branch name and address are required.')
        else:
            # Enforce plan branch limit
            limit = getattr(settings, 'BRANCH_LIMITS', {}).get(
                request.business.subscription_plan, 1
            )
            current = Branch.objects.filter(business=request.business, is_active=True).count()
            if current >= limit:
                messages.error(
                    request,
                    f'Your plan allows a maximum of {limit} active branch(es). '
                    'Upgrade to add more.'
                )
            else:
                try:
                    Branch.objects.create(
                        business=request.business,
                        name=name, address=address,
                        phone=phone, email=email,
                    )
                    messages.success(request, f'Branch "{name}" created.')
                except Exception as e:
                    if 'UNIQUE' in str(e).upper():
                        messages.error(request, f'A branch named "{name}" already exists.')
                    else:
                        messages.error(request, f'Error creating branch: {e}')
        return redirect('branch_list', slug=slug)

    branches = Branch.objects.filter(business=request.business).order_by('name')
    return render(request, 'pos/branches/branch_list.html', {
        'branches': branches,
        'branch_limit': getattr(settings, 'BRANCH_LIMITS', {}).get(
            request.business.subscription_plan, 1
        ),
    })


@login_required
@business_required
def branch_detail(request, slug=None, branch_id=None):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('branch_list', slug=slug)

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
        return redirect('branch_detail', slug=slug, branch_id=branch_id)

    memberships = BranchMembership.objects.filter(branch=branch).select_related('user')
    return render(request, 'pos/branches/branch_detail.html', {
        'branch': branch,
        'memberships': memberships,
    })


# ── Branch Stock ──────────────────────────────────────────────────────────────

@login_required
@business_required
def branch_stock(request, slug=None, branch_id=None):
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    # Check access
    if not _require_owner_admin(request):
        if not BranchMembership.objects.filter(
            user=request.user, branch=branch, is_active=True
        ).exists():
            messages.error(request, 'Permission denied.')
            return redirect('branch_list', slug=slug)

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
def transfer_list(request, slug=None, branch_id=None):
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    if not _require_owner_admin(request):
        if not BranchMembership.objects.filter(
            user=request.user, branch=branch, is_active=True,
            role__in=['manager', 'stock_manager'],
        ).exists():
            messages.error(request, 'Permission denied.')
            return redirect('branch_list', slug=slug)

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
def transfer_create(request, slug=None, branch_id=None):
    from django.db.models import Q
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    if not _require_owner_admin(request):
        if not BranchMembership.objects.filter(
            user=request.user, branch=branch, is_active=True,
            role__in=['manager', 'stock_manager'],
        ).exists():
            messages.error(request, 'Permission denied.')
            return redirect('branch_list', slug=slug)

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

        return redirect('transfer_list', slug=slug, branch_id=branch_id)

    products = Product.objects.filter(business=request.business, is_active=True).order_by('name')
    return render(request, 'pos/branches/transfer_form.html', {
        'branch': branch,
        'other_branches': other_branches,
        'products': products,
    })


@login_required
@business_required
def business_transfer_list(request, slug=None):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)

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
def branch_membership_list(request, slug=None, branch_id=None):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('branch_list', slug=slug)

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
        return redirect('branch_membership_list', slug=slug, branch_id=branch_id)

    memberships = BranchMembership.objects.filter(branch=branch).select_related('user')
    return render(request, 'pos/branches/membership_list.html', {
        'branch': branch,
        'memberships': memberships,
        'role_choices': BranchMembership.ROLE_CHOICES,
    })


# ── Price Overrides ───────────────────────────────────────────────────────────

@login_required
@business_required
def price_override_list(request, slug=None, branch_id=None):
    branch = get_object_or_404(Branch, pk=branch_id, business=request.business)

    can_edit = _require_owner_admin(request) or BranchMembership.objects.filter(
        user=request.user, branch=branch, is_active=True, role='manager'
    ).exists()

    if not can_edit:
        messages.error(request, 'Permission denied.')
        return redirect('branch_list', slug=slug)

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
        return redirect('price_override_list', slug=slug, branch_id=branch_id)

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
def consolidated_report(request, slug=None):
    if not _require_owner_admin(request):
        messages.error(request, 'Permission denied.')
        return redirect('dashboard', slug=slug)

    from datetime import date, timedelta
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


# ── Branch switcher (AJAX) ────────────────────────────────────────────────────

@login_required
@business_required
def set_active_branch(request, slug=None):
    """POST: set session['active_branch_id']. branch_id='' clears it (HQ mode)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    branch_id = request.POST.get('branch_id', '').strip()
    if branch_id:
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
        request.session.pop('active_branch_id', None)
        return JsonResponse({'branch_id': None, 'branch_name': 'HQ'})


# ── Branch login ──────────────────────────────────────────────────────────────

def branch_login(request, slug=None, branch_id=None):
    """
    Branch-specific login page.
    Shown when a non-authenticated user (or a different user) wants to
    operate a specific branch. On success, sets the active branch in session.
    """
    from django.contrib.auth import authenticate, login as auth_login
    from .models import Business, BusinessMembership

    business = get_object_or_404(Business, slug=slug, is_active=True)
    branch = get_object_or_404(Branch, pk=branch_id, business=business, is_active=True)

    error = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)
        if user is None:
            # Try email
            from django.contrib.auth.models import User as AuthUser
            try:
                u = AuthUser.objects.get(email=username)
                user = authenticate(request, username=u.username, password=password)
            except AuthUser.DoesNotExist:
                pass

        if user is None:
            error = 'Invalid username or password.'
        else:
            # Check user has access to this branch
            has_branch_access = BranchMembership.objects.filter(
                user=user, branch=branch, is_active=True
            ).exists()
            # Owners/admins of the business also have access
            has_business_access = is_owner_or_admin(user, business)

            if not has_branch_access and not has_business_access:
                error = 'You do not have access to this branch.'
            else:
                auth_login(request, user)
                # Ensure business membership exists
                BusinessMembership.objects.get_or_create(
                    user=user, business=business,
                    defaults={'role': 'cashier', 'is_active': True},
                )
                # Set active branch in session
                request.session['active_branch_id'] = branch.pk
                messages.success(request, f'Logged in to {branch.name}.')
                return redirect('dashboard', slug=slug)

    return render(request, 'pos/branches/branch_login.html', {
        'branch': branch,
        'business': business,
        'error': error,
    })
