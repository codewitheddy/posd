"""
Terminal Sync Module Manifest
"""
from core.registry import ModuleManifest


manifest = ModuleManifest(
    key='sync',
    name='Terminal Synchronization',
    version='1.0.0',
    description='Bidirectional event replication and conflict resolution for offline POS mobile/hardware registers.',
    icon='bi bi-arrow-repeat',
    dependencies=['pos'],
    permission_prefix='sync',
    url_prefix='/api/v1/sync/',
)
