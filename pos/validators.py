"""
Custom password validators for stronger password policies
"""
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class UppercaseValidator:
    """Require at least one uppercase letter"""
    def validate(self, password, user=None):
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                _('Password must contain at least one uppercase letter.'),
                code='password_no_upper',
            )

    def get_help_text(self):
        return _('Your password must contain at least one uppercase letter.')


class LowercaseValidator:
    """Require at least one lowercase letter"""
    def validate(self, password, user=None):
        if not re.search(r'[a-z]', password):
            raise ValidationError(
                _('Password must contain at least one lowercase letter.'),
                code='password_no_lower',
            )

    def get_help_text(self):
        return _('Your password must contain at least one lowercase letter.')


class NumberValidator:
    """Require at least one digit"""
    def validate(self, password, user=None):
        if not re.search(r'\d', password):
            raise ValidationError(
                _('Password must contain at least one number.'),
                code='password_no_number',
            )

    def get_help_text(self):
        return _('Your password must contain at least one number.')


class SpecialCharValidator:
    """Require at least one special character"""
    def validate(self, password, user=None):
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-\[\]\\\/\+\=\~\`\;\']', password):
            raise ValidationError(
                _('Password must contain at least one special character (!@#$%^&* etc.).'),
                code='password_no_special',
            )

    def get_help_text(self):
        return _('Your password must contain at least one special character.')


class PasswordHistoryValidator:
    """
    Prevent reuse of the last N passwords.
    Requires PasswordHistory model to be populated on password change.
    """
    def __init__(self, history_count=5):
        self.history_count = history_count

    def validate(self, password, user=None):
        if user is None or not user.pk:
            return

        from django.contrib.auth.hashers import check_password
        from .models import PasswordHistory

        recent = PasswordHistory.objects.filter(user=user).order_by('-created_at')[:self.history_count]
        for entry in recent:
            if check_password(password, entry.password_hash):
                raise ValidationError(
                    _(f'You cannot reuse any of your last {self.history_count} passwords.'),
                    code='password_reused',
                )

    def get_help_text(self):
        return _(f'Your password cannot be the same as your last {self.history_count} passwords.')
