"""
Management Command: startmodule
Scaffolds a standard business module structure conforming to Platform Architecture principles.
"""
import os
from django.core.management.base import BaseCommand, CommandError


MODULE_PY_TEMPLATE = '''"""
{module_name_title} Module Manifest
"""
from core.registry import ModuleManifest, MenuSection, MenuItem, DashboardCard

manifest = ModuleManifest(
    key='{module_key}',
    name='{module_name_title}',
    version='1.0.0',
    description='{module_name_title} business module for ERP Platform',
    icon='bi bi-folder2-open',
    dependencies=[],
    permission_prefix='{module_key}',
    default_roles={{
        '{module_name_title} Manager': [],
        '{module_name_title} Staff': [],
    }},
    menu_sections=[
        MenuSection(
            title='{module_name_title}',
            order=100,
            items=[
                MenuItem(
                    title='Overview',
                    url_name='{module_key}:dashboard',
                    icon='bi bi-speedometer2',
                ),
            ],
        ),
    ],
    dashboard_cards=[],
    url_prefix='/{module_key}/',
)
'''

API_PY_TEMPLATE = '''"""
{module_name_title} Module Public Interface (api.py)
This is the ONLY file sibling modules are permitted to import from {module_key}.
Never import models, views, or internal services directly.
"""
from typing import Any, Dict, List, Optional


def get_module_status() -> Dict[str, Any]:
    """Return public status and health for {module_key}."""
    return {{
        'module': '{module_key}',
        'is_ready': True,
    }}
'''

HANDLERS_PY_TEMPLATE = '''"""
{module_name_title} Domain Event Handlers
Idempotent subscriber functions reacting to system outbox events.
"""
import logging

logger = logging.getLogger(__name__)


def on_employee_hired(event_payload: dict) -> None:
    """Example handler for employee_hired event."""
    pass
'''

SELECTORS_PY_TEMPLATE = '''"""
{module_name_title} Selectors (Read Layer)
All complex database queries and data aggregation live here.
Views call selectors; views do not write raw complex ORM queries.
"""
from django.db.models import QuerySet


def get_active_items(company) -> QuerySet:
    """Example selector returning scoped records."""
    pass
'''

SERVICES_PY_TEMPLATE = '''"""
{module_name_title} Services (Business Logic Layer)
All write operations, state transitions, and business rules live here.
"""
import logging
from django.db import transaction

logger = logging.getLogger(__name__)


@transaction.atomic
def perform_action(company, data: dict, user=None):
    """Example transactional service."""
    pass
'''

APPS_PY_TEMPLATE = '''from django.apps import AppConfig


class {app_config_class}(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = '{module_key}'
    verbose_name = '{module_name_title}'
'''

URLS_PY_TEMPLATE = '''from django.urls import path
from {module_key} import views

app_name = '{module_key}'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
]
'''

VIEWS_PY_TEMPLATE = '''from django.views.generic import TemplateView
from core.views import ModuleEnabledRequiredMixin, CompanyBranchScopeMixin


class DashboardView(ModuleEnabledRequiredMixin, CompanyBranchScopeMixin, TemplateView):
    template_name = '{module_key}/dashboard.html'
    module_key = '{module_key}'
'''


class Command(BaseCommand):
    help = "Scaffolds a new modular monolith business module with standard architecture structure."

    def add_arguments(self, parser):
        parser.add_argument('module_name', type=str, help='Name of the module (e.g. accounting, inventory, crm)')

    def handle(self, *args, **options):
        module_key = options['module_name'].lower().strip()
        module_name_title = module_key.replace('_', ' ').title()
        app_config_class = f"{module_key.title().replace('_', '')}Config"

        module_dir = os.path.join(os.getcwd(), module_key)
        if os.path.exists(module_dir):
            raise CommandError(f"Directory '{module_key}' already exists.")

        os.makedirs(module_dir, exist_ok=True)
        os.makedirs(os.path.join(module_dir, 'templates', module_key), exist_ok=True)
        os.makedirs(os.path.join(module_dir, 'tests'), exist_ok=True)
        os.makedirs(os.path.join(module_dir, 'migrations'), exist_ok=True)

        files = {
            '__init__.py': '',
            'apps.py': APPS_PY_TEMPLATE.format(module_key=module_key, module_name_title=module_name_title, app_config_class=app_config_class),
            'module.py': MODULE_PY_TEMPLATE.format(module_key=module_key, module_name_title=module_name_title),
            'api.py': API_PY_TEMPLATE.format(module_key=module_key, module_name_title=module_name_title),
            'handlers.py': HANDLERS_PY_TEMPLATE.format(module_key=module_key, module_name_title=module_name_title),
            'models.py': f'"""\n{module_name_title} Models\n"""\nfrom django.db import models\nfrom core.models import TimeStampedModel, CompanyScopedModel, BranchScopedModel\n',
            'selectors.py': SELECTORS_PY_TEMPLATE.format(module_key=module_key, module_name_title=module_name_title),
            'services.py': SERVICES_PY_TEMPLATE.format(module_key=module_key, module_name_title=module_name_title),
            'forms.py': 'from django import forms\n',
            'views.py': VIEWS_PY_TEMPLATE.format(module_key=module_key),
            'urls.py': URLS_PY_TEMPLATE.format(module_key=module_key),
            'migrations/__init__.py': '',
            'tests/__init__.py': '',
            'tests/test_api.py': f'from django.test import TestCase\nfrom {module_key} import api\n\nclass ApiTest(TestCase):\n    def test_status(self):\n        self.assertTrue(api.get_module_status()[\"is_ready\"])\n',
            f'templates/{module_key}/dashboard.html': f'{{% extends "core/base.html" %}}\n{{% block title %}}{module_name_title}{{% endblock %}}\n{{% block content %}}\n<div class="container-fluid">\n    <h2>{module_name_title}</h2>\n</div>\n{{% endblock %}}\n',
        }

        for rel_path, content in files.items():
            full_path = os.path.join(module_dir, rel_path)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)

        self.stdout.write(self.style.SUCCESS(f"Successfully scaffolded new module '{module_key}'!"))
        self.stdout.write(f"Next steps:\n  1. Add '{module_key}' to INSTALLED_APPS in settings.py\n  2. Include '{module_key}.urls' in root urls.py\n  3. Run: python manage.py makemigrations {module_key}")
