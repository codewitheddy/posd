"""
Core Platform Context Processors
Provides active company, branch, and unread notifications to all Django templates.
"""
from core.notifications.service import get_unread_notifications
from core.scoping import get_current_company, get_current_branch


def core_platform_context(request):
    """
    Inject core platform variables into template context.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {
            'platform_company': None,
            'platform_branch': None,
            'unread_notifications_count': 0,
            'unread_notifications_list': [],
        }

    company = getattr(request, 'company', None) or get_current_company(request)
    branch = getattr(request, 'branch', None) or get_current_branch(request)
    unread_qs = get_unread_notifications(request.user)[:5]

    return {
        'platform_company': company,
        'platform_branch': branch,
        'unread_notifications_count': get_unread_notifications(request.user).count(),
        'unread_notifications_list': unread_qs,
    }
