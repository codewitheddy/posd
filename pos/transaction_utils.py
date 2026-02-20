"""
Transaction management utilities for atomic operations with retry logic.

This module provides decorators and context managers for wrapping operations
in database transactions with appropriate isolation levels and automatic retry
mechanisms for transient failures.
"""

import time
import random
import logging
from functools import wraps
from typing import Callable, Tuple, Optional
from django.db import transaction, OperationalError, IntegrityError
from django.db.backends.utils import CursorWrapper

logger = logging.getLogger(__name__)


def calculate_backoff_delay(attempt: int, base_ms: int = 100) -> float:
    """
    Calculate exponential backoff delay with jitter.
    
    Args:
        attempt: Current retry attempt number (0-indexed)
        base_ms: Base delay in milliseconds
        
    Returns:
        Delay in seconds with jitter applied
    """
    # Exponential backoff: base_ms * (2 ^ attempt)
    delay_ms = base_ms * (2 ** attempt)
    
    # Add jitter: random value between 0 and delay_ms
    jitter_ms = random.uniform(0, delay_ms)
    
    # Return total delay in seconds
    return (delay_ms + jitter_ms) / 1000.0


def atomic_with_retry(
    max_retries: int = 3,
    isolation_level: str = 'READ_COMMITTED',
    retry_on: Tuple = (OperationalError, IntegrityError),
    backoff_base_ms: int = 100
) -> Callable:
    """
    Decorator for atomic operations with automatic retry logic.
    
    Wraps a function in a database transaction with the specified isolation level
    and automatically retries on specified exceptions using exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        isolation_level: Database isolation level ('READ_COMMITTED' or 'SERIALIZABLE')
        retry_on: Tuple of exception types to retry on
        backoff_base_ms: Base delay for exponential backoff in milliseconds
        
    Returns:
        Decorated function
        
    Example:
        @atomic_with_retry(max_retries=3, isolation_level='SERIALIZABLE')
        def complete_sale(business, items):
            # Sale completion logic
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    # Set isolation level if SERIALIZABLE
                    if isolation_level == 'SERIALIZABLE':
                        with transaction.atomic():
                            # Set isolation level for this transaction
                            from django.db import connection
                            with connection.cursor() as cursor:
                                cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                            
                            # Execute the function
                            result = func(*args, **kwargs)
                            
                            if attempt > 0:
                                logger.info(
                                    f"{func.__name__} succeeded on retry attempt {attempt}"
                                )
                            
                            return result
                    else:
                        # Use default READ COMMITTED isolation level
                        with transaction.atomic():
                            result = func(*args, **kwargs)
                            
                            if attempt > 0:
                                logger.info(
                                    f"{func.__name__} succeeded on retry attempt {attempt}"
                                )
                            
                            return result
                            
                except retry_on as e:
                    last_exception = e
                    
                    # Don't retry if we've exhausted attempts
                    if attempt >= max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} retries: {str(e)}"
                        )
                        raise
                    
                    # Calculate backoff delay
                    delay = calculate_backoff_delay(attempt, backoff_base_ms)
                    
                    logger.warning(
                        f"{func.__name__} failed on attempt {attempt + 1}, "
                        f"retrying in {delay:.3f}s: {str(e)}"
                    )
                    
                    # Wait before retrying
                    time.sleep(delay)
                    
            # Should never reach here, but raise last exception if we do
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class atomic_transaction:
    """
    Context manager for explicit transaction control with isolation level.
    
    Provides fine-grained control over transaction boundaries and isolation levels
    for complex operations that need manual transaction management.
    
    Args:
        isolation_level: Database isolation level ('READ_COMMITTED' or 'SERIALIZABLE')
        
    Example:
        with atomic_transaction(isolation_level='SERIALIZABLE'):
            # Perform operations
            product.quantity -= 1
            product.save()
    """
    
    def __init__(self, isolation_level: str = 'READ_COMMITTED'):
        self.isolation_level = isolation_level
        self.atomic_context = None
        
    def __enter__(self):
        # Start atomic transaction
        self.atomic_context = transaction.atomic()
        self.atomic_context.__enter__()
        
        # Set isolation level if SERIALIZABLE
        if self.isolation_level == 'SERIALIZABLE':
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Exit atomic transaction
        if self.atomic_context:
            return self.atomic_context.__exit__(exc_type, exc_val, exc_tb)
        return False


def check_version_and_update(
    model_instance,
    expected_version: int,
    update_fields: dict
) -> bool:
    """
    Update model instance only if version matches expected version.
    
    Implements optimistic locking by checking the version field before updating.
    Raises ConcurrentModificationError if version mismatch is detected.
    
    Args:
        model_instance: Model instance to update
        expected_version: Expected version number
        update_fields: Dictionary of fields to update
        
    Returns:
        True if update succeeded
        
    Raises:
        ConcurrentModificationError: If version mismatch detected
        
    Example:
        check_version_and_update(
            product,
            expected_version=5,
            update_fields={'quantity': 100}
        )
    """
    from pos.exceptions import ConcurrentModificationError
    from django.db.models import F
    
    model_class = model_instance.__class__
    pk = model_instance.pk
    
    # Build update query with version check
    update_dict = update_fields.copy()
    update_dict['version'] = F('version') + 1
    
    # Perform conditional update
    rows_updated = model_class.objects.filter(
        pk=pk,
        version=expected_version
    ).update(**update_dict)
    
    if rows_updated == 0:
        # Version mismatch - reload to get actual version
        model_instance.refresh_from_db()
        actual_version = model_instance.version
        
        raise ConcurrentModificationError(
            model=model_class.__name__,
            expected_version=expected_version,
            actual_version=actual_version
        )
    
    # Reload instance to get updated values
    model_instance.refresh_from_db()
    return True
