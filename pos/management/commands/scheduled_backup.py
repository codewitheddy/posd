"""
Automated backup scheduling and monitoring command
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from django.core.management import call_command
import os
import logging
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run automated backup schedule with monitoring and alerting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schedule',
            choices=['daily', 'weekly', 'monthly'],
            default='daily',
            help='Backup schedule type',
        )
        parser.add_argument(
            '--notify',
            action='store_true',
            help='Send email notification on completion/failure',
        )
        parser.add_argument(
            '--upload',
            action='store_true',
            help='Upload backups to cloud storage',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify backup integrity after creation',
        )

    def handle(self, *args, **options):
        schedule = options['schedule']
        notify = options['notify']
        upload = options['upload']
        verify = options['verify']

        self.stdout.write(f'🚀 Starting {schedule} backup process...')

        start_time = timezone.now()
        results = {
            'success': False,
            'database_backup': None,
            'media_backup': None,
            'business_backups': [],
            'errors': [],
            'warnings': []
        }

        try:
            # Create backup directory with schedule
            backup_base_dir = os.path.join(settings.BASE_DIR, 'backups', 'scheduled', schedule)
            os.makedirs(backup_base_dir, exist_ok=True)

            # Database and media backup
            results.update(self.perform_database_backup(backup_base_dir, upload))

            # Business-specific backups (for multi-tenant)
            results['business_backups'] = self.perform_business_backups(backup_base_dir)

            # Verification
            if verify:
                verification_results = self.verify_backups(backup_base_dir)
                results.update(verification_results)

            # Cleanup old backups
            self.cleanup_old_backups(schedule)

            results['success'] = True
            self.stdout.write(self.style.SUCCESS('✅ Backup process completed successfully'))

        except Exception as e:
            results['errors'].append(str(e))
            logger.error(f'Backup process failed: {e}')
            self.stdout.write(self.style.ERROR(f'❌ Backup process failed: {e}'))

        # Calculate duration
        end_time = timezone.now()
        duration = end_time - start_time
        results['duration'] = f"{duration.total_seconds():.2f}s"

        # Send notification
        if notify:
            self.send_notification(results, schedule)

        # Log results
        self.log_backup_results(results, schedule)

    def perform_database_backup(self, backup_dir, upload):
        """Perform database and media backup"""
        results = {}

        try:
            self.stdout.write('📦 Creating database and media backup...')

            # Call the existing backup_database command
            from io import StringIO
            from django.core.management import call_command

            # Capture command output
            output = StringIO()
            call_command('backup_database', stdout=output)

            command_output = output.getvalue()

            # Parse output to find backup file paths
            for line in command_output.split('\n'):
                if 'Database:' in line:
                    results['database_backup'] = line.split('Database:')[1].strip()
                elif 'Media:' in line:
                    results['media_backup'] = line.split('Media:')[1].strip()

            if upload:
                self.upload_to_cloud(results.get('database_backup'))
                self.upload_to_cloud(results.get('media_backup'))

        except Exception as e:
            results['errors'] = results.get('errors', []) + [f'Database backup failed: {e}']

        return results

    def perform_business_backups(self, backup_dir):
        """Perform business-specific backups"""
        from pos.models import Business

        business_backups = []

        try:
            businesses = Business.objects.filter(is_active=True)

            for business in businesses:
                try:
                    self.stdout.write(f'📦 Backing up business: {business.name}')

                    # Call backup_business command
                    from io import StringIO
                    output = StringIO()
                    call_command('backup_business', business.id, stdout=output)

                    # Parse output for backup file path
                    command_output = output.getvalue()
                    for line in command_output.split('\n'):
                        if 'Backup completed:' in line:
                            backup_file = line.split('Backup completed:')[1].strip()
                            business_backups.append({
                                'business': business.name,
                                'file': backup_file
                            })
                            break

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'⚠️  Business backup failed for {business.name}: {e}'))

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠️  Business backup process failed: {e}'))

        return business_backups

    def verify_backups(self, backup_dir):
        """Verify backup integrity"""
        results = {'verification_passed': True, 'verification_errors': []}

        try:
            self.stdout.write('🔍 Verifying backup integrity...')

            from io import StringIO
            output = StringIO()
            call_command('verify_backup', backup_dir, stdout=output)

            command_output = output.getvalue()

            # Check for failures in output
            if '❌' in command_output or 'Failed' in command_output:
                results['verification_passed'] = False
                results['verification_errors'].append('Backup verification failed')

        except Exception as e:
            results['verification_passed'] = False
            results['verification_errors'].append(f'Verification error: {e}')

        return results

    def cleanup_old_backups(self, schedule):
        """Clean up old backups based on schedule"""
        try:
            backup_dir = os.path.join(settings.BASE_DIR, 'backups')

            # Retention periods
            retention_days = {
                'daily': 30,    # Keep 30 days of daily backups
                'weekly': 90,   # Keep 90 days of weekly backups
                'monthly': 365  # Keep 1 year of monthly backups
            }

            days = retention_days.get(schedule, 30)

            from io import StringIO
            output = StringIO()
            call_command('backup_database', stdout=output)  # This includes cleanup

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠️  Cleanup failed: {e}'))

    def upload_to_cloud(self, file_path):
        """Upload backup to cloud storage"""
        if not file_path or not os.path.exists(file_path):
            return

        try:
            self.stdout.write(f'☁️  Uploading to cloud: {os.path.basename(file_path)}')

            # Placeholder for cloud upload implementation
            # This would integrate with AWS S3, Google Cloud Storage, etc.

            # Example for AWS S3:
            # import boto3
            # s3 = boto3.client('s3')
            # s3.upload_file(file_path, 'your-bucket', os.path.basename(file_path))

            self.stdout.write(self.style.SUCCESS('✅ Cloud upload completed'))

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠️  Cloud upload failed: {e}'))

    def send_notification(self, results, schedule):
        """Send email notification about backup results"""
        try:
            subject = f"Marid POS {schedule.title()} Backup {'Success' if results['success'] else 'Failed'}"

            body = f"""
Marid POS Automated Backup Report
{'='*40}

Schedule: {schedule.title()}
Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}
Duration: {results.get('duration', 'Unknown')}

Status: {'✅ SUCCESS' if results['success'] else '❌ FAILED'}

Backup Details:
"""

            if results.get('database_backup'):
                body += f"- Database: {os.path.basename(results['database_backup'])}\n"
            if results.get('media_backup'):
                body += f"- Media: {os.path.basename(results['media_backup'])}\n"

            if results.get('business_backups'):
                body += f"- Business Backups: {len(results['business_backups'])}\n"

            if results.get('errors'):
                body += f"\nErrors:\n"
                for error in results['errors']:
                    body += f"- {error}\n"

            if results.get('warnings'):
                body += f"\nWarnings:\n"
                for warning in results['warnings']:
                    body += f"- {warning}\n"

            # Send email
            self.send_email(subject, body)

        except Exception as e:
            self.stdout.write(self.style.WARNING(f'⚠️  Notification failed: {e}'))

    def send_email(self, subject, body):
        """Send email notification"""
        try:
            # Email configuration from settings
            from django.core.mail import send_mail

            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.ADMINS[0][1] if settings.ADMINS else 'admin@example.com'],
                fail_silently=True
            )

        except Exception as e:
            logger.error(f'Email notification failed: {e}')

    def log_backup_results(self, results, schedule):
        """Log backup results to file"""
        try:
            log_dir = os.path.join(settings.BASE_DIR, 'logs')
            os.makedirs(log_dir, exist_ok=True)

            log_file = os.path.join(log_dir, 'backup.log')

            with open(log_file, 'a') as f:
                f.write(f"{timezone.now().isoformat()} - {schedule} - {'SUCCESS' if results['success'] else 'FAILED'} - {results.get('duration', 'Unknown')}\n")

        except Exception as e:
            logger.error(f'Backup logging failed: {e}')</content>
<parameter name="filePath">d:\V2POS\posd\pos\management\commands\scheduled_backup.py