"""
Services package for POS system.

This package contains service layer classes that encapsulate business logic
and provide atomic operations with transaction management.
"""

from .audit_service import AuditLogger

__all__ = ['AuditLogger']
