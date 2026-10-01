"""
Management command to seed Kenyan reference data:
- 47 Counties of Kenya
- Commercial Banks and CBK Clearing Codes
"""
from django.core.management.base import BaseCommand
from core.seeders.kenya_reference_data import seed_kenya_counties, seed_kenya_banks


class Command(BaseCommand):
    help = 'Seeds 47 Kenyan Counties and Commercial Bank clearing codes'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Kenyan Reference Data..."))
        
        county_count = seed_kenya_counties()
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {county_count} Kenyan counties."))
        
        bank_count = seed_kenya_banks()
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {bank_count} Kenyan commercial banks."))
