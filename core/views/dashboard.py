"""
Platform Modular Dashboard View
Renders registered dashboard cards from all active modules.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView
from core.dashboard import render_dashboard_cards
from core.scoping import get_current_company, get_current_branch, get_user_branches


class PlatformDashboardView(LoginRequiredMixin, TemplateView):
    """
    Main Platform Dashboard rendering widgets dynamically from all enabled modules.
    """
    template_name = 'core/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = get_current_company(self.request)
        branch = get_current_branch(self.request)

        context['company'] = company
        context['branch'] = branch
        context['user_branches'] = get_user_branches(self.request.user, company) if company else []
        context['rendered_cards'] = render_dashboard_cards(self.request)
        return context


class SwitchBranchView(LoginRequiredMixin, TemplateView):
    """Switch active branch in user session."""

    def post(self, request, branch_id):
        company = get_current_company(request)
        if company:
            user_branches = get_user_branches(request.user, company)
            target_branch = user_branches.filter(id=branch_id).first()
            if target_branch:
                request.session['active_branch_id'] = target_branch.id
                if hasattr(request.user, 'core_profile'):
                    profile = request.user.core_profile
                    profile.last_active_branch = target_branch
                    profile.save(update_fields=['last_active_branch'])

        return redirect(request.META.get('HTTP_REFERER', 'core_dashboard'))
