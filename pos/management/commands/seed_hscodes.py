"""
Management command to seed the HS Code library with common Kenyan goods.
Based on KRA EAC CET 2022 tariff schedule.

Usage:
    python manage.py seed_hscodes
    python manage.py seed_hscodes --clear   # wipe existing and re-seed
"""
from django.core.management.base import BaseCommand
from pos.models import HSCode

# fmt: off
CODES = [
    # ── Chapter 01 — Live animals ──────────────────────────────────────────
    ("010121", "Pure-bred breeding horses",                          0,  0,  0, "pcs"),
    ("010290", "Live bovine animals, other",                         0,  0, 25, "pcs"),
    ("010391", "Live swine, weighing < 50 kg",                       0,  0, 25, "pcs"),
    ("010511", "Live fowls of species Gallus domesticus, ≤185g",     0,  0, 25, "pcs"),

    # ── Chapter 02 — Meat ──────────────────────────────────────────────────
    ("020110", "Carcasses and half-carcasses of bovine, fresh",      0,  0, 25, "kg"),
    ("020230", "Boneless bovine meat, frozen",                       0,  0, 25, "kg"),
    ("020714", "Cuts of fowls of Gallus domesticus, frozen",         0,  0, 25, "kg"),

    # ── Chapter 03 — Fish ──────────────────────────────────────────────────
    ("030192", "Live eels",                                          0,  0, 25, "kg"),
    ("030231", "Albacore or longfinned tunas, fresh",                0,  0, 25, "kg"),
    ("030374", "Mackerel, frozen",                                   0,  0, 25, "kg"),
    ("030487", "Tilapia fillets, frozen",                            0,  0, 25, "kg"),

    # ── Chapter 04 — Dairy ─────────────────────────────────────────────────
    ("040110", "Milk and cream, not concentrated, fat ≤1%",          0,  0, 60, "l"),
    ("040120", "Milk and cream, fat >1% ≤6%",                        0,  0, 60, "l"),
    ("040210", "Milk powder, fat ≤1.5%",                             0,  0, 25, "kg"),
    ("040221", "Milk powder, fat >1.5%, unsweetened",                0,  0, 25, "kg"),
    ("040310", "Yogurt",                                             0,  0, 25, "kg"),
    ("040510", "Butter",                                             0,  0, 25, "kg"),
    ("040610", "Fresh (unripened) cheese",                           0,  0, 25, "kg"),

    # ── Chapter 07 — Vegetables ────────────────────────────────────────────
    ("070190", "Potatoes, fresh or chilled, other",                  0,  0, 50, "kg"),
    ("070200", "Tomatoes, fresh or chilled",                         0,  0, 50, "kg"),
    ("070310", "Onions and shallots, fresh or chilled",              0,  0, 50, "kg"),
    ("070700", "Cucumbers and gherkins, fresh or chilled",           0,  0, 50, "kg"),
    ("070960", "Fruits of genus Capsicum (peppers), fresh",          0,  0, 50, "kg"),

    # ── Chapter 08 — Fruits ────────────────────────────────────────────────
    ("080300", "Bananas, including plantains, fresh or dried",       0,  0, 50, "kg"),
    ("080430", "Pineapples, fresh or dried",                         0,  0, 50, "kg"),
    ("080510", "Oranges, fresh or dried",                            0,  0, 50, "kg"),
    ("080520", "Mandarins, clementines, fresh or dried",             0,  0, 50, "kg"),
    ("080610", "Grapes, fresh",                                      0,  0, 50, "kg"),
    ("080711", "Watermelons, fresh",                                 0,  0, 50, "kg"),
    ("080719", "Other melons, fresh",                                0,  0, 50, "kg"),
    ("080920", "Cherries, fresh",                                    0,  0, 50, "kg"),
    ("081010", "Strawberries, fresh",                                0,  0, 50, "kg"),

    # ── Chapter 09 — Coffee, tea, spices ───────────────────────────────────
    ("090111", "Coffee, not roasted, not decaffeinated",             0,  0, 25, "kg"),
    ("090121", "Coffee, roasted, not decaffeinated",                 0,  0, 25, "kg"),
    ("090240", "Black tea (fermented) and partly fermented tea",     0,  0, 25, "kg"),
    ("090411", "Pepper of genus Piper, dried, neither crushed nor ground", 0, 0, 25, "kg"),
    ("090910", "Anise seeds",                                        0,  0, 25, "kg"),

    # ── Chapter 10 — Cereals ───────────────────────────────────────────────
    ("100190", "Wheat and meslin, other",                            0,  0, 35, "kg"),
    ("100300", "Barley",                                             0,  0, 35, "kg"),
    ("100590", "Maize (corn), other",                                0,  0, 50, "kg"),
    ("100630", "Semi-milled or wholly milled rice",                  0,  0, 75, "kg"),

    # ── Chapter 11 — Milling products ─────────────────────────────────────
    ("110100", "Wheat or meslin flour",                              0,  0, 35, "kg"),
    ("110220", "Maize (corn) flour",                                 0,  0, 35, "kg"),
    ("110313", "Pellets of maize (corn)",                            0,  0, 35, "kg"),

    # ── Chapter 15 — Fats and oils ─────────────────────────────────────────
    ("150710", "Crude soya-bean oil",                                0,  0, 25, "kg"),
    ("151110", "Crude palm oil",                                     0,  0, 25, "kg"),
    ("151190", "Palm oil, other",                                    0,  0, 25, "kg"),
    ("151211", "Crude sunflower-seed oil",                           0,  0, 25, "kg"),
    ("151219", "Sunflower-seed oil, other",                          0,  0, 25, "kg"),
    ("152200", "Degras; residues from fatty substances",             0,  0, 25, "kg"),

    # ── Chapter 16 — Prepared meat/fish ───────────────────────────────────
    ("160100", "Sausages and similar products",                     16,  0, 25, "kg"),
    ("160232", "Prepared/preserved poultry, Gallus domesticus",     16,  0, 25, "kg"),
    ("160414", "Prepared/preserved tunas, skipjack",                16,  0, 25, "kg"),

    # ── Chapter 17 — Sugar ─────────────────────────────────────────────────
    ("170111", "Cane sugar, raw, in solid form",                     0,  0, 100,"kg"),
    ("170112", "Beet sugar, raw, in solid form",                     0,  0, 100,"kg"),
    ("170191", "Refined sugar, containing added flavouring/colouring", 16, 0, 100, "kg"),
    ("170199", "Other refined sugar",                               16,  0, 100,"kg"),
    ("170211", "Lactose and lactose syrup",                         16,  0, 25, "kg"),

    # ── Chapter 18 — Cocoa ─────────────────────────────────────────────────
    ("180100", "Cocoa beans, whole or broken, raw or roasted",       0,  0, 25, "kg"),
    ("180400", "Cocoa butter, fat and oil",                         16,  0, 25, "kg"),
    ("180610", "Cocoa powder, containing added sugar",              16,  0, 25, "kg"),
    ("180690", "Chocolate and other food preparations containing cocoa, other", 16, 0, 25, "kg"),

    # ── Chapter 19 — Preparations of cereals ──────────────────────────────
    ("190110", "Preparations for infant use, retail sale",          16,  0, 25, "kg"),
    ("190190", "Malt extract; food preparations of flour, other",   16,  0, 25, "kg"),
    ("190211", "Uncooked pasta, not stuffed, containing eggs",      16,  0, 25, "kg"),
    ("190300", "Tapioca and substitutes prepared from starch",      16,  0, 25, "kg"),
    ("190410", "Prepared foods obtained by swelling/roasting of cereals", 16, 0, 25, "kg"),
    ("190590", "Bread, pastry, cakes, biscuits, other",             16,  0, 25, "kg"),

    # ── Chapter 20 — Prepared vegetables/fruit ────────────────────────────
    ("200110", "Cucumbers and gherkins, prepared/preserved by vinegar", 16, 0, 25, "kg"),
    ("200290", "Tomatoes, prepared/preserved, other",               16,  0, 25, "kg"),
    ("200410", "Potatoes, prepared/preserved, frozen",              16,  0, 25, "kg"),
    ("200911", "Orange juice, frozen",                              16,  0, 25, "l"),
    ("200980", "Juice of any other single fruit/vegetable",         16,  0, 25, "l"),

    # ── Chapter 21 — Miscellaneous edible preparations ────────────────────
    ("210111", "Extracts, essences and concentrates of coffee",     16,  0, 25, "kg"),
    ("210112", "Preparations with basis of coffee extracts",        16,  0, 25, "kg"),
    ("210120", "Extracts, essences and concentrates of tea/maté",   16,  0, 25, "kg"),
    ("210310", "Soya sauce",                                        16,  0, 25, "kg"),
    ("210320", "Tomato ketchup and other tomato sauces",            16,  0, 25, "kg"),
    ("210390", "Other sauces and preparations; mixed condiments",   16,  0, 25, "kg"),
    ("210410", "Soups and broths and preparations therefor",        16,  0, 25, "kg"),
    ("210690", "Food preparations not elsewhere specified, other",  16,  0, 25, "kg"),

    # ── Chapter 22 — Beverages ─────────────────────────────────────────────
    ("220110", "Mineral waters and aerated waters, not sweetened",   0,  0, 25, "l"),
    ("220190", "Waters, other (ice, snow)",                          0,  0, 25, "l"),
    ("220210", "Waters, including mineral/aerated, sweetened/flavoured", 16, 0, 25, "l"),
    ("220290", "Non-alcoholic beverages, other",                    16,  0, 25, "l"),
    ("220300", "Beer made from malt",                               16, 10, 75, "l"),
    ("220410", "Sparkling wine",                                    16, 10, 75, "l"),
    ("220421", "Other wine, in containers ≤2l",                     16, 10, 75, "l"),
    ("220710", "Undenatured ethyl alcohol, ≥80% vol",               16, 10, 75, "l"),
    ("220820", "Spirits obtained by distilling grape wine/marc",    16, 10, 75, "l"),
    ("220830", "Whiskies",                                          16, 10, 75, "l"),
    ("220840", "Rum and other spirits from fermented sugar-cane",   16, 10, 75, "l"),
    ("220860", "Vodka",                                             16, 10, 75, "l"),
    ("220890", "Other spirits and liqueurs",                        16, 10, 75, "l"),

    # ── Chapter 24 — Tobacco ───────────────────────────────────────────────
    ("240110", "Tobacco, not stemmed/stripped",                      0, 35, 35, "kg"),
    ("240220", "Cigarettes containing tobacco",                     16, 35, 35, "u"),
    ("240290", "Other manufactured tobacco",                        16, 35, 35, "kg"),

    # ── Chapter 27 — Mineral fuels ─────────────────────────────────────────
    ("271012", "Light oils and preparations",                        8,  0, 25, "l"),
    ("271019", "Other petroleum oils",                               8,  0, 25, "l"),
    ("271121", "Natural gas, in gaseous state",                      8,  0, 25, "kg"),

    # ── Chapter 30 — Pharmaceutical products ──────────────────────────────
    ("300190", "Glands and other organs for organo-therapeutic uses", 0, 0,  0, "kg"),
    ("300210", "Antisera and other blood fractions",                  0, 0,  0, "kg"),
    ("300310", "Medicaments containing penicillins, not in dosage",   0, 0,  0, "kg"),
    ("300390", "Other medicaments, not in dosage form",               0, 0,  0, "kg"),
    ("300490", "Other medicaments, in dosage form",                   0, 0,  0, "kg"),

    # ── Chapter 33 — Essential oils / cosmetics ────────────────────────────
    ("330300", "Perfumes and toilet waters",                         16,  0, 25, "kg"),
    ("330410", "Lip make-up preparations",                          16,  0, 25, "kg"),
    ("330491", "Powders, whether or not compressed",                16,  0, 25, "kg"),
    ("330499", "Other beauty/make-up preparations",                 16,  0, 25, "kg"),
    ("330510", "Shampoos",                                          16,  0, 25, "kg"),
    ("330590", "Other preparations for use on hair",                16,  0, 25, "kg"),
    ("330610", "Dentifrices",                                       16,  0, 25, "kg"),
    ("330710", "Pre-shave, shaving or after-shave preparations",    16,  0, 25, "kg"),

    # ── Chapter 34 — Soap / detergents ────────────────────────────────────
    ("340111", "Soap for toilet use",                               16,  0, 25, "kg"),
    ("340119", "Other soap",                                        16,  0, 25, "kg"),
    ("340120", "Soap in other forms",                               16,  0, 25, "kg"),
    ("340211", "Anionic organic surface-active agents",             16,  0, 25, "kg"),
    ("340290", "Other surface-active preparations",                 16,  0, 25, "kg"),

    # ── Chapter 39 — Plastics ──────────────────────────────────────────────
    ("392321", "Sacks and bags of polymers of ethylene",            16,  0, 25, "kg"),
    ("392329", "Sacks and bags of other plastics",                  16,  0, 25, "kg"),
    ("392410", "Tableware and kitchenware of plastics",             16,  0, 25, "kg"),

    # ── Chapter 48 — Paper / paperboard ───────────────────────────────────
    ("481820", "Handkerchiefs, cleansing/facial tissues of paper",  16,  0, 25, "kg"),
    ("481840", "Sanitary towels and tampons, napkins",              16,  0, 25, "kg"),
    ("481890", "Other household/sanitary articles of paper",        16,  0, 25, "kg"),

    # ── Chapter 52 — Cotton ────────────────────────────────────────────────
    ("520100", "Cotton, not carded or combed",                       0,  0, 25, "kg"),
    ("520512", "Cotton yarn, single, combed, ≥714.29 decitex",       0,  0, 25, "kg"),

    # ── Chapter 61/62 — Clothing ───────────────────────────────────────────
    ("610910", "T-shirts, singlets of cotton, knitted",             16,  0, 35, "u"),
    ("620342", "Men's trousers of cotton",                          16,  0, 35, "u"),
    ("620462", "Women's trousers of cotton",                        16,  0, 35, "u"),

    # ── Chapter 64 — Footwear ──────────────────────────────────────────────
    ("640299", "Other footwear with outer soles/uppers of rubber/plastics", 16, 0, 35, "pcs"),
    ("640399", "Other footwear with outer soles of rubber, uppers of leather", 16, 0, 35, "pcs"),

    # ── Chapter 84 — Machinery ─────────────────────────────────────────────
    ("841451", "Table, floor, wall, window, ceiling or roof fans",  16,  0, 25, "pcs"),
    ("841510", "Air conditioning machines, window/wall type",       16,  0, 25, "pcs"),
    ("845011", "Fully-automatic washing machines, ≤10 kg",          16,  0, 25, "pcs"),
    ("845121", "Dryers of a dry linen capacity ≤10 kg",             16,  0, 25, "pcs"),
    ("845211", "Automatic sewing machines",                         16,  0, 25, "pcs"),

    # ── Chapter 85 — Electrical equipment ─────────────────────────────────
    ("851610", "Electric instantaneous or storage water heaters",   16,  0, 25, "pcs"),
    ("851640", "Electric smoothing irons",                          16,  0, 25, "pcs"),
    ("851650", "Microwave ovens",                                   16,  0, 25, "pcs"),
    ("851660", "Other ovens; cookers, cooking plates, boiling rings", 16, 0, 25, "pcs"),
    ("851671", "Coffee or tea makers",                              16,  0, 25, "pcs"),
    ("851672", "Toasters",                                          16,  0, 25, "pcs"),
    ("851679", "Other electrothermic appliances",                   16,  0, 25, "pcs"),
    ("851712", "Telephones for cellular networks (mobile phones)",  16,  0, 25, "pcs"),
    ("851770", "Parts of telephone sets",                           16,  0, 25, "kg"),
    ("852110", "Video recording/reproducing apparatus, magnetic tape", 16, 0, 25, "pcs"),
    ("852872", "Other reception apparatus for television, colour",  16,  0, 25, "pcs"),
    ("854370", "Other electrical machines and apparatus",           16,  0, 25, "pcs"),

    # ── Chapter 87 — Vehicles ──────────────────────────────────────────────
    ("870321", "Motor cars, spark-ignition, cylinder capacity ≤1000cc", 16, 0, 25, "pcs"),
    ("870322", "Motor cars, spark-ignition, 1000cc < cc ≤1500cc",  16,  0, 25, "pcs"),
    ("870323", "Motor cars, spark-ignition, 1500cc < cc ≤3000cc",  16,  0, 25, "pcs"),
    ("870410", "Dumpers for off-highway use",                       16,  0, 25, "pcs"),
    ("871120", "Motorcycles, reciprocating piston engine, 50cc < cc ≤250cc", 16, 0, 25, "pcs"),

    # ── Chapter 90 — Optical / medical instruments ─────────────────────────
    ("900110", "Optical fibres and optical fibre bundles",          16,  0,  0, "kg"),
    ("900130", "Contact lenses",                                    16,  0,  0, "pcs"),
    ("901831", "Syringes, with or without needles",                  0,  0,  0, "pcs"),
    ("901839", "Other needles, catheters, cannulae",                 0,  0,  0, "pcs"),
]
# fmt: on


class Command(BaseCommand):
    help = "Seed the HS Code library with common Kenyan goods (KRA EAC CET 2022)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete all existing HS codes before seeding'
        )

    def handle(self, *args, **options):
        if options['clear']:
            deleted, _ = HSCode.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted} existing HS codes.'))

        created = updated = 0
        for code, description, vat, excise, duty, unit in CODES:
            obj, is_new = HSCode.objects.update_or_create(
                code=code,
                defaults={
                    'description': description,
                    'vat_rate': vat,
                    'excise_rate': excise,
                    'import_duty': duty,
                    'is_excisable': excise > 0,
                    'unit': unit,
                    'is_active': True,
                }
            )
            if is_new:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Created: {created}, Updated: {updated}. '
                f'Total HS codes: {HSCode.objects.count()}'
            )
        )
