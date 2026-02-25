# Sync API Views for Offline Data Synchronization
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.utils import timezone
import json
import logging

# Use model_imports to prevent import errors
from .model_imports import (
    Sale, SaleItem, SalePayment,
    Product, Customer, PaymentMethod
)
from .decorators import business_required

logger = logging.getLogger(__name__)


@login_required
@business_required
@require_http_methods(["POST"])
def sync_sale(request, slug):
    """
    Sync a single offline sale to the server
    
    Expected JSON payload:
    {
        "temp_id": "temp_1234567890_abc123",
        "sale_data": {
            "customer_id": 123,
            "items": [...],
            "payments": [...],
            "total": 1000.00,
            "timestamp": 1234567890
        }
    }
    """
    try:
        data = json.loads(request.body)
        temp_id = data.get('temp_id')
        sale_data = data.get('sale_data', {})
        
        if not temp_id or not sale_data:
            return JsonResponse({
                'success': False,
                'message': 'Missing required data'
            }, status=400)
        
        # Check for duplicate (already synced)
        existing_sale = Sale.objects.filter(
            business=request.business,
            cashier=request.user,
            total=sale_data.get('total'),
            date__gte=timezone.now() - timezone.timedelta(hours=24)
        ).first()
        
        if existing_sale:
            logger.warning(f"Possible duplicate sale detected: {temp_id}")
            return JsonResponse({
                'success': True,
                'sale_id': existing_sale.id,
                'message': 'Sale already exists (possible duplicate)',
                'duplicate': True
            })
        
        # Create sale in transaction
        with transaction.atomic():
            # Get customer if provided
            customer = None
            if sale_data.get('customer_id'):
                try:
                    customer = Customer.objects.get(
                        id=sale_data['customer_id'],
                        business=request.business
                    )
                except Customer.DoesNotExist:
                    pass
            
            # Create sale
            sale = Sale.objects.create(
                business=request.business,
                cashier=request.user,
                customer=customer,
                subtotal=sale_data.get('subtotal', 0),
                tax=sale_data.get('tax', 0),
                discount=sale_data.get('discount', 0),
                total=sale_data.get('total', 0),
                notes=f"Synced from offline (temp_id: {temp_id})"
            )
            
            # Create sale items
            for item_data in sale_data.get('items', []):
                try:
                    product = Product.objects.get(
                        id=item_data['product_id'],
                        business=request.business
                    )
                    
                    SaleItem.objects.create(
                        sale=sale,
                        product=product,
                        quantity=item_data['quantity'],
                        price=item_data['price'],
                        tax=item_data.get('tax', 0),
                        discount=item_data.get('discount', 0),
                        subtotal=item_data.get('subtotal', 0)
                    )
                    
                    # Update stock
                    if product.track_stock:
                        product.stock_quantity -= item_data['quantity']
                        product.save()
                        
                except Product.DoesNotExist:
                    logger.error(f"Product not found: {item_data['product_id']}")
                    continue
            
            # Create payments
            for payment_data in sale_data.get('payments', []):
                try:
                    # Get payment method
                    payment_method = PaymentMethod.objects.filter(
                        business=request.business,
                        code=payment_data.get('method', 'cash')
                    ).first()
                    
                    if not payment_method:
                        payment_method = PaymentMethod.objects.filter(
                            business=request.business,
                            code='cash'
                        ).first()
                    
                    if payment_method:
                        SalePayment.objects.create(
                            business=request.business,
                            sale=sale,
                            payment_method=payment_method,
                            amount=payment_data['amount'],
                            reference=payment_data.get('reference', '')
                        )
                except Exception as e:
                    logger.error(f"Error creating payment: {e}")
                    continue
            
            logger.info(f"Sale synced successfully: {temp_id} → {sale.id}")
            
            return JsonResponse({
                'success': True,
                'sale_id': sale.id,
                'invoice_number': sale.invoice_number,
                'message': 'Sale synced successfully'
            })
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error syncing sale: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)


@login_required
@business_required
@require_http_methods(["GET"])
def sync_status(request, slug):
    """
    Get sync status and statistics
    """
    try:
        # Get recent sales count
        recent_sales = Sale.objects.filter(
            business=request.business,
            cashier=request.user,
            date__gte=timezone.now() - timezone.timedelta(hours=24)
        ).count()
        
        return JsonResponse({
            'success': True,
            'status': {
                'recent_sales_24h': recent_sales,
                'server_time': timezone.now().isoformat(),
                'online': True
            }
        })
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=500)
