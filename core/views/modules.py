"""
Backoffice Module Control Views
Allows administrators to view, monitor, and toggle business modules.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView
from core.registry import module_registry
from core.scoping import get_current_company


class AdminRequiredMixin(UserPassesTestMixin):
    """Requires user to be a superuser or Company Administrator/Owner."""

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        company = get_current_company(self.request)
        if company:
            membership = company.memberships.filter(user=user, is_active=True).first()
            return bool(membership and membership.is_admin_or_owner)
        return False


class ModuleControlView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Backoffice screen showing all registered modules, versions, dependencies, health status, and activation toggles.
    """
    template_name = 'core/modules/module_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company = get_current_company(self.request)
        company_id = company.id if company else None

        modules_data = []
        for manifest in module_registry.get_all():
            is_enabled = module_registry.is_enabled(manifest.key, company_id)
            deps_valid, missing_deps = module_registry.validate_dependencies(manifest.key, company_id)

            # Run health checks
            health_results = []
            for hc in manifest.health_checks:
                try:
                    passed, message = hc.check_callback()
                    health_results.append({'name': hc.name, 'passed': passed, 'message': message})
                except Exception as e:
                    health_results.append({'name': hc.name, 'passed': False, 'message': str(e)})

            modules_data.append({
                'manifest': manifest,
                'is_enabled': is_enabled,
                'can_toggle': not manifest.is_core,
                'deps_valid': deps_valid,
                'missing_deps': missing_deps,
                'health_results': health_results,
            })

        context['modules'] = modules_data
        context['company'] = company
        return context


class ModuleToggleView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Handle POST request to enable or disable a business module.
    """

    def post(self, request, module_key):
        company = get_current_company(request)
        if not company:
            messages.error(request, "No active company found.")
            return redirect('core_module_list')

        manifest = module_registry.get(module_key)
        if not manifest:
            messages.error(request, f"Module '{module_key}' not recognized.")
            return redirect('core_module_list')

        if manifest.is_core:
            messages.warning(request, "Core module cannot be disabled.")
            return redirect('core_module_list')

        current_status = module_registry.is_enabled(module_key, company.id)
        new_status = not current_status

        if new_status:
            # Check dependencies before enabling
            is_valid, missing_deps = module_registry.validate_dependencies(module_key, company.id)
            if not is_valid:
                messages.error(
                    request,
                    f"Cannot enable '{manifest.name}'. Missing dependencies: {', '.join(missing_deps)}"
                )
                return redirect('core_module_list')

        module_registry.set_enabled(module_key, company.id, new_status, user=request.user)
        action_str = "enabled" if new_status else "disabled"
        messages.success(request, f"Module '{manifest.name}' has been {action_str} successfully.")
        return redirect('core_module_list')
