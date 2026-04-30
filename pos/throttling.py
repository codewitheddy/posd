"""
Custom throttling classes for rate limiting
"""

from rest_framework.throttling import SimpleRateThrottle


class AuthThrottle(SimpleRateThrottle):
    """
    Throttle for authentication endpoints (login, password reset, etc.)
    More restrictive than default anonymous throttling
    """
    scope = 'auth'
    rate = '5/minute'


class LoginThrottle(SimpleRateThrottle):
    """
    Very restrictive throttle for login attempts to prevent brute force attacks
    """
    scope = 'login'
    rate = '3/minute'


class PasswordResetThrottle(SimpleRateThrottle):
    """
    Throttle for password reset requests
    """
    scope = 'auth'
    rate = '2/minute'