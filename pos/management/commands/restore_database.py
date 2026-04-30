"""
Database and media restore management command
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from pos.backup_security import BackupEncryption, BackupIntegrity
from pos.models import BackupAuditLog, Business
import subprocess
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Restore database and media files from backup'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_file',
            type=str,
            help='Path to the database backup file (.sql for PostgreSQL, .db for SQLite)',
        )
        parser.add_argument(
            '--media-backup',
            type=str,
            help='Path to the media backup file (.tar.gz)',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm restoration (required for safety)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be restored without actually doing it',
        )
        parser.add_argument(
            '--business-id',
            type=int,
            help='Business ID for audit logging (defaults to first business)',
        )
        parser.add_argument(
            '--skip-checksum',
            action='store_true',
            help='Skip checksum verification (not recommended)',
        )

    def handle(self, *args, **options):
        backup_file = options['backup_file']
        media_backup = options.get('media_backup')
        confirm = options['confirm']
        dry_run = options['dry_run']
        skip_checksum = options.get('skip_checksum', False)
        business_id = options.get('business_id')

        if not os.path.exists(backup_file):
            self.stdout.write(self.style.ERROR(f'❌ Backup file not found: {backup_file}'))
            return

        # Get business for audit logging
        business = None
        if business_id:
            try:
                business = Business.objects.get(id=business_id)
            except Business.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'⚠️  Business {business_id} not found'))
        else:
            business = Business.objects.first()

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be made'))
            confirm = True  # Skip confirmation for dry run

        if not confirm:
            self.stdout.write(self.style.WARNING('⚠️  WARNING: This will overwrite existing data!'))
            self.stdout.write('Use --confirm to proceed with restoration.')
            return

        # Handle encrypted backups
        actual_backup_file = backup_file
        if backup_file.endswith('.gpg'):
            self.stdout.write('🔓 Backup is encrypted, decrypting...')
            try:
                encryption = BackupEncryption()
                decrypted_file = backup_file.replace('.gpg', '.decrypted')
                encryption.decrypt_file(backup_file, decrypted_file)
                actual_backup_file = decrypted_file
                self.stdout.write(self.style.SUCCESS('✅ Backup decrypted'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Decryption failed: {e}'))
                logger.error(f'Backup decryption failed: {e}')
                try:
                    BackupAuditLog.log_backup_operation(
                        operation='restore_database',
                        status='failed',
                        user=None,
                        business=business,
                        backup_file=os.path.basename(backup_file),
                        error_message=f'Decryption failed: {e}'
                    )
                except Exception as log_e:
                    logger.warning(f'Audit logging failed: {log_e}')
                return

        # Verify checksum if not skipped
        if not skip_checksum and not backup_file.endswith('.gpg'):
            self.stdout.write('🔍 Verifying backup checksum...')
            try:
                integrity = BackupIntegrity()
                if integrity.verify_checksum(actual_backup_file):
                    self.stdout.write(self.style.SUCCESS('✅ Checksum verified'))
                else:
                    self.stdout.write(self.style.ERROR('❌ Checksum verification failed - backup may be corrupted!'))
                    try:
                        BackupAuditLog.log_backup_operation(
                            operation='restore_database',
                            status='failed',
                            user=None,
                            business=business,
                            backup_file=os.path.basename(backup_file),
                            error_message='Checksum verification failed'
                        )
                    except Exception as log_e:
                        logger.warning(f'Audit logging failed: {log_e}')
                    return
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Checksum verification skipped: {e}'))

        # Create pre-restore backup
        if not dry_run:
            self.create_pre_restore_backup()

        # Restore database
        self.restore_database(actual_backup_file, dry_run, business)

        # Restore media files
        if media_backup:
            self.restore_media(media_backup, dry_run, business)

        # Clean up decrypted temp file
        if actual_backup_file != backup_file and os.path.exists(actual_backup_file):
            try:
                os.remove(actual_backup_file)
                self.stdout.write('🧹 Cleaned up temporary decrypted file')
            except Exception as e:
                logger.warning(f'Failed to clean up temp file: {e}')

        if not dry_run:
            # Log successful restoration
            try:
                BackupAuditLog.log_backup_operation(
                    operation='restore_database',
                    status='success',
                    user=None,
                    business=business,
                    backup_file=os.path.basename(backup_file),
                    details={'restored_at': timezone.now().isoformat()}
                )
            except Exception as log_e:
                logger.warning(f'Audit logging failed: {log_e}')

            self.stdout.write(self.style.SUCCESS('✅ Restoration completed successfully'))
            self.stdout.write(self.style.WARNING('🔄 Please restart your application server'))
        else:
            self.stdout.write(self.style.SUCCESS('🔍 Dry run completed - no changes made'))

    def create_pre_restore_backup(self):
        """Create a backup before restoration"""
        self.stdout.write('📦 Creating pre-restore backup...')
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(settings.BASE_DIR, 'backups', 'pre_restore')
        os.makedirs(backup_dir, exist_ok=True)

        # Quick database backup
        db_settings = settings.DATABASES['default']
        if db_settings['ENGINE'] == 'django.db.backends.postgresql':
            backup_file = os.path.join(backup_dir, f'pre_restore_db_{timestamp}.sql')
            try:
                cmd = [
                    'pg_dump',
                    '-h', db_settings.get('HOST', 'localhost'),
                    '-U', db_settings['USER'],
                    '-d', db_settings['NAME'],
                    '-f', backup_file,
                    '--no-password'
                ]
                env = os.environ.copy()
                env['PGPASSWORD'] = db_settings['PASSWORD']
                subprocess.run(cmd, env=env, check=True)
                self.stdout.write(f'📦 Pre-restore backup: {backup_file}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Pre-restore backup failed: {e}'))

    def restore_database(self, backup_file, dry_run, business=None):
        """Restore database from backup"""
        db_settings = settings.DATABASES['default']

        if dry_run:
            self.stdout.write(f'🔍 Would restore database from: {backup_file}')
            return

        try:
            if db_settings['ENGINE'] == 'django.db.backends.postgresql':
                # PostgreSQL restore
                self.stdout.write('🔄 Restoring PostgreSQL database...')
                cmd = [
                    'psql',
                    '-h', db_settings.get('HOST', 'localhost'),
                    '-U', db_settings['USER'],
                    '-d', db_settings['NAME'],
                    '-f', backup_file,
                    '--no-password'
                ]

                env = os.environ.copy()
                env['PGPASSWORD'] = db_settings['PASSWORD']

                subprocess.run(cmd, env=env, check=True)
                self.stdout.write(self.style.SUCCESS('✅ Database restored'))

            elif db_settings['ENGINE'] == 'django.db.backends.sqlite3':
                # SQLite restore
                self.stdout.write('🔄 Restoring SQLite database...')
                import shutil
                shutil.copy2(backup_file, db_settings['NAME'])
                self.stdout.write(self.style.SUCCESS('✅ SQLite database restored'))

            else:
                self.stdout.write(self.style.ERROR('❌ Database engine not supported for restore'))

        except Exception as e:
            logger.error(f'Database restore failed: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Database restore failed: {e}'))
            try:
                BackupAuditLog.log_backup_operation(
                    operation='restore_database',
                    status='failed',
                    user=None,
                    business=business,
                    backup_file=os.path.basename(backup_file),
                    error_message=str(e)
                )
            except Exception as log_e:
                logger.warning(f'Audit logging failed: {log_e}')
            raise

    def restore_media(self, media_backup, dry_run, business=None):
        """Restore media files from backup"""
        if not os.path.exists(media_backup):
            self.stdout.write(self.style.ERROR(f'❌ Media backup file not found: {media_backup}'))
            return

        if dry_run:
            self.stdout.write(f'🔍 Would restore media from: {media_backup}')
            return

        try:
            self.stdout.write('🔄 Restoring media files...')
            media_root = settings.MEDIA_ROOT

            # Create backup of current media
            if os.path.exists(media_root):
                backup_path = f"{media_root}.backup_{timezone.now().strftime('%Y%m%d_%H%M%S')}"
                os.rename(media_root, backup_path)
                self.stdout.write(f'📦 Current media backed up to: {backup_path}')

            # Extract media backup
            os.makedirs(media_root, exist_ok=True)
            subprocess.run([
                'tar', '-xzf', media_backup, '-C', os.path.dirname(media_root)
            ], check=True)

            self.stdout.write(self.style.SUCCESS('✅ Media files restored'))

            # Log successful media restoration
            try:
                BackupAuditLog.log_backup_operation(
                    operation='restore_media',
                    status='success',
                    user=None,
                    business=business,
                    backup_file=os.path.basename(media_backup),
                    backup_size_mb=os.path.getsize(media_backup) / 1024 / 1024,
                    details={'restored_at': timezone.now().isoformat()}
                )
            except Exception as log_e:
                logger.warning(f'Audit logging failed: {log_e}')

        except Exception as e:
            logger.error(f'Media restore failed: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Media restore failed: {e}'))
            try:
                BackupAuditLog.log_backup_operation(
                    operation='restore_media',
                    status='failed',
                    user=None,
                    business=business,
                    backup_file=os.path.basename(media_backup),
                    error_message=str(e)
                )
            except Exception as log_e:
                logger.warning(f'Audit logging failed: {log_e}')
            raise
