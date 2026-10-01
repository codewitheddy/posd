from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from pos.models import Business
from hr.models import (
    KenyanBank, StatutoryRuleSet, PAYETaxBand,
    NSSFTierRule, SHIFRule, HousingLevyRule, NITARule, StatutoryReliefRule
)


KENYAN_BANKS_DATA = [
    ('01', 'Kenya Commercial Bank (KCB)', 'KCBLKENX'),
    ('02', 'Standard Chartered Bank Kenya', 'SCBLKENX'),
    ('03', 'Absa Bank Kenya PLC', 'BARBKENX'),
    ('07', 'Commercial Bank of Africa (NCBA)', 'CBAFKENX'),
    ('11', 'Co-operative Bank of Kenya', 'COOPKENX'),
    ('12', 'National Bank of Kenya', 'NBKEKENX'),
    ('14', 'Oriental Commercial Bank', 'OBLKENX'),
    ('19', 'Diamond Trust Bank Kenya (DTB)', 'DTBLKENX'),
    ('20', 'Stanbic Bank Kenya', 'SBICKENX'),
    ('23', 'Consolidated Bank of Kenya', 'CONLKENX'),
    ('31', 'Stanbic Bank', 'SBICKENX'),
    ('43', 'Ecobank Kenya', 'ECOBKENX'),
    ('50', 'Paramount Bank', 'PMNTKENX'),
    ('51', 'Kingdom Bank Limited', 'JAMAKENX'),
    ('53', 'Guaranty Trust Bank Kenya', 'GTBIKENX'),
    ('54', 'Victoria Commercial Bank', 'VICKENX'),
    ('55', 'Guardian Bank', 'GUARKENX'),
    ('57', 'I&M Bank Limited', 'IMBLKENX'),
    ('63', 'Development Bank of Kenya', 'DBKENX'),
    ('66', 'SBM Bank Kenya', 'CHASKENX'),
    ('68', 'Equity Bank Kenya Limited', 'EQBLKENX'),
    ('70', 'Family Bank Limited', 'FABLKENX'),
    ('72', 'Gulf African Bank', 'GABLKENX'),
    ('74', 'First Community Bank', 'FCBLKENX'),
    ('76', 'UBA Kenya Bank Limited', 'UNBAKENX'),
    ('78', 'Credit Bank Limited', 'CRBLKENX'),
]


class Command(BaseCommand):
    help = 'Seeds Kenyan commercial banks list and versioned reference statutory rulesets for all businesses.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding Kenyan Commercial Banks...'))
        banks_created = 0
        for code, name, swift in KENYAN_BANKS_DATA:
            bank, created = KenyanBank.objects.get_or_create(
                bank_code=code,
                defaults={'name': name, 'swift_code': swift, 'is_active': True}
            )
            if created:
                banks_created += 1
        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {banks_created} new Kenyan banks (Total: {KenyanBank.objects.count()}).'))

        self.stdout.write(self.style.NOTICE('Seeding Versioned 2026 Reference Statutory Rulesets for Businesses...'))
        businesses = Business.objects.all()
        rulesets_created = 0
        for b in businesses:
            ruleset = StatutoryRuleSet.get_active_ruleset(b)
            if ruleset:
                rulesets_created += 1
                self.stdout.write(f' - [{b.name}]: Active ruleset {ruleset.version_code}')

        self.stdout.write(self.style.SUCCESS(f'Completed seeding rulesets across {rulesets_created} businesses.'))
