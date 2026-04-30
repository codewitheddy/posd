"""
restore/wal.py — SQLite WAL recovery check on startup.

For PostgreSQL deployments (the primary DB) this is a no-op.
For SQLite (local device storage) it completes any pending WAL checkpoint.
"""
import logging

logger = logging.getLogger(__name__)


def check_wal_recovery(sender, **kwargs):
    """
    Called via post_migrate signal in RestoreConfig.ready().
    Completes any pending SQLite WAL checkpoint before the app accepts writes.
    """
    from django.conf import settings as django_settings
    for alias, db_conf in django_settings.DATABASES.items():
        engine = db_conf.get('ENGINE', '')
        if 'sqlite3' not in engine:
            continue
        db_path = db_conf.get('NAME', '')
        if not db_path or db_path == ':memory:':
            continue
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            conn.close()
            logger.info("WAL checkpoint completed for SQLite database: %s", db_path)
        except Exception as exc:
            logger.warning("WAL checkpoint failed for %s: %s", db_path, exc)
