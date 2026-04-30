"""
Structured error handling and logging for POS system.

This module provides comprehensive error logging with context, structured error
responses, and sensitive data sanitization for security and compliance.
"""

import logging
import traceback
import uuid
import re
from django.utils import timezone
from typing import Dict, Any, Optional
from django.http import HttpRequest, JsonResponse
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class ErrorLogger:
    """
    Centralized error logging with complete context capture.
    
    Logs errors with full context including user, business, request details,
    and sanitized input data for debugging and compliance.
    """
    
    # Patterns for sensitive data that should be sanitized
    SENSITIVE_PATTERNS = [
        (r'password', '***REDACTED***'),
        (r'passwd', '***REDACTED***'),
        (r'pwd', '***REDACTED***'),
        (r'secret', '***REDACTED***'),
        (r'token', '***REDACTED***'),
        (r'api[_-]?key', '***REDACTED***'),
        (r'credit[_-]?card', '***REDACTED***'),
        (r'card[_-]?number', '***REDACTED***'),
        (r'cvv', '***REDACTED***'),
        (r'ssn', '***REDACTED***'),
        (r'social[_-]?security', '***REDACTED***'),
    ]
    
    @staticmethod
    def sanitize_data(data: Any) -> Any:
        """
        Sanitize sensitive data before logging.
        
        Recursively searches through dictionaries and lists to redact
        sensitive information like passwords, credit cards, etc.
        
        Args:
            data: Data to sanitize (dict, list, or primitive)
            
        Returns:
            Sanitized copy of data
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                # Check if key matches sensitive pattern
                key_lower = str(key).lower()
                is_sensitive = any(
                    re.search(pattern, key_lower)
                    for pattern, _ in ErrorLogger.SENSITIVE_PATTERNS
                )
                
                if is_sensitive:
                    sanitized[key] = '***REDACTED***'
                else:
                    sanitized[key] = ErrorLogger.sanitize_data(value)
            return sanitized
            
        elif isinstance(data, (list, tuple)):
            return [ErrorLogger.sanitize_data(item) for item in data]
            
        elif isinstance(data, str):
            # Check for credit card patterns (simple check)
            if re.search(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', data):
                return '***CARD_NUMBER_REDACTED***'
            return data
            
        else:
            return data
    
    @staticmethod
    def extract_request_context(request: Optional[HttpRequest]) -> Dict[str, Any]:
        """
        Extract relevant context from HTTP request.
        
        Args:
            request: Django HttpRequest object
            
        Returns:
            Dictionary with request context
        """
        if not request:
            return {}
        
        context = {
            'path': request.path,
            'method': request.method,
            'ip_address': ErrorLogger.get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        }
        
        # Add query parameters (sanitized)
        if request.GET:
            context['query_params'] = ErrorLogger.sanitize_data(dict(request.GET))
        
        # Add POST data (sanitized) - be careful with large files
        if request.method == 'POST' and request.POST:
            context['post_data'] = ErrorLogger.sanitize_data(dict(request.POST))
        
        return context
    
    @staticmethod
    def get_client_ip(request: HttpRequest) -> str:
        """
        Get client IP address from request, handling proxies.
        
        Args:
            request: Django HttpRequest object
            
        Returns:
            Client IP address
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    def log_error(
        self,
        error: Exception,
        context: Dict[str, Any],
        user: Optional[User] = None,
        request: Optional[HttpRequest] = None
    ) -> str:
        """
        Log error with complete context and return error reference ID.
        
        Args:
            error: Exception that occurred
            context: Additional context dictionary
            user: User who triggered the error (if applicable)
            request: HTTP request object (if applicable)
            
        Returns:
            Unique error reference ID for correlation
            
        Example:
            error_ref = logger.log_error(
                error=e,
                context={'operation': 'sale_completion', 'sale_id': 123},
                user=request.user,
                request=request
            )
        """
        # Generate unique error reference ID
        error_ref_id = str(uuid.uuid4())
        
        # Build error log entry
        log_entry = {
            'error_ref_id': error_ref_id,
            'timestamp': timezone.now().isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'stack_trace': traceback.format_exc(),
        }
        
        # Add user context
        if user and user.is_authenticated:
            log_entry['user'] = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            }
        
        # Add request context
        if request:
            log_entry['request'] = self.extract_request_context(request)
        
        # Add custom context (sanitized)
        if context:
            log_entry['context'] = self.sanitize_data(context)
        
        # Add exception-specific context if available
        if hasattr(error, 'to_dict'):
            log_entry['exception_details'] = error.to_dict()
        
        # Log the error
        logger.error(
            f"Error [{error_ref_id}]: {type(error).__name__} - {str(error)}",
            extra=log_entry,
            exc_info=True
        )
        
        return error_ref_id
    
    def log_transaction_failure(
        self,
        operation: str,
        error: Exception,
        transaction_data: Dict[str, Any],
        user: User,
        business
    ) -> str:
        """
        Log transaction failure with complete transaction context.
        
        Args:
            operation: Operation name (e.g., 'sale_completion')
            error: Exception that caused failure
            transaction_data: Transaction data (will be sanitized)
            user: User who initiated transaction
            business: Business context
            
        Returns:
            Unique error reference ID
            
        Example:
            error_ref = logger.log_transaction_failure(
                operation='sale_completion',
                error=e,
                transaction_data={'items': [...], 'payments': [...]},
                user=cashier,
                business=business
            )
        """
        context = {
            'operation': operation,
            'business_id': business.id,
            'business_name': business.name,
            'transaction_data': self.sanitize_data(transaction_data),
        }
        
        # Add database transaction info if available
        from django.db import connection
        if connection.in_atomic_block:
            context['in_transaction'] = True
            context['isolation_level'] = connection.isolation_level
        
        return self.log_error(
            error=error,
            context=context,
            user=user
        )


class ErrorResponse:
    """
    Structured error response for API and view responses.
    
    Provides consistent error response format with error codes,
    user-friendly messages, and optional technical details.
    """
    
    # Error code categories
    ERROR_CODES = {
        # User errors (4xx)
        'VALIDATION_ERROR': 'VAL_001',
        'INSUFFICIENT_STOCK': 'VAL_002',
        'INSUFFICIENT_POINTS': 'VAL_003',
        'INSUFFICIENT_BALANCE': 'VAL_004',
        'DUPLICATE_PAYMENT': 'VAL_005',
        
        # System errors (5xx)
        'DATABASE_ERROR': 'SYS_001',
        'TRANSACTION_FAILED': 'SYS_002',
        'CONCURRENT_MODIFICATION': 'SYS_003',
        'DEADLOCK_DETECTED': 'SYS_004',
        'UNKNOWN_ERROR': 'SYS_999',
    }
    
    def __init__(
        self,
        error_code: str,
        user_message: str,
        technical_details: Optional[Dict] = None,
        reference_id: Optional[str] = None
    ):
        """
        Initialize error response.
        
        Args:
            error_code: Error code from ERROR_CODES
            user_message: User-friendly error message
            technical_details: Technical details (for debugging, not shown to users)
            reference_id: Error reference ID for correlation with logs
        """
        self.error_code = error_code
        self.user_message = user_message
        self.technical_details = technical_details or {}
        self.reference_id = reference_id or str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error response to dictionary.
        
        Returns:
            Dictionary representation of error
        """
        response = {
            'error': True,
            'error_code': self.error_code,
            'message': self.user_message,
            'reference_id': self.reference_id,
        }
        
        # Include technical details only in debug mode
        from django.conf import settings
        if settings.DEBUG and self.technical_details:
            response['technical_details'] = self.technical_details
        
        return response
    
    def to_json_response(self, status_code: int = 400) -> JsonResponse:
        """
        Convert error response to Django JsonResponse.
        
        Args:
            status_code: HTTP status code (default: 400)
            
        Returns:
            JsonResponse object
        """
        return JsonResponse(self.to_dict(), status=status_code)
    
    @classmethod
    def from_exception(cls, error: Exception, reference_id: Optional[str] = None):
        """
        Create ErrorResponse from exception.
        
        Args:
            error: Exception to convert
            reference_id: Error reference ID from logging
            
        Returns:
            ErrorResponse instance
        """
        from pos.exceptions import (
            InsufficientStockError,
            InsufficientPointsError,
            InsufficientBalanceError,
            DuplicatePaymentError,
            ConcurrentModificationError,
            ValidationError
        )
        
        # Map exceptions to error codes and messages
        if isinstance(error, InsufficientStockError):
            return cls(
                error_code=cls.ERROR_CODES['INSUFFICIENT_STOCK'],
                user_message=error.message,
                technical_details=error.to_dict(),
                reference_id=reference_id
            )
        elif isinstance(error, InsufficientPointsError):
            return cls(
                error_code=cls.ERROR_CODES['INSUFFICIENT_POINTS'],
                user_message=error.message,
                technical_details=error.to_dict(),
                reference_id=reference_id
            )
        elif isinstance(error, InsufficientBalanceError):
            return cls(
                error_code=cls.ERROR_CODES['INSUFFICIENT_BALANCE'],
                user_message=error.message,
                technical_details=error.to_dict(),
                reference_id=reference_id
            )
        elif isinstance(error, DuplicatePaymentError):
            return cls(
                error_code=cls.ERROR_CODES['DUPLICATE_PAYMENT'],
                user_message=error.message,
                technical_details=error.to_dict(),
                reference_id=reference_id
            )
        elif isinstance(error, ConcurrentModificationError):
            return cls(
                error_code=cls.ERROR_CODES['CONCURRENT_MODIFICATION'],
                user_message="This record was modified by another user. Please refresh and try again.",
                technical_details=error.to_dict(),
                reference_id=reference_id
            )
        elif isinstance(error, ValidationError):
            return cls(
                error_code=cls.ERROR_CODES['VALIDATION_ERROR'],
                user_message=error.message,
                technical_details=error.to_dict(),
                reference_id=reference_id
            )
        else:
            # Unknown error - return generic system error
            return cls(
                error_code=cls.ERROR_CODES['UNKNOWN_ERROR'],
                user_message="An unexpected error occurred. Please try again or contact support.",
                technical_details={'error_type': type(error).__name__, 'message': str(error)},
                reference_id=reference_id
            )
