"""
Backup & Disaster Recovery Module Manifest
"""
from core.registry import ModuleManifest, MenuSection, MenuItem


manifest = ModuleManifest(
    key='backup',
    name='Backup & Disaster Recovery',
    version='1.0.0',
    description='Automated encrypted database snapshots, off-site replication, and point-in-time recovery.',
    icon='bi bi-shield-check',
    dependencies=[],
    permission_prefix='backup',
    menu_sections=[
        MenuSection(
            title='System & Backups',
            order=90,
            items=[
                MenuItem(
                    title='Backup Snapshots',
                    url_name='backup:backup_dashboard',
                    icon='bi bi-cloud-arrow-up',
                ),
            ],
        ),
    ],
    url_prefix='/settings/backup/',
)
