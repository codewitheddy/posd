"""
Backup monitoring and health check command
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
import os
import logging
from pathlib import Path
from datetime import timedelta

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Monitor backup health and generate reports'

    def add_arguments(self, parser):
        parser.add_argument(
            '--report',
            action='store_true',
            help='Generate detailed backup report',
        )
        parser.add_argument(
            '--alert',
            action='store_true',
            help='Send alerts for backup issues',
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix common backup issues',
        )

    def handle(self, *args, **options):
        generate_report = options['report']
        send_alerts = options['alert']
        auto_fix = options['fix']

        self.stdout.write('🔍 Monitoring backup health...')

        # Analyze backup directory structure
        backup_base = os.path.join(settings.BASE_DIR, 'backups')
        if not os.path.exists(backup_base):
            self.stdout.write(self.style.ERROR('❌ Backup directory not found'))
            return

        # Collect backup statistics
        stats = self.analyze_backup_directory(backup_base)

        # Check backup health
        health_issues = self.check_backup_health(stats)

        # Generate report
        if generate_report:
            self.generate_backup_report(stats, health_issues)

        # Send alerts
        if send_alerts and health_issues:
            self.send_backup_alerts(health_issues)

        # Auto-fix issues
        if auto_fix:
            self.auto_fix_issues(health_issues)

        # Summary
        self.display_summary(stats, health_issues)

    def analyze_backup_directory(self, backup_base):
        """Analyze the backup directory structure"""
        stats = {
            'total_backups': 0,
            'total_size': 0,
            'backups_by_type': {},
            'backups_by_date': {},
            'oldest_backup': None,
            'newest_backup': None,
            'missing_types': [],
            'corrupted_files': []
        }

        # Walk through backup directory
        for root, dirs, files in os.walk(backup_base):
            for file in files:
                if self.is_backup_file(file):
                    file_path = os.path.join(root, file)
                    file_stat = os.stat(file_path)

                    stats['total_backups'] += 1
                    stats['total_size'] += file_stat.st_size

                    # Categorize by type
                    backup_type = self.get_backup_type(file)
                    if backup_type not in stats['backups_by_type']:
                        stats['backups_by_type'][backup_type] = []
                    stats['backups_by_type'][backup_type].append(file_path)

                    # Track dates
                    file_date = self.get_file_date(file_path)
                    if file_date:
                        date_str = file_date.strftime('%Y-%m-%d')
                        if date_str not in stats['backups_by_date']:
                            stats['backups_by_date'][date_str] = []
                        stats['backups_by_date'][date_str].append(file_path)

                        # Track oldest/newest
                        if not stats['oldest_backup'] or file_date < stats['oldest_backup']:
                            stats['oldest_backup'] = file_date
                        if not stats['newest_backup'] or file_date > stats['newest_backup']:
                            stats['newest_backup'] = file_date

        # Check for missing backup types
        expected_types = ['database', 'media', 'business']
        for backup_type in expected_types:
            if backup_type not in stats['backups_by_type']:
                stats['missing_types'].append(backup_type)

        return stats

    def is_backup_file(self, filename):
        """Check if file is a backup file"""
        return (
            filename.startswith(('db_backup_', 'media_backup_')) or
            ('backup' in filename and filename.endswith('.json')) or
            filename.endswith(('.sql', '.tar.gz', '.db'))
        )

    def get_backup_type(self, filename):
        """Determine backup type from filename"""
        if filename.startswith('db_backup_') or filename.endswith('.sql'):
            return 'database'
        elif filename.startswith('media_backup_') or filename.endswith('.tar.gz'):
            return 'media'
        elif filename.endswith('.json'):
            return 'business'
        else:
            return 'unknown'

    def get_file_date(self, file_path):
        """Extract date from backup filename"""
        filename = os.path.basename(file_path)

        # Try different date patterns
        import re
        patterns = [
            r'(\d{8}_\d{6})',  # YYYYMMDD_HHMMSS
            r'(\d{8})',        # YYYYMMDD
            r'(\d{4}-\d{2}-\d{2})'  # YYYY-MM-DD
        ]

        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                date_str = match.group(1)
                try:
                    if '_' in date_str:
                        dt = timezone.datetime.strptime(date_str, '%Y%m%d_%H%M%S')
                        return timezone.make_aware(dt)
                    elif '-' in date_str:
                        dt = timezone.datetime.strptime(date_str, '%Y-%m-%d')
                        return timezone.make_aware(dt)
                    else:
                        dt = timezone.datetime.strptime(date_str, '%Y%m%d')
                        return timezone.make_aware(dt)
                except ValueError:
                    continue

        return None

    def check_backup_health(self, stats):
        """Check for backup health issues"""
        issues = []

        # Check if backups exist
        if stats['total_backups'] == 0:
            issues.append({
                'severity': 'critical',
                'message': 'No backup files found',
                'recommendation': 'Run backup_database and backup_business commands'
            })

        # Check for recent backups
        if stats['newest_backup']:
            days_since_last_backup = (timezone.now() - stats['newest_backup']).days
            if days_since_last_backup > 7:
                issues.append({
                    'severity': 'warning',
                    'message': f'No recent backup ({days_since_last_backup} days old)',
                    'recommendation': 'Schedule regular automated backups'
                })

        # Check backup size
        if stats['total_size'] < 1024 * 1024:  # Less than 1MB
            issues.append({
                'severity': 'warning',
                'message': 'Total backup size is very small',
                'recommendation': 'Verify backup contents and check for missing data'
            })

        # Check for missing backup types
        for missing_type in stats['missing_types']:
            issues.append({
                'severity': 'warning',
                'message': f'Missing {missing_type} backups',
                'recommendation': f'Configure {missing_type} backup procedures'
            })

        # Check backup distribution
        if len(stats['backups_by_date']) < 7:  # Less than a week of backups
            issues.append({
                'severity': 'info',
                'message': 'Limited backup history',
                'recommendation': 'Consider increasing backup retention period'
            })

        return issues

    def generate_backup_report(self, stats, issues):
        """Generate detailed backup report"""
        report_path = os.path.join(settings.BASE_DIR, 'backups', 'backup_report.txt')

        with open(report_path, 'w') as f:
            f.write('Marid POS Backup Health Report\n')
            f.write('=' * 40 + '\n\n')
            f.write(f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')

            # Summary
            f.write('SUMMARY\n')
            f.write('-' * 20 + '\n')
            f.write(f'Total Backups: {stats["total_backups"]}\n')
            f.write(f'Total Size: {stats["total_size"] / 1024 / 1024:.2f} MB\n')

            if stats['oldest_backup']:
                f.write(f'Oldest Backup: {stats["oldest_backup"].strftime("%Y-%m-%d")}\n')
            if stats['newest_backup']:
                f.write(f'Newest Backup: {stats["newest_backup"].strftime("%Y-%m-%d")}\n')

            f.write('\nBACKUPS BY TYPE\n')
            f.write('-' * 20 + '\n')
            for backup_type, files in stats['backups_by_type'].items():
                f.write(f'{backup_type.title()}: {len(files)} files\n')

            f.write('\nBACKUPS BY DATE\n')
            f.write('-' * 20 + '\n')
            for date, files in sorted(stats['backups_by_date'].items()):
                f.write(f'{date}: {len(files)} files\n')

            if issues:
                f.write('\nISSUES FOUND\n')
                f.write('-' * 20 + '\n')
                for issue in issues:
                    f.write(f'[{issue["severity"].upper()}] {issue["message"]}\n')
                    f.write(f'  Recommendation: {issue["recommendation"]}\n\n')

        self.stdout.write(self.style.SUCCESS(f'📊 Report generated: {report_path}'))

    def send_backup_alerts(self, issues):
        """Send alerts for critical backup issues"""
        critical_issues = [issue for issue in issues if issue['severity'] == 'critical']

        if critical_issues:
            try:
                from django.core.mail import send_mail

                subject = '🚨 CRITICAL: Marid POS Backup Issues Detected'
                message = 'Critical backup issues have been detected:\n\n'

                for issue in critical_issues:
                    message += f'- {issue["message"]}\n'

                message += '\nPlease review backup configuration immediately.'

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[settings.ADMINS[0][1] if settings.ADMINS else 'admin@example.com'],
                    fail_silently=True
                )

                self.stdout.write(self.style.SUCCESS('📧 Critical alerts sent'))

            except Exception as e:
                self.stdout.write(self.style.WARNING(f'⚠️  Alert sending failed: {e}'))

    def auto_fix_issues(self, issues):
        """Attempt to automatically fix common issues"""
        for issue in issues:
            if 'No backup files found' in issue['message']:
                self.stdout.write('🔧 Attempting to create initial backup...')
                try:
                    from django.core.management import call_command
                    call_command('backup_database')
                    self.stdout.write(self.style.SUCCESS('✅ Initial backup created'))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'❌ Auto-fix failed: {e}'))

    def display_summary(self, stats, issues):
        """Display backup health summary"""
        self.stdout.write('\n📊 Backup Health Summary')
        self.stdout.write('=' * 30)

        # Status indicator
        if any(issue['severity'] == 'critical' for issue in issues):
            self.stdout.write(self.style.ERROR('🔴 CRITICAL ISSUES FOUND'))
        elif any(issue['severity'] == 'warning' for issue in issues):
            self.stdout.write(self.style.WARNING('🟡 WARNINGS FOUND'))
        else:
            self.stdout.write(self.style.SUCCESS('🟢 BACKUPS HEALTHY'))

        self.stdout.write(f'\nTotal backups: {stats["total_backups"]}')
        self.stdout.write(f'Total size: {stats["total_size"] / 1024 / 1024:.2f} MB')

        if issues:
            self.stdout.write(f'\nIssues: {len(issues)}')
            for issue in issues:
                color = {
                    'critical': self.style.ERROR,
                    'warning': self.style.WARNING,
                    'info': self.style.SUCCESS
                }.get(issue['severity'], self.style.SUCCESS)

                self.stdout.write(color(f'• {issue["severity"].upper()}: {issue["message"]}'))

        self.stdout.write('\nRun with --report for detailed analysis')