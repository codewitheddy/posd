"""
Idempotency key management for preventing duplicate request processing.

This module provides utilities for detecting and preventing duplicate operations
using idempotency keys with configurable time-to-live (TTL).
"""

import logging
from datetime import timedelta
from typing import Tuple, Optional, Dict
from django.utils import timezone
from django.db import transaction, IntegrityError
from pos.models import IdempotencyKey, Business

logger = logging.getLogger(__name__)


class IdempotencyManager:
    """
    Manager for idempotency key operations.
    
    Provides methods for checking, creating, and managing idempotency keys
    to prevent duplicate processing of requests.
    """
    
    def check_and_create(
        self,
        key: str,
        business: Business,
        operation_type: str,
        request_data: Dict,
        ttl_seconds: int = 86400
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Check if idempotency key exists and create if not.
        
        Args:
            key: Unique idempotency key (e.g., payment reference number)
            business: Business instance
            operation_type: Type of operation (e.g., 'sale_completion', 'payment_processing')
            request_data: Request data to store
            ttl_seconds: Time-to-live in seconds (default: 24 hours)
            
        Returns:
            Tuple of (is_duplicate, existing_response):
                - is_duplicate: True if key already exists
                - existing_response: Response data from previous request if duplicate
                
        Example:
            is_duplicate, response = manager.check_and_create(
                key='PAY-12345',
                business=business,
                operation_type='payment_processing',
                request_data={'amount': 1000, 'supplier_id': 5}
            )
            
            if is_duplicate:
                return response  # Return cached response
        """
        try:
            with transaction.atomic():
                # Try to get existing key
                try:
                    existing_key = IdempotencyKey.objects.select_for_update().get(
                        key=key,
                        business=business
                    )
                    
                    # Check if expired
                    if existing_key.is_expired():
                        # Delete expired key and create new one
                        existing_key.delete()
                        logger.info(f"Deleted expired idempotency key: {key}")
                        
                        # Create new key
                        expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
                        IdempotencyKey.objects.create(
                            key=key,
                            business=business,
                            operation_type=operation_type,
                            request_data=request_data,
                            status='processing',
                            expires_at=expires_at
                        )
                        
                        return (False, None)
                    
                    # Key exists and not expired - this is a duplicate
                    logger.warning(
                        f"Duplicate request detected for key: {key}, "
                        f"status: {existing_key.status}"
                    )
                    
                    # Return existing response if completed
                    if existing_key.status == 'completed':
                        return (True, existing_key.response_data)
                    elif existing_key.status == 'processing':
                        # Request is still being processed
                        return (True, {'status': 'processing', 'message': 'Request is being processed'})
                    else:  # failed
                        # Previous request failed - allow retry
                        return (False, None)
                        
                except IdempotencyKey.DoesNotExist:
                    # Key doesn't exist - create it
                    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
                    IdempotencyKey.objects.create(
                        key=key,
                        business=business,
                        operation_type=operation_type,
                        request_data=request_data,
                        status='processing',
                        expires_at=expires_at
                    )
                    
                    logger.info(f"Created new idempotency key: {key}")
                    return (False, None)
                    
        except IntegrityError:
            # Race condition - key was created by another request
            # Treat as duplicate
            logger.warning(f"Race condition detected for idempotency key: {key}")
            return (True, None)
    
    def mark_completed(self, key: str, response_data: Dict) -> None:
        """
        Mark idempotency key as completed with response data.
        
        Args:
            key: Idempotency key
            response_data: Response data to cache
            
        Example:
            manager.mark_completed(
                key='PAY-12345',
                response_data={'payment_id': 123, 'status': 'success'}
            )
        """
        try:
            idempotency_key = IdempotencyKey.objects.get(key=key)
            idempotency_key.status = 'completed'
            idempotency_key.response_data = response_data
            idempotency_key.save(update_fields=['status', 'response_data'])
            
            logger.info(f"Marked idempotency key as completed: {key}")
            
        except IdempotencyKey.DoesNotExist:
            logger.error(f"Idempotency key not found: {key}")
    
    def mark_failed(self, key: str, error_details: Dict) -> None:
        """
        Mark idempotency key as failed.
        
        Args:
            key: Idempotency key
            error_details: Error details to store
            
        Example:
            manager.mark_failed(
                key='PAY-12345',
                error_details={'error': 'Insufficient balance'}
            )
        """
        try:
            idempotency_key = IdempotencyKey.objects.get(key=key)
            idempotency_key.status = 'failed'
            idempotency_key.response_data = error_details
            idempotency_key.save(update_fields=['status', 'response_data'])
            
            logger.info(f"Marked idempotency key as failed: {key}")
            
        except IdempotencyKey.DoesNotExist:
            logger.error(f"Idempotency key not found: {key}")
    
    def cleanup_expired(self) -> int:
        """
        Remove expired idempotency keys.
        
        Should be called periodically (e.g., via cron job or management command)
        to clean up old keys and free database space.
        
        Returns:
            Number of keys removed
            
        Example:
            manager = IdempotencyManager()
            removed_count = manager.cleanup_expired()
            print(f"Removed {removed_count} expired keys")
        """
        now = timezone.now()
        expired_keys = IdempotencyKey.objects.filter(expires_at__lt=now)
        count = expired_keys.count()
        expired_keys.delete()
        
        logger.info(f"Cleaned up {count} expired idempotency keys")
        return count


def idempotent(key_generator, ttl_seconds: int = 86400):
    """
    Decorator for making functions idempotent.
    
    Prevents duplicate execution of a function within the TTL window by
    checking idempotency keys before execution.
    
    Args:
        key_generator: Function that generates idempotency key from function arguments
        ttl_seconds: Time-to-live for idempotency key in seconds
        
    Returns:
        Decorated function
        
    Example:
        @idempotent(
            key_generator=lambda self, payment_data: payment_data['reference_number'],
            ttl_seconds=86400
        )
        def process_payment(self, payment_data):
            # Payment processing logic
            pass
    """
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate idempotency key
            key = key_generator(*args, **kwargs)
            
            # Extract business from arguments (assume it's in kwargs or first arg after self)
            business = kwargs.get('business')
            if not business and len(args) > 1:
                # Try to get business from first argument after self
                if hasattr(args[1], '__class__') and args[1].__class__.__name__ == 'Business':
                    business = args[1]
            
            if not business:
                # Can't use idempotency without business context
                logger.warning(f"Idempotency check skipped - no business context for key: {key}")
                return func(*args, **kwargs)
            
            # Check idempotency
            manager = IdempotencyManager()
            is_duplicate, existing_response = manager.check_and_create(
                key=key,
                business=business,
                operation_type=func.__name__,
                request_data={'args': str(args), 'kwargs': str(kwargs)},
                ttl_seconds=ttl_seconds
            )
            
            if is_duplicate and existing_response:
                logger.info(f"Returning cached response for idempotency key: {key}")
                return existing_response
            
            # Execute function
            try:
                result = func(*args, **kwargs)
                
                # Mark as completed
                manager.mark_completed(key, result if isinstance(result, dict) else {'result': str(result)})
                
                return result
                
            except Exception as e:
                # Mark as failed
                manager.mark_failed(key, {'error': str(e)})
                raise
        
        return wrapper
    return decorator
