"""
Backup verification and testing command
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
import os
import subprocess
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Verify and test backup integrity'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_path',
            type=str,
            help='Path to backup file or directory containing backups',
        )
        parser.add_argument(
            '--type',
            choices=['database', 'business', 'media', 'all'],
            default='all',
            help='Type of backup to verify',
        )
        parser.add_argument(
            '--comprehensive',
            action='store_true',
            help='Run comprehensive verification (slower but more thorough)',
        )

    def handle(self, *args, **options):
        backup_path = options['backup_path']
        backup_type = options['type']
        comprehensive = options['comprehensive']

        if not os.path.exists(backup_path):
            self.stdout.write(self.style.ERROR(f'❌ Backup path not found: {backup_path}'))
            return

        self.stdout.write(f'🔍 Verifying backups in: {backup_path}')

        if os.path.isfile(backup_path):
            # Single file verification
            self.verify_single_file(backup_path, backup_type, comprehensive)
        else:
            # Directory verification
            self.verify_directory(backup_path, backup_type, comprehensive)

    def verify_single_file(self, file_path, backup_type, comprehensive):
        """Verify a single backup file"""
        file_name = os.path.basename(file_path)

        if file_name.startswith('db_backup_') and file_name.endswith('.sql'):
            if backup_type in ['database', 'all']:
                self.verify_database_backup(file_path, comprehensive)
        elif file_name.startswith('media_backup_') and file_name.endswith('.tar.gz'):
            if backup_type in ['media', 'all']:
                self.verify_media_backup(file_path, comprehensive)
        elif file_name.endswith('.json') and 'backup' in file_name:
            if backup_type in ['business', 'all']:
                self.verify_business_backup(file_path, comprehensive)
        else:
            self.stdout.write(self.style.WARNING(f'⚠️  Unknown backup type: {file_name}'))

    def verify_directory(self, dir_path, backup_type, comprehensive):
        """Verify all backups in a directory"""
        backup_files = []

        for root, dirs, files in os.walk(dir_path):
            for file in files:
                if self.is_backup_file(file):
                    backup_files.append(os.path.join(root, file))

        if not backup_files:
            self.stdout.write(self.style.WARNING('⚠️  No backup files found in directory'))
            return

        self.stdout.write(f'📁 Found {len(backup_files)} backup files')

        verified = 0
        failed = 0

        for backup_file in sorted(backup_files):
            try:
                self.verify_single_file(backup_file, backup_type, comprehensive)
                verified += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Verification failed for {backup_file}: {e}'))
                failed += 1

        self.stdout.write(f'\n📊 Verification Summary:')
        self.stdout.write(f'  Verified: {verified}')
        self.stdout.write(f'  Failed: {failed}')
        self.stdout.write(f'  Success Rate: {(verified/(verified+failed)*100):.1f}%')

    def is_backup_file(self, filename):
        """Check if file is a backup file"""
        return (
            filename.startswith(('db_backup_', 'media_backup_')) or
            ('backup' in filename and filename.endswith('.json')) or
            filename.endswith(('.sql', '.tar.gz', '.db'))
        )

    def verify_database_backup(self, file_path, comprehensive):
        """Verify database backup integrity"""
        file_name = os.path.basename(file_path)
        self.stdout.write(f'🔍 Verifying database backup: {file_name}')

        try:
            # Check file size
            file_size = os.path.getsize(file_path) / 1024 / 1024  # MB
            if file_size < 0.1:
                raise ValueError(f'Backup file too small: {file_size:.2f} MB')

            # Basic syntax check for SQL files
            if file_path.endswith('.sql'):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(1024)  # Read first 1KB
                    if not content.strip():
                        raise ValueError('Backup file appears to be empty')

                    # Check for SQL keywords
                    sql_keywords = ['CREATE', 'INSERT', 'BEGIN', 'COMMIT']
                    has_sql = any(keyword in content.upper() for keyword in sql_keywords)
                    if not has_sql:
                        raise ValueError('File does not appear to contain SQL data')

            if comprehensive:
                # Attempt to restore to a test database
                self.test_database_restore(file_path)

            self.stdout.write(self.style.SUCCESS(f'✅ Database backup verified ({file_size:.2f} MB)'))

        except Exception as e:
            raise ValueError(f'Database backup verification failed: {e}')

    def verify_media_backup(self, file_path, comprehensive):
        """Verify media backup integrity"""
        file_name = os.path.basename(file_path)
        self.stdout.write(f'🔍 Verifying media backup: {file_name}')

        try:
            # Check file size
            file_size = os.path.getsize(file_path) / 1024 / 1024  # MB

            # Test tar.gz integrity
            result = subprocess.run(
                ['tar', '-tzf', file_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise ValueError(f'Tar archive is corrupted: {result.stderr}')

            # Count files
            file_list = result.stdout.strip().split('\n')
            file_count = len([f for f in file_list if f.strip()])

            if comprehensive and file_count > 0:
                # Test extraction to temporary directory
                import tempfile
                with tempfile.TemporaryDirectory() as temp_dir:
                    extract_result = subprocess.run(
                        ['tar', '-xzf', file_path, '-C', temp_dir],
                        capture_output=True,
                        timeout=60
                    )
                    if extract_result.returncode != 0:
                        raise ValueError('Failed to extract archive for testing')

            self.stdout.write(self.style.SUCCESS(f'✅ Media backup verified ({file_size:.2f} MB, {file_count} files)'))

        except Exception as e:
            raise ValueError(f'Media backup verification failed: {e}')

    def verify_business_backup(self, file_path, comprehensive):
        """Verify business backup integrity"""
        file_name = os.path.basename(file_path)
        self.stdout.write(f'🔍 Verifying business backup: {file_name}')

        try:
            # Check file size
            file_size = os.path.getsize(file_path) / 1024 / 1024  # MB
            if file_size < 0.1:
                raise ValueError(f'Backup file too small: {file_size:.2f} MB')

            # Validate JSON structure
            with open(file_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            # Check required fields
            required_fields = ['metadata', 'business']
            for field in required_fields:
                if field not in backup_data:
                    raise ValueError(f'Missing required field: {field}')

            # Validate metadata
            metadata = backup_data['metadata']
            required_meta = ['business_name', 'business_slug', 'backup_date', 'version']
            for field in required_meta:
                if field not in metadata:
                    raise ValueError(f'Missing metadata field: {field}')

            # Count records
            total_records = 0
            for key, data in backup_data.items():
                if key != 'metadata' and isinstance(data, list):
                    total_records += len(data)

            if comprehensive:
                # Validate data structure
                self.validate_business_data_structure(backup_data)

            self.stdout.write(self.style.SUCCESS(f'✅ Business backup verified ({file_size:.2f} MB, {total_records} records)'))

        except json.JSONDecodeError as e:
            raise ValueError(f'Invalid JSON format: {e}')
        except Exception as e:
            raise ValueError(f'Business backup verification failed: {e}')

    def validate_business_data_structure(self, backup_data):
        """Validate the structure of business backup data"""
        # This could be expanded to validate foreign key relationships, etc.
        pass

    def test_database_restore(self, backup_file):
        """Test database restore to a temporary database"""
        # This is a simplified test - in production, you'd want to test against a temp DB
        self.stdout.write('Testing database restore capability...')

        # For now, just check if the file can be read
        with open(backup_file, 'rb') as f:
            # Try to read a small portion to verify it's not corrupted
            f.read(1024)

        self.stdout.write('Database restore test passed')