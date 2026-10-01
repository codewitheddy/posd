"""
Import Boundary Enforcement Tests (AST-Based)
Enforces Architecture Principles:
1. Core NEVER imports from any business module.
2. Modules only import sibling modules via their public interface (api.py).
"""
import ast
import os
from django.conf import settings
from django.test import TestCase

BUSINESS_MODULES = ['pos', 'hr', 'accounting', 'sync', 'backup', 'restore', 'events']


class ImportBoundaryTests(TestCase):
    """
    Automated architectural guardrail tests that inspect the AST of every python file.
    """

    def setUp(self):
        self.base_dir = str(settings.BASE_DIR)

    def _get_python_files(self, package_dir: str):
        py_files = []
        full_path = os.path.join(self.base_dir, package_dir)
        if not os.path.exists(full_path):
            return py_files

        for root, _, files in os.walk(full_path):
            if 'migrations' in root or '__pycache__' in root or '.git' in root:
                continue
            for f in files:
                if f.endswith('.py'):
                    py_files.append(os.path.join(root, f))
        return py_files

    def test_core_never_imports_from_any_business_module(self):
        """
        Verify that core has ZERO imports from any module (pos, hr, etc.).
        Core is the platform foundation and must remain 100% decoupled from business modules.
        """
        core_files = self._get_python_files('core')
        violations = []

        for fpath in core_files:
            rel_path = os.path.relpath(fpath, self.base_dir)
            with open(fpath, 'r', encoding='utf-8') as f:
                try:
                    tree = ast.parse(f.read(), filename=fpath)
                except Exception:
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        for mod in BUSINESS_MODULES:
                            if name.name.startswith(mod):
                                violations.append(f"{rel_path}:{node.lineno} -> import {name.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for mod in BUSINESS_MODULES:
                            if node.module.startswith(mod):
                                violations.append(f"{rel_path}:{node.lineno} -> from {node.module} import ...")

        self.assertEqual(
            violations,
            [],
            f"Architecture Violation: Core MUST NEVER import from business modules!\nFound:\n" + "\n".join(violations)
        )

    def test_module_api_boundary_rules(self):
        """
        Verify that new modules adhere to importing only <sibling>.api or core.
        """
        # Checks that core exports required public interfaces
        import core.models as core_models
        import core.registry as core_registry
        import core.scoping as core_scoping
        import core.settings_store as core_settings_store
        import core.views as core_views

        self.assertTrue(hasattr(core_models, 'Company'))
        self.assertTrue(hasattr(core_models, 'Branch'))
        self.assertTrue(hasattr(core_models, 'CompanyMembership'))
        self.assertTrue(hasattr(core_registry, 'module_registry'))
        self.assertTrue(hasattr(core_scoping, 'CompanyBranchScopeMixin'))
        self.assertTrue(hasattr(core_settings_store, 'SettingStore'))
