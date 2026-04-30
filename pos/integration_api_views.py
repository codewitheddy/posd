"""
Integration API views — authenticated REST endpoints for external systems.
All tenant-scoped endpoints live under /api/v1/{slug}/.
"""
import csv
import hashlib
import hmac
import json
import math
import secrets

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import APIKey, Business, BusinessMembership, Customer, Product, Sale


# ── Base view ─────────────────────────────────────────────────────────────────

class IntegrationBaseView(APIView):
    """
    Base class for all tenant-scoped Integration API views.
    Resolves the Business from the URL slug and enforces scoping:
      - API key auth: key.business must match the slug's business
      - JWT/session auth: user must be owner or admin of the business
    """

    def get_business(self, slug):
        business = get_object_or_404(Business, slug=slug, is_active=True)
        auth = self.request.auth

        if isinstance(auth, APIKey):
            if auth.business_id != business.id:
                raise PermissionDenied('API key is not authorised for this business.')
        else:
            # JWT or session — require owner/admin membership
            if not self.request.user or not self.request.user.is_authenticated:
                raise AuthenticationFailed('Authentication required.')
            if not self.request.user.is_superuser:
                if not BusinessMembership.objects.filter(
                    user=self.request.user,
                    business=business,
                    is_active=True,
                    role__in=['owner', 'admin'],
                ).exists():
                    raise PermissionDenied('You do not have permission to access this business.')

        return business


# ── Sales JSON endpoint ───────────────────────────────────────────────────────

class SalesListView(IntegrationBaseView):
    """GET /api/v1/{slug}/sales/ — paginated JSON sales export."""

    def get(self, request, slug):
        business = self.get_business(slug)

        qs = Sale.objects.filter(business=business).select_related(
            'customer', 'cashier'
        ).prefetch_related(
            'items__product', 'payments__payment_method'
        ).order_by('date')

        start = request.GET.get('start_date')
        end = request.GET.get('end_date')
        if start:
            qs = qs.filter(date__date__gte=start)
        if end:
            qs = qs.filter(date__date__lte=end)

        # Pagination
        try:
            page = max(1, int(request.GET.get('page', 1)))
        except (ValueError, TypeError):
            page = 1
        try:
            page_size = min(500, max(1, int(request.GET.get('page_size', 100))))
        except (ValueError, TypeError):
            page_size = 100

        total = qs.count()
        total_pages = max(1, math.ceil(total / page_size))
        offset = (page - 1) * page_size
        sales = qs[offset: offset + page_size]

        base_url = request.build_absolute_uri(request.path)
        query_parts = []
        if start:
            query_parts.append(f'start_date={start}')
        if end:
            query_parts.append(f'end_date={end}')
        query_parts.append(f'page_size={page_size}')

        def page_url(p):
            parts = query_parts + [f'page={p}']
            return f"{base_url}?{'&'.join(parts)}"

        results = []
        for sale in sales:
            results.append({
                'id': sale.id,
                'sale_number': sale.invoice_number,
                'date': sale.date.isoformat() if sale.date else None,
                'customer': sale.customer.name if sale.customer else None,
                'cashier': sale.cashier.username if sale.cashier else None,
                'subtotal': str(sale.subtotal),
                'vat': str(sale.vat_amount),
                'discount': str(sale.discount_amount),
                'total': str(sale.total),
                'payments': [
                    {
                        'method': p.payment_method.name if p.payment_method else None,
                        'amount': str(p.amount),
                        'reference': p.reference_number or '',
                    }
                    for p in sale.payments.all()
                ],
                'items': [
                    {
                        'product': i.product.name if i.product else None,
                        'product_code': i.product.product_code if i.product else None,
                        'quantity': str(i.quantity),
                        'unit_price': str(i.unit_price),
                        'subtotal': str(i.subtotal),
                    }
                    for i in sale.items.all()
                ],
            })

        return Response({
            'count': total,
            'next': page_url(page + 1) if page < total_pages else None,
            'previous': page_url(page - 1) if page > 1 else None,
            'results': results,
        })


# ── CSV export endpoints ──────────────────────────────────────────────────────

class SalesCSVView(IntegrationBaseView):
    """GET /api/v1/{slug}/sales/csv/ — CSV sales export."""

    def get(self, request, slug):
        business = self.get_business(slug)

        qs = Sale.objects.filter(business=business).select_related(
            'customer', 'cashier'
        ).prefetch_related('items__product', 'payments__payment_method').order_by('date')

        start = request.GET.get('start_date')
        end = request.GET.get('end_date')
        if start:
            qs = qs.filter(date__date__gte=start)
        if end:
            qs = qs.filter(date__date__lte=end)

        response = HttpResponse(content_type='text/csv')
        fname = f"{business.slug}_sales_{timezone.now().strftime('%Y%m%d')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{fname}"'

        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Invoice No', 'Customer', 'Cashier',
            'Subtotal', 'VAT', 'Discount', 'Total',
            'Payment Method', 'Payment Reference', 'Notes',
        ])
        for sale in qs:
            payment_names = ', '.join(
                p.payment_method.name for p in sale.payments.all() if p.payment_method
            )
            payment_refs = ', '.join(p.reference_number or '' for p in sale.payments.all())
            writer.writerow([
                sale.date.strftime('%Y-%m-%d %H:%M') if sale.date else '',
                sale.invoice_number,
                sale.customer.name if sale.customer else '',
                sale.cashier.get_full_name() or sale.cashier.username if sale.cashier else '',
                sale.subtotal,
                sale.vat_amount,
                sale.discount_amount,
                sale.total,
                payment_names,
                payment_refs,
                '',
            ])
        return response


class ProductsCSVView(IntegrationBaseView):
    """GET /api/v1/{slug}/products/csv/ — CSV product catalogue export."""

    def get(self, request, slug):
        business = self.get_business(slug)
        products = Product.objects.filter(business=business).select_related(
            'category', 'unit'
        ).order_by('name')

        response = HttpResponse(content_type='text/csv')
        fname = f"{business.slug}_products_{timezone.now().strftime('%Y%m%d')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{fname}"'

        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Product Code', 'Barcode', 'Category',
            'Unit Price', 'Cost Price', 'Stock Qty', 'Low Stock Threshold',
            'Unit', 'Is Active',
        ])
        for p in products:
            writer.writerow([
                p.name,
                p.product_code or '',
                p.barcode or '',
                p.category.name if p.category else '',
                p.unit_price,
                p.cost_price or '',
                p.stock_quantity,
                p.low_stock_threshold,
                p.unit.abbreviation if p.unit else '',
                'Yes' if p.is_active else 'No',
            ])
        return response


class CustomersCSVView(IntegrationBaseView):
    """GET /api/v1/{slug}/customers/csv/ — CSV customer list export."""

    def get(self, request, slug):
        business = self.get_business(slug)
        customers = Customer.objects.filter(business=business).order_by('name')

        response = HttpResponse(content_type='text/csv')
        fname = f"{business.slug}_customers_{timezone.now().strftime('%Y%m%d')}.csv"
        response['Content-Disposition'] = f'attachment; filename="{fname}"'

        writer = csv.writer(response)
        writer.writerow([
            'Name', 'Email', 'Phone', 'Tier', 'Loyalty Points',
            'Total Purchases', 'Created',
        ])
        for c in customers:
            writer.writerow([
                c.name,
                c.email or '',
                c.phone or '',
                c.tier,
                c.loyalty_points,
                c.total_purchases,
                c.created_at.strftime('%Y-%m-%d') if c.created_at else '',
            ])
        return response


# ── Signature verification ────────────────────────────────────────────────────

class VerifySignatureView(APIView):
    """
    POST /api/v1/verify-signature/
    No authentication required — developer utility endpoint.
    Body: {"secret": "...", "signature": "sha256=...", "payload": "..."}
    Returns: {"valid": true/false}
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        try:
            secret = request.data.get('secret', '')
            signature = request.data.get('signature', '')
            payload = request.data.get('payload', '')

            if not all([secret, signature, payload]):
                return Response({'valid': False})

            if isinstance(payload, dict):
                payload = json.dumps(payload, default=str)

            expected = 'sha256=' + hmac.new(
                secret.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()
            valid = hmac.compare_digest(expected, signature)
            return Response({'valid': valid})
        except Exception:
            return Response({'valid': False})


# ── API Key management ────────────────────────────────────────────────────────

class APIKeyListCreateView(IntegrationBaseView):
    """
    GET  /api/v1/{slug}/api-keys/ — list active API keys (name, dates, id)
    POST /api/v1/{slug}/api-keys/ — create a new API key (returns token once)
    """

    def get(self, request, slug):
        business = self.get_business(slug)
        keys = APIKey.objects.filter(business=business, is_active=True).values(
            'id', 'name', 'created_at', 'last_used_at'
        )
        return Response({'api_keys': list(keys)})

    def post(self, request, slug):
        business = self.get_business(slug)

        # Enforce max 10 active keys
        active_count = APIKey.objects.filter(business=business, is_active=True).count()
        if active_count >= 10:
            return Response(
                {'error': 'Maximum of 10 active API keys per business.'},
                status=400,
            )

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': 'A name is required for the API key.'}, status=400)

        token = secrets.token_hex(32)  # 64-char hex
        api_key = APIKey.objects.create(
            key=token,
            name=name,
            business=business,
            created_by=request.user if request.user and request.user.is_authenticated else None,
        )
        return Response({
            'id': api_key.id,
            'name': api_key.name,
            'key': token,  # Shown once — never returned again
            'created_at': api_key.created_at,
            'message': 'Store this key securely. It will not be shown again.',
        }, status=201)


class APIKeyRevokeView(IntegrationBaseView):
    """DELETE /api/v1/{slug}/api-keys/{pk}/ — revoke an API key."""

    def delete(self, request, slug, pk):
        business = self.get_business(slug)
        try:
            api_key = APIKey.objects.get(pk=pk, business=business)
        except APIKey.DoesNotExist:
            return Response({'error': 'API key not found.'}, status=404)

        api_key.is_active = False
        api_key.save(update_fields=['is_active'])
        return Response({'message': f'API key "{api_key.name}" has been revoked.'})
