"""
Kenya Reference Data Seeder
Seeds all 47 Counties of Kenya and major Commercial Banks / Clearing Codes.
"""
from core.models.reference import KenyaCounty, KenyaBank


COUNTIES_DATA = [
    {'code': '001', 'name': 'Mombasa', 'capital': 'Mombasa City', 'region': 'coast'},
    {'code': '002', 'name': 'Kwale', 'capital': 'Kwale', 'region': 'coast'},
    {'code': '003', 'name': 'Kilifi', 'capital': 'Kilifi', 'region': 'coast'},
    {'code': '004', 'name': 'Tana River', 'capital': 'Hola', 'region': 'coast'},
    {'code': '005', 'name': 'Lamu', 'capital': 'Lamu', 'region': 'coast'},
    {'code': '006', 'name': 'Taita Taveta', 'capital': 'Mwatate', 'region': 'coast'},
    {'code': '007', 'name': 'Garissa', 'capital': 'Garissa', 'region': 'north_eastern'},
    {'code': '008', 'name': 'Wajir', 'capital': 'Wajir', 'region': 'north_eastern'},
    {'code': '009', 'name': 'Mandera', 'capital': 'Mandera', 'region': 'north_eastern'},
    {'code': '010', 'name': 'Marsabit', 'capital': 'Marsabit', 'region': 'eastern'},
    {'code': '011', 'name': 'Isiolo', 'capital': 'Isiolo', 'region': 'eastern'},
    {'code': '012', 'name': 'Meru', 'capital': 'Meru', 'region': 'eastern'},
    {'code': '013', 'name': 'Tharaka-Nithi', 'capital': 'Kathwana', 'region': 'eastern'},
    {'code': '014', 'name': 'Embu', 'capital': 'Embu', 'region': 'eastern'},
    {'code': '015', 'name': 'Kitui', 'capital': 'Kitui', 'region': 'eastern'},
    {'code': '016', 'name': 'Machakos', 'capital': 'Machakos', 'region': 'eastern'},
    {'code': '017', 'name': 'Makueni', 'capital': 'Wote', 'region': 'eastern'},
    {'code': '018', 'name': 'Nyandarua', 'capital': 'Ol Kalou', 'region': 'central'},
    {'code': '019', 'name': 'Nyeri', 'capital': 'Nyeri', 'region': 'central'},
    {'code': '020', 'name': 'Kirinyaga', 'capital': 'Kerugoya', 'region': 'central'},
    {'code': '021', 'name': "Murang'a", 'capital': "Murang'a", 'region': 'central'},
    {'code': '022', 'name': 'Kiambu', 'capital': 'Kiambu', 'region': 'central'},
    {'code': '023', 'name': 'Turkana', 'capital': 'Lodwar', 'region': 'rift_valley'},
    {'code': '024', 'name': 'West Pokot', 'capital': 'Kapenguria', 'region': 'rift_valley'},
    {'code': '025', 'name': 'Samburu', 'capital': 'Maralal', 'region': 'rift_valley'},
    {'code': '026', 'name': 'Trans Nzoia', 'capital': 'Kitale', 'region': 'rift_valley'},
    {'code': '027', 'name': 'Uasin Gishu', 'capital': 'Eldoret', 'region': 'rift_valley'},
    {'code': '028', 'name': 'Elgeyo Marakwet', 'capital': 'Iten', 'region': 'rift_valley'},
    {'code': '029', 'name': 'Nandi', 'capital': 'Kapsabet', 'region': 'rift_valley'},
    {'code': '030', 'name': 'Baringo', 'capital': 'Kabarnet', 'region': 'rift_valley'},
    {'code': '031', 'name': 'Laikipia', 'capital': 'Rumuruti', 'region': 'rift_valley'},
    {'code': '032', 'name': 'Nakuru', 'capital': 'Nakuru City', 'region': 'rift_valley'},
    {'code': '033', 'name': 'Narok', 'capital': 'Narok', 'region': 'rift_valley'},
    {'code': '034', 'name': 'Kajiado', 'capital': 'Kajiado', 'region': 'rift_valley'},
    {'code': '035', 'name': 'Kericho', 'capital': 'Kericho', 'region': 'rift_valley'},
    {'code': '036', 'name': 'Bomet', 'capital': 'Bomet', 'region': 'rift_valley'},
    {'code': '037', 'name': 'Kakamega', 'capital': 'Kakamega', 'region': 'western'},
    {'code': '038', 'name': 'Vihiga', 'capital': 'Mbale', 'region': 'western'},
    {'code': '039', 'name': 'Bungoma', 'capital': 'Bungoma', 'region': 'western'},
    {'code': '040', 'name': 'Busia', 'capital': 'Busia', 'region': 'western'},
    {'code': '041', 'name': 'Siaya', 'capital': 'Siaya', 'region': 'nyanza'},
    {'code': '042', 'name': 'Kisumu', 'capital': 'Kisumu City', 'region': 'nyanza'},
    {'code': '043', 'name': 'Homa Bay', 'capital': 'Homa Bay', 'region': 'nyanza'},
    {'code': '044', 'name': 'Migori', 'capital': 'Migori', 'region': 'nyanza'},
    {'code': '045', 'name': 'Kisii', 'capital': 'Kisii', 'region': 'nyanza'},
    {'code': '046', 'name': 'Nyamira', 'capital': 'Nyamira', 'region': 'nyanza'},
    {'code': '047', 'name': 'Nairobi City', 'capital': 'Nairobi City', 'region': 'nairobi'},
]

BANKS_DATA = [
    {'bank_code': '01', 'name': 'Kenya Commercial Bank (KCB)', 'swift_code': 'KCBLKENX', 'paybill_number': '522522'},
    {'bank_code': '02', 'name': 'Standard Chartered Bank Kenya', 'swift_code': 'SCBLKENX', 'paybill_number': '329329'},
    {'bank_code': '03', 'name': 'Absa Bank Kenya PLC', 'swift_code': 'BARCKENX', 'paybill_number': '303030'},
    {'bank_code': '11', 'name': 'Co-operative Bank of Kenya', 'swift_code': 'CPOQKENX', 'paybill_number': '400200'},
    {'bank_code': '12', 'name': 'National Bank of Kenya', 'swift_code': 'NBKEKENX', 'paybill_number': '544700'},
    {'bank_code': '14', 'name': 'NCBA Bank Kenya PLC', 'swift_code': 'CBAFKENX', 'paybill_number': '888888'},
    {'bank_code': '31', 'name': 'Stanbic Bank Kenya', 'swift_code': 'SBICKENX', 'paybill_number': '600100'},
    {'bank_code': '43', 'name': 'Equity Bank Kenya', 'swift_code': 'EQBLKENX', 'paybill_number': '247247'},
    {'bank_code': '53', 'name': 'Family Bank Kenya', 'swift_code': 'FABLKENX', 'paybill_number': '222111'},
    {'bank_code': '57', 'name': 'I&M Bank Limited', 'swift_code': 'IMBLKENX', 'paybill_number': '542542'},
    {'bank_code': '63', 'name': 'Diamond Trust Bank (DTB)', 'swift_code': 'DTKENX', 'paybill_number': '516600'},
    {'bank_code': '68', 'name': 'Sidian Bank', 'swift_code': 'SIDIKENX', 'paybill_number': '111999'},
    {'bank_code': '70', 'name': 'Prime Bank Limited', 'swift_code': 'PRIMKENX', 'paybill_number': '982800'},
    {'bank_code': '74', 'name': 'Credit Bank PLC', 'swift_code': 'CRDBKENX', 'paybill_number': '973900'},
    {'bank_code': '76', 'name': 'Kingdom Bank Kenya', 'swift_code': 'KNGDKENX', 'paybill_number': '529900'},
]


def seed_kenya_counties() -> int:
    """Seed or update all 47 counties of Kenya."""
    count = 0
    for data in COUNTIES_DATA:
        KenyaCounty.objects.update_or_create(
            code=data['code'],
            defaults={
                'name': data['name'],
                'capital': data['capital'],
                'region': data['region'],
            }
        )
        count += 1
    return count


def seed_kenya_banks() -> int:
    """Seed or update Kenyan commercial banks and clearing codes."""
    count = 0
    for data in BANKS_DATA:
        KenyaBank.objects.update_or_create(
            bank_code=data['bank_code'],
            defaults={
                'name': data['name'],
                'swift_code': data['swift_code'],
                'paybill_number': data['paybill_number'],
                'is_active': True,
            }
        )
        count += 1
    return count
