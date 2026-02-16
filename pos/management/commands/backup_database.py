"""
Database and media backup management command
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
import subprocess
import os
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Backup database and media files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--upload',
            action='store_true',
            help='Upload backup to cloud storage (if configured)',
        )

    def handle(self, *args, **options):
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        # Backup database
        db_backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.sql')
        self.backup_database(db_backup_file)

        # Backup media files
        media_backup_file = os.path.join(backup_dir, f'media_backup_{timestamp}.tar.gz')
        self.backup_media(media_backup_file)

        # Cleanup old backups (keep last 30 days)
        self.cleanup_old_backups(backup_dir, days=30)

        self.stdout.write(self.style.SUCCESS(f'✅ Backup completed: {timestamp}'))
        self.stdout.write(f'  Database: {db_backup_file}')
        self.stdout.write(f'  Media: {media_backup_file}')

    def backup_database(self, output_file):
        """Backup database"""
        db_settings = settings.DATABASES['default']
        
        try:
            if db_settings['ENGINE'] == 'django.db.backends.postgresql':
                # PostgreSQL backup
                cmd = [
                    'pg_dump',
                    '-h', db_settings.get('HOST', 'localhost'),
                    '-U', db_settings['USER'],
                    '-d', db_settings['NAME'],
                    '-f', output_file,
                    '--no-password'
                ]
                
                env = os.environ.copy()
                env['PGPASSWORD'] = db_settings['PASSWORD']
                
                subprocess.run(cmd, env=env, check=True)
                self.stdout.write(self.style.SUCCESS(f'✅ Database backed up'))
            
            elif db_settings['ENGINE'] == 'django.db.backends.sqlite3':
                # SQLite backup
                import shutil
                shutil.copy2(db_settings['NAME'], output_file)
                self.stdout.write(self.style.SUCCESS(f'✅ SQLite database backed up'))
            
            else:
                self.stdout.write(self.style.WARNING('⚠️  Database engine not supported for backup'))
        
        except Exception as e:
            logger.error(f'Database backup failed: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Database backup failed: {e}'))

    def backup_media(self, output_file):
        """Backup media files"""
        try:
            media_root = settings.MEDIA_ROOT
            if os.path.exists(media_root) and os.listdir(media_root):
                subprocess.run([
                    'tar', '-czf', output_file, '-C', 
                    os.path.dirname(media_root),
                    os.path.basename(media_root)
                ], check=True)
                
                file_size = os.path.getsize(output_file) / 1024 / 1024  # MB
                self.stdout.write(self.style.SUCCESS(f'✅ Media files backed up ({file_size:.2f} MB)'))
            else:
                self.stdout.write(self.style.WARNING('⚠️  No media files to backup'))
        
        except Exception as e:
            logger.error(f'Media backup failed: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Media backup failed: {e}'))

    def cleanup_old_backups(self, backup_dir, days=30):
        """Remove backups older than specified days"""
        import time
        now = time.time()
        cutoff = now - (days * 86400)
        removed_count = 0

        for filename in os.listdir(backup_dir):
            file_path = os.path.join(backup_dir, filename)
            if os.path.isfile(file_path):
                if os.path.getmtime(file_path) < cutoff:
                    os.remove(file_path)
                    removed_count += 1

        if removed_count > 0:
            self.stdout.write(f'🗑️  Removed {removed_count} old backup(s)')
