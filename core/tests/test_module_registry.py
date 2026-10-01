"""
Module Registry and Lifecycle Unit Tests
"""
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from core.models import Company, ModuleActivation
from core.registry import (
    ModuleRegistry,
    ModuleManifest,
    MenuSection,
    MenuItem,
    DashboardCard,
    HealthCheck,
    module_registry,
)
from core.navigation import build_navigation
from core.dashboard import render_dashboard_cards
from core.checks import check_module_manifests, find_cycle


class ModuleRegistryTests(TestCase):
    """Test suite for module registration, manifest discovery, and enablement."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testadmin', email='admin@example.com')
        self.company = Company.objects.create(name='Test Corp', slug='test-corp')

    def test_autodiscover_registers_core_and_business_modules(self):
        """Verify autodiscovery registers pos, hr, backup, and sync."""
        module_registry.autodiscover()
        registered_keys = [m.key for m in module_registry.get_all()]

        self.assertIn('pos', registered_keys)
        self.assertIn('hr', registered_keys)
        self.assertIn('backup', registered_keys)
        self.assertIn('sync', registered_keys)

    def test_enable_and_disable_module_for_company(self):
        """Test toggling module activation per company."""
        module_registry.autodiscover()
        
        # By default, modules are active
        self.assertTrue(module_registry.is_enabled('hr', self.company.id))

        # Disable HR module for this company
        module_registry.set_enabled('hr', self.company.id, False, user=self.user)
        self.assertFalse(module_registry.is_enabled('hr', self.company.id))

        # Re-enable HR module
        module_registry.set_enabled('hr', self.company.id, True, user=self.user)
        self.assertTrue(module_registry.is_enabled('hr', self.company.id))

    def test_dynamic_navigation_filters_disabled_modules(self):
        """Verify navigation menu hides items belonging to disabled modules."""
        module_registry.autodiscover()

        request = self.factory.get('/')
        request.user = self.user
        request.company = self.company

        # Active state: navigation contains HR items
        nav = build_navigation(request)
        section_titles = [s.title for s in nav]
        self.assertIn('Human Resources', section_titles)

        # Disable HR module
        module_registry.set_enabled('hr', self.company.id, False, user=self.user)
        
        nav_disabled = build_navigation(request)
        section_titles_disabled = [s.title for s in nav_disabled]
        self.assertNotIn('Human Resources', section_titles_disabled)

    def test_dashboard_card_error_boundary_does_not_break_page(self):
        """Verify that a failing dashboard card is safely caught without raising 500 error."""
        custom_registry = ModuleRegistry()

        def failing_callback(req, comp, br):
            raise ValueError("Simulated database failure inside dashboard card")

        custom_manifest = ModuleManifest(
            key='faulty_module',
            name='Faulty Module',
            dashboard_cards=[
                DashboardCard(
                    key='broken_card',
                    title='Failing Metric Card',
                    template_name='core/dashboard.html',
                    context_callback=failing_callback,
                )
            ]
        )
        custom_registry.register(custom_manifest)

        request = self.factory.get('/')
        request.user = self.user
        request.company = self.company

        # Calling render_dashboard_cards should succeed with graceful fallback
        cards = render_dashboard_cards(request)
        self.assertIsInstance(cards, list)

    def test_circular_dependency_detection(self):
        """Test that circular dependencies are caught by system checks."""
        cycle_graph = {
            'A': ['B'],
            'B': ['C'],
            'C': ['A'],
        }
        cycle = find_cycle(cycle_graph)
        self.assertEqual(cycle, ['A', 'B', 'C', 'A'])

        acyclic_graph = {
            'A': ['B', 'C'],
            'B': ['C'],
            'C': [],
        }
        no_cycle = find_cycle(acyclic_graph)
        self.assertEqual(no_cycle, [])

    def test_system_checks_pass_cleanly(self):
        """Verify core system checks run without errors on current configuration."""
        errors = check_module_manifests(None)
        self.assertEqual(errors, [])
