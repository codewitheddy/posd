"""
Custom exception classes for POS system error handling.

This module defines custom exceptions for business logic errors, concurrency
control, and validation failures. Each exception includes context attributes
for detailed error information and logging.
"""


class InsufficientStockError(Exception):
    """
    Raised when attempting to sell or adjust stock beyond available quantity.
    
    Attributes:
        product: Product instance with insufficient stock
        requested: Quantity requested
        available: Quantity available
        message: Human-readable error message
    """
    
    def __init__(self, product, requested: int, available: int):
        self.product = product
        self.requested = requested
        self.available = available
        self.message = (
            f"Insufficient stock for {product.name}. "
            f"Requested: {requested}, Available: {available}"
        )
        super().__init__(self.message)
        
    def to_dict(self):
        """Return exception details as dictionary for logging."""
        return {
            'error_type': 'InsufficientStockError',
            'product_id': self.product.id,
            'product_name': self.product.name,
            'requested_quantity': self.requested,
            'available_quantity': self.available,
            'message': self.message
        }


class ConcurrentModificationError(Exception):
    """
    Raised when optimistic locking detects concurrent modification.
    
    Indicates that a record was modified by another transaction between
    the time it was read and the time an update was attempted.
    
    Attributes:
        model: Name of the model that was modified
        expected_version: Version number expected
        actual_version: Actual version number in database
        message: Human-readable error message
    """
    
    def __init__(self, model: str, expected_version: int, actual_version: int):
        self.model = model
        self.expected_version = expected_version
        self.actual_version = actual_version
        self.message = (
            f"Concurrent modification detected for {model}. "
            f"Expected version: {expected_version}, "
            f"Actual version: {actual_version}"
        )
        super().__init__(self.message)
        
    def to_dict(self):
        """Return exception details as dictionary for logging."""
        return {
            'error_type': 'ConcurrentModificationError',
            'model': self.model,
            'expected_version': self.expected_version,
            'actual_version': self.actual_version,
            'message': self.message
        }


class InsufficientPointsError(Exception):
    """
    Raised when attempting to redeem more loyalty points than available.
    
    Attributes:
        customer: Customer instance with insufficient points
        requested: Points requested for redemption
        available: Points available in customer account
        message: Human-readable error message
    """
    
    def __init__(self, customer, requested: int, available: int):
        self.customer = customer
        self.requested = requested
        self.available = available
        self.message = (
            f"Insufficient loyalty points for {customer.name}. "
            f"Requested: {requested}, Available: {available}"
        )
        super().__init__(self.message)
        
    def to_dict(self):
        """Return exception details as dictionary for logging."""
        return {
            'error_type': 'InsufficientPointsError',
            'customer_id': self.customer.id,
            'customer_name': self.customer.name,
            'requested_points': self.requested,
            'available_points': self.available,
            'message': self.message
        }


class DuplicatePaymentError(Exception):
    """
    Raised when attempting to process a payment with duplicate reference number.
    
    Prevents duplicate payment processing through idempotency key validation.
    
    Attributes:
        reference_number: Duplicate payment reference number
        message: Human-readable error message
    """
    
    def __init__(self, reference_number: str):
        self.reference_number = reference_number
        self.message = (
            f"Payment with reference number '{reference_number}' "
            f"has already been processed"
        )
        super().__init__(self.message)
        
    def to_dict(self):
        """Return exception details as dictionary for logging."""
        return {
            'error_type': 'DuplicatePaymentError',
            'reference_number': self.reference_number,
            'message': self.message
        }


class ValidationError(Exception):
    """
    Raised when business rule validation fails.
    
    Can contain multiple validation failures for comprehensive error reporting.
    
    Attributes:
        errors: Dictionary or list of validation errors
        message: Human-readable error message
    """
    
    def __init__(self, errors, message: str = "Validation failed"):
        self.errors = errors
        self.message = message
        super().__init__(self.message)
        
    def to_dict(self):
        """Return exception details as dictionary for logging."""
        return {
            'error_type': 'ValidationError',
            'errors': self.errors,
            'message': self.message
        }


class InsufficientBalanceError(Exception):
    """
    Raised when payment allocation exceeds purchase balance.
    
    Attributes:
        purchase_id: ID of purchase with insufficient balance
        requested: Amount requested for allocation
        available: Available balance on purchase
        message: Human-readable error message
    """
    
    def __init__(self, purchase_id: int, requested: float, available: float):
        self.purchase_id = purchase_id
        self.requested = requested
        self.available = available
        self.message = (
            f"Insufficient balance for purchase {purchase_id}. "
            f"Requested: {requested}, Available: {available}"
        )
        super().__init__(self.message)
        
    def to_dict(self):
        """Return exception details as dictionary for logging."""
        return {
            'error_type': 'InsufficientBalanceError',
            'purchase_id': self.purchase_id,
            'requested_amount': self.requested,
            'available_balance': self.available,
            'message': self.message
        }
