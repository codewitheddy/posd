"""
VAT Code management views — custom admin dashboard views for business VAT tax codes.
Supports list, create, edit, delete, toggle-active, and default seeding.
"""
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from .models import VATCode, ActivityLog
from .decorators import business_required
from .security_utils import verify_admin_password_and_reason


def _check_vat_permission(request):
    """Check if the user has permission to manage tax settings and product configs."""
    if request.user.is_superuser:
        return True
    membership = getattr(request, 'business_membership', None)
    if membership and membership.role in ['owner', 'admin', 'manager']:
        return True
    # Fallback to user_permissions context
    return bool(request.user.is_staff)


@login_required
@business_required
def vatcode_list(request, slug=None):
    """List all VAT codes for the current business with filtering, product counts, and summary stats."""
    business = request.business
    q = request.GET.get('q', '').strip()
    rate_filter = request.GET.get('rate', '').strip()
    status_filter = request.GET.get('status', '').strip()

    codes = VATCode.objects.filter(business=business).annotate(
        product_count=Count('products')
    ).order_by('code')

    if q:
        codes = codes.filter(
            Q(code__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q)
        )

    if rate_filter:
        try:
            codes = codes.filter(vat_rate=Decimal(rate_filter))
        except Exception:
            pass

    if status_filter == 'active':
        codes = codes.filter(is_active=True)
    elif status_filter == 'inactive':
        codes = codes.filter(is_active=False)

    # Compute summary statistics
    all_codes = VATCode.objects.filter(business=business)
    total_count = all_codes.count()
    active_count = all_codes.filter(is_active=True).count()
    standard_count = all_codes.filter(vat_rate=Decimal('16.00')).count()
    zero_exempt_count = all_codes.filter(vat_rate=Decimal('0.00')).count()

    # Get distinct rates for filter dropdown
    available_rates = all_codes.values_list('vat_rate', flat=True).distinct().order_by('vat_rate')

    paginator = Paginator(codes, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    can_edit = _check_vat_permission(request)

    return render(request, 'pos/vatcodes/list.html', {
        'page_obj': page_obj,
        'q': q,
        'rate_filter': rate_filter,
        'status_filter': status_filter,
        'available_rates': available_rates,
        'total_count': total_count,
        'active_count': active_count,
        'standard_count': standard_count,
        'zero_exempt_count': zero_exempt_count,
        'can_edit': can_edit,
    })


@login_required
@business_required
def vatcode_create(request, slug=None):
    """Create a new VAT code for the current business."""
    if not _check_vat_permission(request):
        messages.error(request, 'You do not have permission to manage tax settings.')
        return redirect('vatcode_list', slug=request.business.slug)

    business = request.business

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        vat_rate_raw = request.POST.get('vat_rate', '16.00').strip()
        description = request.POST.get('description', '').strip()
        hs_code_chapter = request.POST.get('hs_code_chapter', '').strip()
        excise_rate_raw = request.POST.get('excise_rate', '0.00').strip()
        is_excisable = bool(request.POST.get('is_excisable'))
        import_duty_raw = request.POST.get('import_duty', '0.00').strip()
        is_active = bool(request.POST.get('is_active', '1') in ['1', 'true', 'on', 'True'])

        # Validation
        if not code:
            messages.error(request, 'VAT Code identifier is required (e.g., VAT-STD, VAT-ZERO).')
        elif not name:
            messages.error(request, 'VAT Code name is required.')
        elif VATCode.objects.filter(business=business, code=code).exists():
            messages.error(request, f'A VAT Code with identifier "{code}" already exists for your business.')
        else:
            try:
                vat_rate = Decimal(vat_rate_raw)
                excise_rate = Decimal(excise_rate_raw) if excise_rate_raw else Decimal('0.00')
                import_duty = Decimal(import_duty_raw) if import_duty_raw else Decimal('0.00')

                new_code = VATCode.objects.create(
                    business=business,
                    code=code,
                    name=name,
                    vat_rate=vat_rate,
                    description=description,
                    hs_code_chapter=hs_code_chapter or None,
                    excise_rate=excise_rate,
                    is_excisable=is_excisable,
                    import_duty=import_duty,
                    is_active=is_active,
                )
                messages.success(request, f'VAT Code "{new_code.code} — {new_code.name}" created successfully.')
                return redirect('vatcode_list', slug=request.business.slug)
            except Exception as e:
                messages.error(request, f'Error creating VAT Code: {str(e)}')

    return render(request, 'pos/vatcodes/form.html', {
        'vatcode': None,
        'rate_choices': VATCode.RATE_CHOICES,
    })


@login_required
@business_required
def vatcode_edit(request, slug=None, pk=None):
    """Edit an existing VAT code for the current business."""
    if not _check_vat_permission(request):
        messages.error(request, 'You do not have permission to manage tax settings.')
        return redirect('vatcode_list', slug=request.business.slug)

    vatcode = get_object_or_404(VATCode, business=request.business, pk=pk)

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        name = request.POST.get('name', '').strip()
        vat_rate_raw = request.POST.get('vat_rate', '16.00').strip()
        description = request.POST.get('description', '').strip()
        hs_code_chapter = request.POST.get('hs_code_chapter', '').strip()
        excise_rate_raw = request.POST.get('excise_rate', '0.00').strip()
        is_excisable = bool(request.POST.get('is_excisable'))
        import_duty_raw = request.POST.get('import_duty', '0.00').strip()
        is_active = bool(request.POST.get('is_active', '1') in ['1', 'true', 'on', 'True'])

        # Validation
        if not code:
            messages.error(request, 'VAT Code identifier is required.')
        elif not name:
            messages.error(request, 'VAT Code name is required.')
        elif VATCode.objects.filter(business=request.business, code=code).exclude(pk=pk).exists():
            messages.error(request, f'Another VAT Code with identifier "{code}" already exists.')
        else:
            try:
                vatcode.code = code
                vatcode.name = name
                vatcode.vat_rate = Decimal(vat_rate_raw)
                vatcode.description = description
                vatcode.hs_code_chapter = hs_code_chapter or None
                vatcode.excise_rate = Decimal(excise_rate_raw) if excise_rate_raw else Decimal('0.00')
                vatcode.is_excisable = is_excisable
                vatcode.import_duty = Decimal(import_duty_raw) if import_duty_raw else Decimal('0.00')
                vatcode.is_active = is_active
                vatcode.save()

                messages.success(request, f'VAT Code "{vatcode.code}" updated successfully.')
                return redirect('vatcode_list', slug=request.business.slug)
            except Exception as e:
                messages.error(request, f'Error updating VAT Code: {str(e)}')

    return render(request, 'pos/vatcodes/form.html', {
        'vatcode': vatcode,
        'rate_choices': VATCode.RATE_CHOICES,
    })


@login_required
@business_required
@require_POST
def vatcode_delete(request, slug=None, pk=None):
    """Delete a VAT code if not attached to products, or warn if attached."""
    if not _check_vat_permission(request):
        messages.error(request, 'You do not have permission to delete VAT codes.')
        return redirect('vatcode_list', slug=request.business.slug)

    vatcode = get_object_or_404(VATCode, business=request.business, pk=pk)
    product_count = vatcode.products.count()

    if product_count > 0:
        messages.warning(
            request,
            f'Cannot delete VAT Code "{vatcode.code}" because it is currently assigned to {product_count} product(s). '
            f'You can deactivate it instead to prevent new assignments.'
        )
        return redirect('vatcode_list', slug=request.business.slug)

    # Enforce Admin Password & Reason
    is_valid, err_msg, clean_reason = verify_admin_password_and_reason(
        request,
        action_name="VAT code deletion"
    )
    if not is_valid:
        messages.error(request, err_msg)
        return redirect('vatcode_list', slug=request.business.slug)

    code_name = f"{vatcode.code} ({vatcode.name})"
    vat_pk = vatcode.pk
    vatcode.delete()

    ActivityLog.log_activity(
        user=request.user,
        action_type='delete',
        model_name='VATCode',
        object_id=vat_pk,
        description=f'Deleted VAT Code: {code_name} | Reason: {clean_reason}',
        request=request,
        business=request.business
    )

    messages.success(request, f'VAT Code "{code_name}" was deleted successfully.')
    return redirect('vatcode_list', slug=request.business.slug)


@login_required
@business_required
@require_POST
def vatcode_toggle_active(request, slug=None, pk=None):
    """Quick action to toggle active/inactive status of a VAT code."""
    if not _check_vat_permission(request):
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    vatcode = get_object_or_404(VATCode, business=request.business, pk=pk)
    vatcode.is_active = not vatcode.is_active
    vatcode.save(update_fields=['is_active'])

    status_label = 'Active' if vatcode.is_active else 'Inactive'
    messages.success(request, f'VAT Code "{vatcode.code}" is now {status_label}.')
    return redirect('vatcode_list', slug=request.business.slug)


@login_required
@business_required
@require_POST
def vatcode_seed_defaults(request, slug=None):
    """Seed standard Kenyan VAT codes for the business if none exist."""
    if not _check_vat_permission(request):
        messages.error(request, 'Permission denied.')
        return redirect('vatcode_list', slug=request.business.slug)

    business = request.business
    defaults = [
        {'code': 'VAT-STD', 'name': 'Standard Rated (16%)', 'vat_rate': Decimal('16.00'), 'description': 'Standard VAT rate for general goods and services.'},
        {'code': 'VAT-ZERO', 'name': 'Zero Rated (0%)', 'vat_rate': Decimal('0.00'), 'description': 'Zero-rated supplies (exports, basic food items).'},
        {'code': 'VAT-EXEMPT', 'name': 'Exempt (0%)', 'vat_rate': Decimal('0.00'), 'description': 'VAT-exempt financial, educational, and medical supplies.'},
        {'code': 'VAT-RED', 'name': 'Reduced Rate (8%)', 'vat_rate': Decimal('8.00'), 'description': 'Reduced rate for specific qualifying supplies (petroleum, etc.).'},
    ]

    created_count = 0
    for item in defaults:
        if not VATCode.objects.filter(business=business, code=item['code']).exists():
            VATCode.objects.create(
                business=business,
                code=item['code'],
                name=item['name'],
                vat_rate=item['vat_rate'],
                description=item['description'],
                is_active=True,
            )
            created_count += 1

    if created_count > 0:
        messages.success(request, f'Successfully seeded {created_count} standard VAT code(s) for {business.name}.')
    else:
        messages.info(request, 'Standard VAT codes already exist for your business.')

    return redirect('vatcode_list', slug=request.business.slug)
