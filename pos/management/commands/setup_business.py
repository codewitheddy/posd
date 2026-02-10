from django.core.management.base import BaseCommand
from pos.models import BusinessSettings


class Command(BaseCommand):
    help = 'Initialize business settings with default values'

    def handle(self, *args, **options):
        settings = BusinessSettings.get_settings()
        
        self.stdout.write(self.style.SUCCESS('Business settings initialized!'))
        self.stdout.write(f'Business Name: {settings.business_name}')
        self.stdout.write(f'VAT Rate: {settings.vat_rate}%')
        self.stdout.write(f'Currency: {settings.currency_symbol}')
        self.stdout.write('')
        self.stdout.write('You can now customize these settings from:')
        self.stdout.write('Admin > Business Settings')
        self.stdout.write('or')
        self.stdout.write('Django Admin > Business Settings')
