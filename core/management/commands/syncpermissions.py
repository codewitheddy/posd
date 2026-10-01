"""
Management Command: syncpermissions
Syncs module declared permissions and default role templates to Django Groups and Permissions.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from core.registry import module_registry


class Command(BaseCommand):
    help = "Syncs all declared module permissions and default roles to Django Groups and Permissions."

    def add_arguments(self, parser):
        parser.add_argument(
            '--module',
            type=str,
            help='Sync permissions only for a specific module key (e.g. pos, hr)',
        )

    def handle(self, *args, **options):
        module_registry.autodiscover()
        target_module = options.get('module')

        modules = module_registry.get_all()
        if target_module:
            modules = [m for m in modules if m.key == target_module]
            if not modules:
                self.stderr.write(self.style.ERROR(f"Module '{target_module}' not found in registry."))
                return

        total_groups_created = 0
        total_perms_assigned = 0

        for manifest in modules:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\nProcessing Module: {manifest.name} ({manifest.key})"))
            
            if not manifest.default_roles:
                self.stdout.write(f"  No default role templates declared.")
                continue

            for role_name, perm_codenames in manifest.default_roles.items():
                group, created = Group.objects.get_or_create(name=role_name)
                if created:
                    total_groups_created += 1
                    self.stdout.write(self.style.SUCCESS(f"  + Created Group: {role_name}"))
                else:
                    self.stdout.write(f"  = Found Group: {role_name}")

                # Resolve and assign permissions
                assigned_count = 0
                for perm_str in perm_codenames:
                    if '.' in perm_str:
                        app_label, codename = perm_str.split('.', 1)
                        perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
                    else:
                        perm = Permission.objects.filter(codename=perm_str).first()

                    if perm:
                        group.permissions.add(perm)
                        assigned_count += 1
                        total_perms_assigned += 1
                    else:
                        self.stderr.write(self.style.WARNING(f"    ! Permission not found in DB: {perm_str}"))

                self.stdout.write(f"    Attached {assigned_count} permissions to '{role_name}'")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nPermission Sync Complete! Groups Created: {total_groups_created}, Permissions Synced: {total_perms_assigned}"
            )
        )
