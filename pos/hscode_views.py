"""
HS Code management views — list, create, edit, delete, AJAX search.
All views accept slug= because they live under /b/<slug>/ URL group.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST

from .models import HSCode
from .decorators import business_required


@login_required
@business_required
def hscode_list(request, slug=None):
    q = request.GET.get('q', '').strip()
    chapter = request.GET.get('chapter', '').strip()

    codes = HSCode.objects.annotate(product_count=Count('products'))

    if q:
        codes = codes.filter(
            Q(code__icontains=q) | Q(description__icontains=q) | Q(notes__icontains=q)
        )
    if chapter:
        codes = codes.filter(chapter=chapter)

    chapters = HSCode.objects.values_list('chapter', flat=True).distinct().order_by('chapter')

    paginator = Paginator(codes, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'pos/hscodes/list.html', {
        'page_obj': page_obj,
        'q': q,
        'chapter': chapter,
        'chapters': chapters,
        'total': codes.count(),
    })


@login_required
@business_required
def hscode_create(request, slug=None):
    if not request.user.is_superuser:
        messages.error(request, 'Only platform administrators can add HS codes.')
        return redirect('hscode_list', slug=slug)

    if request.method == 'POST':
        ok, obj_or_err = _save_from_post(None, request.POST)
        if ok:
            messages.success(request, f'HS Code {obj_or_err.code} added.')
            return redirect('hscode_list', slug=slug)
        messages.error(request, obj_or_err)

    return render(request, 'pos/hscodes/form.html', {
        'hscode': None,
        'hscode_units': HSCode.UNIT_CHOICES,
    })


@login_required
@business_required
def hscode_edit(request, slug=None, pk=None):
    if not request.user.is_superuser:
        messages.error(request, 'Only platform administrators can edit HS codes.')
        return redirect('hscode_list', slug=slug)

    hscode = get_object_or_404(HSCode, pk=pk)

    if request.method == 'POST':
        ok, obj_or_err = _save_from_post(hscode, request.POST)
        if ok:
            messages.success(request, f'HS Code {obj_or_err.code} updated.')
            return redirect('hscode_list', slug=slug)
        messages.error(request, obj_or_err)

    return render(request, 'pos/hscodes/form.html', {
        'hscode': hscode,
        'hscode_units': HSCode.UNIT_CHOICES,
    })


@login_required
@business_required
@require_POST
def hscode_delete(request, slug=None, pk=None):
    if not request.user.is_superuser:
        messages.error(request, 'Only platform administrators can delete HS codes.')
        return redirect('hscode_list', slug=slug)

    hscode = get_object_or_404(HSCode, pk=pk)
    code = hscode.code
    hscode.delete()
    messages.success(request, f'HS Code {code} deleted.')
    return redirect('hscode_list', slug=slug)


def hscode_search(request, slug=None):
    """AJAX: GET ?q=<query> — returns matching HS codes for autocomplete."""
    q = request.GET.get('q', '').strip()
    limit = min(int(request.GET.get('limit', 20)), 50)

    if not q or len(q) < 2:
        return JsonResponse({'results': []})

    codes = HSCode.objects.filter(
        Q(code__icontains=q) | Q(description__icontains=q),
        is_active=True,
    ).values('id', 'code', 'description', 'vat_rate', 'excise_rate', 'import_duty', 'is_excisable')[:limit]

    return JsonResponse({'results': list(codes)})


def hscode_detail(request, slug=None, pk=None):
    """AJAX: return JSON detail for a single HS code."""
    hscode = get_object_or_404(HSCode, pk=pk)
    return JsonResponse({
        'id': hscode.pk,
        'code': hscode.display_code,
        'description': hscode.description,
        'vat_rate': str(hscode.vat_rate),
        'excise_rate': str(hscode.excise_rate),
        'is_excisable': hscode.is_excisable,
        'unit': hscode.unit,
    })


# ── Helper ────────────────────────────────────────────────────────────────────

def _save_from_post(instance, post):
    from decimal import Decimal, InvalidOperation

    code = post.get('code', '').strip().replace(' ', '')
    if not code:
        return False, 'HS Code is required.'
    description = post.get('description', '').strip()
    if not description:
        return False, 'Description is required.'

    qs = HSCode.objects.filter(code=code)
    if instance:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        return False, f'HS Code "{code}" already exists.'

    try:
        vat_rate    = Decimal(post.get('vat_rate', '16') or '16')
        excise_rate = Decimal(post.get('excise_rate', '0') or '0')
        import_duty = Decimal(post.get('import_duty', '0') or '0')
    except InvalidOperation:
        return False, 'Invalid rate value.'

    obj = instance or HSCode()
    obj.code        = code
    obj.description = description
    obj.vat_rate    = vat_rate
    obj.excise_rate = excise_rate
    obj.import_duty = import_duty
    obj.is_excisable= post.get('is_excisable') == 'on'
    obj.unit        = post.get('unit', '')
    obj.notes       = post.get('notes', '').strip()
    obj.is_active   = post.get('is_active', 'on') == 'on'
    obj.save()
    return True, obj
