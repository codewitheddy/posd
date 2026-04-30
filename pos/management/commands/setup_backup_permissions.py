"""
Create backup_admin permission group with required permissions
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from pos.models import BackupAuditLog
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Create backup_admin permission group for backup/restore operations'

    def handle(self, *args, **options):
        # Create or get the backup_admin group
        group, created = Group.objects.get_or_create(name='backup_admin')

        if created:
            self.stdout.write(self.style.SUCCESS('✅ Created backup_admin group'))
        else:
            self.stdout.write('ℹ️  backup_admin group already exists')

        # Get BackupAuditLog content type
        try:
            content_type = ContentType.objects.get_for_model(BackupAuditLog)

            # Define permissions needed for backup operations
            permissions_to_add = [
                'view_backupauditlog',      # Can view audit logs
                'add_backupauditlog',       # Can create audit log entries
                'change_backupauditlog',    # Can modify audit logs (if needed)
                'delete_backupauditlog',    # Can delete old audit logs
            ]

            # Add permissions to group
            added_permissions = []
            for perm_codename in permissions_to_add:
                try:
                    permission = Permission.objects.get(
                        content_type=content_type,
                        codename=perm_codename
                    )
                    group.permissions.add(permission)
                    added_permissions.append(perm_codename)
                except Permission.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  Permission {perm_codename} not found')
                    )

            if added_permissions:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Added {len(added_permissions)} permissions to backup_admin group'
                    )
                )
                for perm in added_permissions:
                    self.stdout.write(f'  • pos.{perm}')

            # Also add permissions for related models (optional but useful)
            try:
                # Add permission to view Business model
                from pos.models import Business
                business_content_type = ContentType.objects.get_for_model(Business)
                business_perm = Permission.objects.get(
                    content_type=business_content_type,
                    codename='view_business'
                )
                group.permissions.add(business_perm)
                self.stdout.write('  • pos.view_business (for audit context)')
            except Exception as e:
                logger.warning(f'Could not add Business view permission: {e}')

            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✅ backup_admin group setup complete'))
            self.stdout.write('')
            self.stdout.write('To add users to this group:')
            self.stdout.write('  python manage.py addgroups user_email backup_admin')
            self.stdout.write('')

        except Exception as e:
            logger.error(f'Error setting up backup_admin group: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))
