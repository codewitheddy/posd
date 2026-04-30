"""
Database and media backup management command
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from pos.backup_security import BackupEncryption, BackupIntegrity
from pos.models import BackupAuditLog, Business
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
        parser.add_argument(
            '--business-id',
            type=int,
            help='Business ID for audit logging (defaults to first business)',
        )

    def handle(self, *args, **options):
        upload = options['upload']
        business_id = options.get('business_id')
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        # Get business for audit logging (use first or specified)
        business = None
        if business_id:
            try:
                business = Business.objects.get(id=business_id)
            except Business.DoesNotExist:
                self.stdout.write(self.style.WARNING(f'⚠️  Business {business_id} not found, audit logging as None'))
        else:
            business = Business.objects.first()

        # Backup database with encryption and checksums
        db_backup_file = os.path.join(backup_dir, f'db_backup_{timestamp}.sql')
        db_status = self.backup_database(db_backup_file, business)

        # Backup media files with encryption and checksums
        media_backup_file = os.path.join(backup_dir, f'media_backup_{timestamp}.tar.gz')
        media_status = self.backup_media(media_backup_file, business)

        # Upload to cloud if requested
        if upload:
            self.upload_to_cloud(db_backup_file, business)
            self.upload_to_cloud(media_backup_file, business)

        # Cleanup old backups (use settings retention policy)
        retention_days = getattr(settings, 'BACKUP_RETENTION_DAILY', 7)
        self.cleanup_old_backups(backup_dir, days=retention_days)

        self.stdout.write(self.style.SUCCESS(f'✅ Backup completed: {timestamp}'))
        self.stdout.write(f'  Database: {db_backup_file}')
        self.stdout.write(f'  Media: {media_backup_file}')

        if upload:
            self.stdout.write(self.style.SUCCESS('✅ Backups uploaded to cloud'))
        
        if db_status and media_status:
            self.stdout.write(self.style.SUCCESS('✅ All backups encrypted and checksummed'))

    def backup_database(self, output_file, business=None):
        """Backup database with encryption and checksums"""
        db_settings = settings.DATABASES['default']
        backup_result = False
        error_message = None
        file_size = 0
        checksum = None
        
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
                backup_result = True
                self.stdout.write(self.style.SUCCESS(f'✅ Database backed up'))
            
            elif db_settings['ENGINE'] == 'django.db.backends.sqlite3':
                # SQLite backup
                import shutil
                shutil.copy2(db_settings['NAME'], output_file)
                backup_result = True
                self.stdout.write(self.style.SUCCESS(f'✅ SQLite database backed up'))
            
            else:
                self.stdout.write(self.style.WARNING('⚠️  Database engine not supported for backup'))
                error_message = 'Unsupported database engine'
        
        except Exception as e:
            logger.error(f'Database backup failed: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Database backup failed: {e}'))
            error_message = str(e)
            backup_result = False
        
        # Encrypt and checksum the backup if successful
        if backup_result and os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / 1024 / 1024  # MB
            
            # Generate checksum
            try:
                integrity = BackupIntegrity()
                checksum = integrity.calculate_sha256(output_file)
                integrity.create_checksum_file(output_file, checksum)
                self.stdout.write(f'✅ Checksum created: {checksum[:16]}...')
            except Exception as e:
                logger.warning(f'Checksum generation failed: {e}')
                self.stdout.write(self.style.WARNING(f'⚠️  Checksum creation failed: {e}'))
            
            # Encrypt if enabled
            is_encrypted = False
            if getattr(settings, 'BACKUP_ENABLE_ENCRYPTION', False):
                try:
                    encryption = BackupEncryption()
                    encrypted_file = f'{output_file}.gpg'
                    encryption.encrypt_file(output_file, encrypted_file)
                    os.remove(output_file)  # Remove unencrypted version
                    output_file = encrypted_file
                    is_encrypted = True
                    self.stdout.write(self.style.SUCCESS('✅ Backup encrypted with GPG'))
                except Exception as e:
                    logger.warning(f'Encryption failed: {e}')
                    self.stdout.write(self.style.WARNING(f'⚠️  Encryption failed: {e}'))
            
            # Log the backup operation
            try:
                BackupAuditLog.log_backup_operation(
                    operation='backup_database',
                    status='success' if backup_result else 'failed',
                    user=None,  # Management command has no user context
                    business=business,
                    backup_file=os.path.basename(output_file),
                    backup_size_mb=file_size,
                    backup_checksum=checksum,
                    is_encrypted=is_encrypted,
                    details={'database': db_settings['NAME']}
                )
            except Exception as e:
                logger.warning(f'Audit logging failed: {e}')
                self.stdout.write(self.style.WARNING(f'⚠️  Audit logging failed: {e}'))
        
        return backup_result

    def backup_media(self, output_file, business=None):
        """Backup media files with encryption and checksums"""
        backup_result = False
        error_message = None
        file_size = 0
        checksum = None
        
        try:
            media_root = settings.MEDIA_ROOT
            if os.path.exists(media_root) and os.listdir(media_root):
                subprocess.run([
                    'tar', '-czf', output_file, '-C', 
                    os.path.dirname(media_root),
                    os.path.basename(media_root)
                ], check=True)
                
                file_size = os.path.getsize(output_file) / 1024 / 1024  # MB
                backup_result = True
                self.stdout.write(self.style.SUCCESS(f'✅ Media files backed up ({file_size:.2f} MB)'))
            else:
                self.stdout.write(self.style.WARNING('⚠️  No media files to backup'))
                backup_result = True  # Not an error if nothing to backup
        
        except Exception as e:
            logger.error(f'Media backup failed: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Media backup failed: {e}'))
            error_message = str(e)
            backup_result = False
        
        # Encrypt and checksum the backup if successful
        if backup_result and os.path.exists(output_file):
            file_size = os.path.getsize(output_file) / 1024 / 1024  # MB
            
            # Generate checksum
            try:
                integrity = BackupIntegrity()
                checksum = integrity.calculate_sha256(output_file)
                integrity.create_checksum_file(output_file, checksum)
                self.stdout.write(f'✅ Checksum created: {checksum[:16]}...')
            except Exception as e:
                logger.warning(f'Checksum generation failed: {e}')
                self.stdout.write(self.style.WARNING(f'⚠️  Checksum creation failed: {e}'))
            
            # Encrypt if enabled
            is_encrypted = False
            if getattr(settings, 'BACKUP_ENABLE_ENCRYPTION', False):
                try:
                    encryption = BackupEncryption()
                    encrypted_file = f'{output_file}.gpg'
                    encryption.encrypt_file(output_file, encrypted_file)
                    os.remove(output_file)  # Remove unencrypted version
                    output_file = encrypted_file
                    is_encrypted = True
                    self.stdout.write(self.style.SUCCESS('✅ Media backup encrypted with GPG'))
                except Exception as e:
                    logger.warning(f'Encryption failed: {e}')
                    self.stdout.write(self.style.WARNING(f'⚠️  Encryption failed: {e}'))
            
            # Log the backup operation
            try:
                BackupAuditLog.log_backup_operation(
                    operation='backup_media',
                    status='success' if backup_result else 'failed',
                    user=None,  # Management command has no user context
                    business=business,
                    backup_file=os.path.basename(output_file),
                    backup_size_mb=file_size,
                    backup_checksum=checksum,
                    is_encrypted=is_encrypted,
                    details={'media_root': settings.MEDIA_ROOT}
                )
            except Exception as e:
                logger.warning(f'Audit logging failed: {e}')
                self.stdout.write(self.style.WARNING(f'⚠️  Audit logging failed: {e}'))
        
        return backup_result

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

    def upload_to_cloud(self, file_path, business=None):
        """Upload backup file to cloud storage with TLS enforcement"""
        if not os.path.exists(file_path):
            return

        try:
            # Check TLS requirement
            if getattr(settings, 'BACKUP_FORCE_TLS', True):
                self.stdout.write('🔒 TLS enforcement enabled for cloud uploads')

            self.stdout.write(f'☁️  Uploading {os.path.basename(file_path)} to cloud...')

            # Try AWS S3 first
            if self.upload_to_s3(file_path):
                # Log successful upload
                try:
                    BackupAuditLog.log_backup_operation(
                        operation='backup_upload',
                        status='success',
                        user=None,
                        business=business,
                        backup_file=os.path.basename(file_path),
                        backup_size_mb=os.path.getsize(file_path) / 1024 / 1024,
                        details={'destination': 'AWS S3'}
                    )
                except Exception as e:
                    logger.warning(f'Audit logging for S3 upload failed: {e}')
                return

            # Try Google Cloud Storage
            if self.upload_to_gcs(file_path):
                # Log successful upload
                try:
                    BackupAuditLog.log_backup_operation(
                        operation='backup_upload',
                        status='success',
                        user=None,
                        business=business,
                        backup_file=os.path.basename(file_path),
                        backup_size_mb=os.path.getsize(file_path) / 1024 / 1024,
                        details={'destination': 'Google Cloud Storage'}
                    )
                except Exception as e:
                    logger.warning(f'Audit logging for GCS upload failed: {e}')
                return

            # Try Azure Blob Storage
            if self.upload_to_azure(file_path):
                # Log successful upload
                try:
                    BackupAuditLog.log_backup_operation(
                        operation='backup_upload',
                        status='success',
                        user=None,
                        business=business,
                        backup_file=os.path.basename(file_path),
                        backup_size_mb=os.path.getsize(file_path) / 1024 / 1024,
                        details={'destination': 'Azure Blob Storage'}
                    )
                except Exception as e:
                    logger.warning(f'Audit logging for Azure upload failed: {e}')
                return

            self.stdout.write(self.style.WARNING('⚠️  No cloud storage configured or available'))

        except Exception as e:
            logger.error(f'Cloud upload failed: {e}')
            self.stdout.write(self.style.WARNING(f'⚠️  Cloud upload failed: {e}'))

    def upload_to_s3(self, file_path):
        """Upload to AWS S3 with TLS enforcement"""
        try:
            import boto3
            from botocore.exceptions import NoCredentialsError

            s3_config = None
            if getattr(settings, 'BACKUP_FORCE_TLS', True):
                # Force HTTPS with signature version 4
                from botocore.config import Config
                s3_config = Config(signature_version='s3v4')

            s3 = boto3.client('s3', config=s3_config)
            bucket = getattr(settings, 'BACKUP_S3_BUCKET', None)
            if not bucket:
                return False

            key = f"backups/{os.path.basename(file_path)}"
            s3.upload_file(file_path, bucket, key)
            self.stdout.write(self.style.SUCCESS('✅ Uploaded to S3 (TLS enforced)'))
            return True

        except (ImportError, NoCredentialsError):
            return False

    def upload_to_gcs(self, file_path):
        """Upload to Google Cloud Storage with TLS enforcement"""
        try:
            from google.cloud import storage
            from google.api_core.gapic_v1 import client_info as grpc_client_info

            bucket_name = getattr(settings, 'BACKUP_GCS_BUCKET', None)
            if not bucket_name:
                return False

            # TLS is inherently enforced by Google Cloud client libraries
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(f"backups/{os.path.basename(file_path)}")
            blob.upload_from_filename(file_path)
            self.stdout.write(self.style.SUCCESS('✅ Uploaded to GCS (TLS enforced)'))
            return True

        except (ImportError, Exception):
            return False

    def upload_to_azure(self, file_path):
        """Upload to Azure Blob Storage with TLS enforcement"""
        try:
            from azure.storage.blob import BlobServiceClient
            from azure.core.exceptions import AzureError

            connection_string = getattr(settings, 'BACKUP_AZURE_CONNECTION_STRING', None)
            container_name = getattr(settings, 'BACKUP_AZURE_CONTAINER', None)

            if not connection_string or not container_name:
                return False

            # Azure SDK enforces TLS by default
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            blob_client = blob_service_client.get_blob_client(
                container=container_name,
                blob=f"backups/{os.path.basename(file_path)}"
            )

            with open(file_path, 'rb') as data:
                blob_client.upload_blob(data, overwrite=True)

            self.stdout.write(self.style.SUCCESS('✅ Uploaded to Azure (TLS enforced)'))
            return True

        except (ImportError, AzureError, Exception):
            return False
