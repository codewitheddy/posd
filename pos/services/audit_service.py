"""
Audit logging service for comprehensive activity tracking.

This module provides centralized audit logging for all critical operations
with complete context capture including request details, execution time,
and operation outcomes.
"""

import logging
import time
from typing import Dict, Any, Optional
from uuid import UUID, uuid4
from django.http import HttpRequest
from django.contrib.auth.models import User
from pos.models import ActivityLog, Business, Sale, Purchase

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Centralized service for creating comprehensive audit log entries.
    
    Provides methods for logging all critical operations with complete context
    including user, business, request details, and execution metrics.
    """
    
    @staticmethod
    def extract_request_context(request: Optional[HttpRequest]) -> tuple:
        """
        Extract IP address and user agent from HTTP request.
        
        Args:
            request: Django HttpRequest object
            
        Returns:
            Tuple of (ip_address, user_agent)
        """
        if not request:
            return (None, '')
        
        # Extract IP address (handle proxies)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0].strip()
        else:
            ip_address = request.META.get('REMOTE_ADDR', '')
        
        # Extract user agent
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        return (ip_address, user_agent)
    
    def log_operation(
        self,
        operation_type: str,
        entity_type: str,
        entity_id: str,
        user: User,
        business: Business,
        status: str = 'success',
        description: str = '',
        request_data: Optional[Dict] = None,
        response_data: Optional[Dict] = None,
        error_details: Optional[Dict] = None,
        request: Optional[HttpRequest] = None,
        correlation_id: Optional[UUID] = None,
        execution_time_ms: Optional[int] = None
    ) -> ActivityLog:
        """
        Create comprehensive audit log entry.
        
        Args:
            operation_type: Type of operation (e.g., 'sale_completion', 'purchase_receiving')
            entity_type: Type of entity (e.g., 'Sale', 'Purchase', 'Product')
            entity_id: ID of the entity
            user: User who performed the operation
            business: Business context
            status: Operation status ('success', 'failure', 'rollback')
            description: Human-readable description
            request_data: Request data (will be stored as JSON)
            response_data: Response data (will be stored as JSON)
            error_details: Error details if operation failed
            request: HTTP request object for extracting IP and user agent
            correlation_id: UUID for correlating related operations
            execution_time_ms: Execution time in milliseconds
            
        Returns:
            Created ActivityLog instance
            
        Example:
            audit_logger = AuditLogger()
            audit_logger.log_operation(
                operation_type='sale_completion',
                entity_type='Sale',
                entity_id=str(sale.id),
                user=cashier,
                business=business,
                status='success',
                description=f'Completed sale {sale.invoice_number}',
                request_data={'items': [...], 'payments': [...]},
                response_data={'sale_id': sale.id, 'total': float(sale.total)},
                request=request,
                execution_time_ms=150
            )
        """
        # Extract request context
        ip_address, user_agent = self.extract_request_context(request)
        
        # Generate correlation ID if not provided
        if correlation_id is None:
            correlation_id = uuid4()
        
        # Create audit log entry
        try:
            activity_log = ActivityLog.objects.create(
                business=business,
                user=user,
                action_type=operation_type[:20],  # Truncate to fit existing field
                description=description or f"{operation_type} on {entity_type} {entity_id}",
                model_name=entity_type,
                object_id=int(entity_id) if entity_id.isdigit() else None,
                operation_type=operation_type,
                entity_type=entity_type,
                entity_id=entity_id,
                status=status,
                correlation_id=correlation_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_data=request_data,
                response_data=response_data,
                error_details=error_details,
                execution_time_ms=execution_time_ms
            )
            
            logger.debug(
                f"Created audit log: {operation_type} - {entity_type} {entity_id} - {status}"
            )
            
            return activity_log
            
        except Exception as e:
            # Log error but don't fail the operation
            logger.error(f"Failed to create audit log: {str(e)}", exc_info=True)
            raise
    
    def log_sale_completion(
        self,
        sale: Sale,
        user: User,
        status: str,
        execution_time_ms: int,
        request: Optional[HttpRequest] = None,
        error_details: Optional[Dict] = None
    ) -> ActivityLog:
        """
        Log sale completion with complete sale details.
        
        Args:
            sale: Sale instance
            user: User who completed the sale
            status: Operation status ('success', 'failure', 'rollback')
            execution_time_ms: Execution time in milliseconds
            request: HTTP request object
            error_details: Error details if operation failed
            
        Returns:
            Created ActivityLog instance
        """
        # Build request data with sale details
        request_data = {
            'invoice_number': sale.invoice_number,
            'customer_id': sale.customer.id if sale.customer else None,
            'customer_name': sale.customer.name if sale.customer else None,
            'items': [
                {
                    'product_id': item.product.id,
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                    'total_price': float(item.total_price)
                }
                for item in sale.items.all()
            ],
            'subtotal': float(sale.subtotal),
            'vat_amount': float(sale.vat_amount),
            'discount_amount': float(sale.discount_amount),
            'total': float(sale.total),
            'amount_paid': float(sale.amount_paid),
            'change_given': float(sale.change_given)
        }
        
        # Build response data
        response_data = {
            'sale_id': sale.id,
            'invoice_number': sale.invoice_number,
            'total': float(sale.total),
            'status': status
        }
        
        description = f"Sale {sale.invoice_number} - Total: KES {sale.total}"
        if status == 'failure':
            description += " (FAILED)"
        elif status == 'rollback':
            description += " (ROLLED BACK)"
        
        return self.log_operation(
            operation_type='sale_completion',
            entity_type='Sale',
            entity_id=str(sale.id),
            user=user,
            business=sale.business,
            status=status,
            description=description,
            request_data=request_data,
            response_data=response_data,
            error_details=error_details,
            request=request,
            execution_time_ms=execution_time_ms
        )
    
    def log_purchase_receiving(
        self,
        purchase: Purchase,
        user: User,
        receiving_data: Dict,
        status: str,
        execution_time_ms: int,
        request: Optional[HttpRequest] = None,
        error_details: Optional[Dict] = None
    ) -> ActivityLog:
        """
        Log purchase receiving with received quantities and discrepancies.
        
        Args:
            purchase: Purchase instance
            user: User who received the goods
            receiving_data: Dictionary with receiving details
            status: Operation status ('success', 'failure', 'rollback')
            execution_time_ms: Execution time in milliseconds
            request: HTTP request object
            error_details: Error details if operation failed
            
        Returns:
            Created ActivityLog instance
        """
        # Build request data
        request_data = {
            'purchase_id': purchase.id,
            'purchase_number': purchase.purchase_number,
            'supplier_id': purchase.supplier.id,
            'supplier_name': purchase.supplier.name,
            'receiving_data': receiving_data
        }
        
        # Build response data
        response_data = {
            'purchase_id': purchase.id,
            'purchase_number': purchase.purchase_number,
            'status': status
        }
        
        description = f"Purchase {purchase.purchase_number} - Goods received from {purchase.supplier.name}"
        if status == 'failure':
            description += " (FAILED)"
        elif status == 'rollback':
            description += " (ROLLED BACK)"
        
        return self.log_operation(
            operation_type='purchase_receiving',
            entity_type='Purchase',
            entity_id=str(purchase.id),
            user=user,
            business=purchase.business,
            status=status,
            description=description,
            request_data=request_data,
            response_data=response_data,
            error_details=error_details,
            request=request,
            execution_time_ms=execution_time_ms
        )
    
    def log_stock_adjustment(
        self,
        product,
        user: User,
        adjustment_type: str,
        quantity_change: int,
        previous_quantity: int,
        new_quantity: int,
        reason: str,
        status: str,
        execution_time_ms: int,
        request: Optional[HttpRequest] = None,
        error_details: Optional[Dict] = None
    ) -> ActivityLog:
        """
        Log stock adjustment with previous and new quantities.
        
        Args:
            product: Product instance
            user: User who made the adjustment
            adjustment_type: Type of adjustment (e.g., 'restock', 'damage', 'correction')
            quantity_change: Quantity change (positive or negative)
            previous_quantity: Stock quantity before adjustment
            new_quantity: Stock quantity after adjustment
            reason: Reason for adjustment
            status: Operation status ('success', 'failure', 'rollback')
            execution_time_ms: Execution time in milliseconds
            request: HTTP request object
            error_details: Error details if operation failed
            
        Returns:
            Created ActivityLog instance
        """
        # Build request data
        request_data = {
            'product_id': product.id,
            'product_name': product.name,
            'adjustment_type': adjustment_type,
            'quantity_change': quantity_change,
            'previous_quantity': previous_quantity,
            'new_quantity': new_quantity,
            'reason': reason
        }
        
        # Build response data
        response_data = {
            'product_id': product.id,
            'new_quantity': new_quantity,
            'status': status
        }
        
        description = (
            f"Stock adjustment for {product.name}: "
            f"{previous_quantity} → {new_quantity} ({quantity_change:+d}) - {reason}"
        )
        if status == 'failure':
            description += " (FAILED)"
        elif status == 'rollback':
            description += " (ROLLED BACK)"
        
        return self.log_operation(
            operation_type='stock_adjustment',
            entity_type='Product',
            entity_id=str(product.id),
            user=user,
            business=product.business,
            status=status,
            description=description,
            request_data=request_data,
            response_data=response_data,
            error_details=error_details,
            request=request,
            execution_time_ms=execution_time_ms
        )
    
    def log_payment_processing(
        self,
        payment,
        user: User,
        allocations: list,
        status: str,
        execution_time_ms: int,
        request: Optional[HttpRequest] = None,
        error_details: Optional[Dict] = None
    ) -> ActivityLog:
        """
        Log payment processing with allocations and balances.
        
        Args:
            payment: SupplierPayment instance
            user: User who processed the payment
            allocations: List of payment allocations
            status: Operation status ('success', 'failure', 'rollback')
            execution_time_ms: Execution time in milliseconds
            request: HTTP request object
            error_details: Error details if operation failed
            
        Returns:
            Created ActivityLog instance
        """
        # Build request data
        request_data = {
            'payment_id': payment.id,
            'supplier_id': payment.supplier.id,
            'supplier_name': payment.supplier.name,
            'amount': float(payment.amount),
            'payment_method': payment.payment_method.name if payment.payment_method else None,
            'reference_number': payment.reference_number,
            'allocations': [
                {
                    'purchase_id': alloc.get('purchase_id'),
                    'amount': float(alloc.get('amount', 0))
                }
                for alloc in allocations
            ]
        }
        
        # Build response data
        response_data = {
            'payment_id': payment.id,
            'reference_number': payment.reference_number,
            'status': status
        }
        
        description = (
            f"Payment {payment.reference_number} - "
            f"{payment.supplier.name} - KES {payment.amount}"
        )
        if status == 'failure':
            description += " (FAILED)"
        elif status == 'rollback':
            description += " (ROLLED BACK)"
        
        return self.log_operation(
            operation_type='payment_processing',
            entity_type='SupplierPayment',
            entity_id=str(payment.id),
            user=user,
            business=payment.business,
            status=status,
            description=description,
            request_data=request_data,
            response_data=response_data,
            error_details=error_details,
            request=request,
            execution_time_ms=execution_time_ms
        )
    
    def log_loyalty_operation(
        self,
        customer,
        user: User,
        operation_type: str,
        points_change: int,
        previous_balance: int,
        new_balance: int,
        reason: str,
        sale=None,
        status: str = 'success',
        execution_time_ms: int = 0,
        request: Optional[HttpRequest] = None,
        error_details: Optional[Dict] = None
    ) -> ActivityLog:
        """
        Log loyalty point operation with point changes and balances.
        
        Args:
            customer: Customer instance
            user: User who performed the operation
            operation_type: Type of operation ('earn_points', 'redeem_points')
            points_change: Points change (positive for earn, negative for redeem)
            previous_balance: Points balance before operation
            new_balance: Points balance after operation
            reason: Reason for operation
            sale: Associated sale if applicable
            status: Operation status ('success', 'failure', 'rollback')
            execution_time_ms: Execution time in milliseconds
            request: HTTP request object
            error_details: Error details if operation failed
            
        Returns:
            Created ActivityLog instance
        """
        # Build request data
        request_data = {
            'customer_id': customer.id,
            'customer_name': customer.name,
            'operation_type': operation_type,
            'points_change': points_change,
            'previous_balance': previous_balance,
            'new_balance': new_balance,
            'reason': reason,
            'sale_id': sale.id if sale else None,
            'sale_invoice': sale.invoice_number if sale else None
        }
        
        # Build response data
        response_data = {
            'customer_id': customer.id,
            'new_balance': new_balance,
            'status': status
        }
        
        description = (
            f"Loyalty {operation_type} for {customer.name}: "
            f"{previous_balance} → {new_balance} ({points_change:+d} points) - {reason}"
        )
        if status == 'failure':
            description += " (FAILED)"
        elif status == 'rollback':
            description += " (ROLLED BACK)"
        
        return self.log_operation(
            operation_type=operation_type,
            entity_type='Customer',
            entity_id=str(customer.id),
            user=user,
            business=customer.business,
            status=status,
            description=description,
            request_data=request_data,
            response_data=response_data,
            error_details=error_details,
            request=request,
            execution_time_ms=execution_time_ms
        )
