"""
Management command to clear all cache
"""
from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Clear all cache data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm cache clearing without prompt',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            confirm = input('Are you sure you want to clear all cache? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('Cache clearing cancelled'))
                return
        
        self.stdout.write('Clearing cache...')
        cache.clear()
        self.stdout.write(self.style.SUCCESS('✅ Cache cleared successfully!'))
