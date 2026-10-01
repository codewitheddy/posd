from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from pos.models import Business, Branch, BusinessMembership
from hr.models import (
    Employee, Department, KenyanBank,
    StatutoryRuleSet, PAYETaxBand, NSSFTierRule, SHIFRule,
    HousingLevyRule, NITARule, StatutoryReliefRule,
    ConsentRecord, DataSubjectRequest, DataBreachIncident, SensitiveDataAccessLog
)


class KenyaCompliancePhase1Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='hr_admin',
            email='hr_admin@example.com',
            password='AdminPassword123!',
            first_name='John',
            last_name='Kamau'
        )
        self.business = Business.objects.create(
            name='Nairobi Superstore Ltd',
            slug='nairobi-superstore',
            owner=self.user,
            is_active=True
        )
        self.branch = Branch.objects.create(
            business=self.business,
            name='CBD Branch',
            code='CBD01',
            is_default=True,
            is_active=True
        )
        BusinessMembership.objects.create(
            user=self.user,
            business=self.business,
            role='owner',
            is_active=True
        )

    def test_employee_valid_kenyan_identifiers(self):
        """Test valid KRA PIN, National ID, and Kenyan phone number."""
        emp = Employee(
            business=self.business,
            branch=self.branch,
            first_name='Faith',
            last_name='Wanjiku',
            id_type='national_id',
            id_number='28491029',
            kra_pin='A012345678X',
            nssf_number='NSSF-123456',
            sha_number='SHA-99887766',
            phone_number='+254712345678',
            mpesa_number='0712345678',
            job_title='Senior Accountant',
            basic_salary=Decimal('85000.00'),
            hire_date=timezone.localdate(),
        )
        emp.full_clean()
        emp.save()
        self.assertEqual(emp.kra_pin, 'A012345678X')
        self.assertTrue(emp.staff_code.startswith('EMP'))

    def test_employee_invalid_kra_pin_raises_validation_error(self):
        """Test that malformed KRA PINs are rejected."""
        emp = Employee(
            business=self.business,
            branch=self.branch,
            first_name='David',
            last_name='Ochieng',
            id_number='19283746',
            kra_pin='INVALID123',
            nssf_number='NSSF-999',
            job_title='Cashier',
            basic_salary=Decimal('35000.00'),
            hire_date=timezone.localdate(),
        )
        with self.assertRaises(ValidationError) as ctx:
            emp.full_clean()
        self.assertIn('kra_pin', ctx.exception.message_dict)

    def test_statutory_ruleset_seeding_and_resolution(self):
        """Test that default Kenya 2026 ruleset seeds correctly and resolves."""
        ruleset = StatutoryRuleSet.get_active_ruleset(self.business)
        self.assertIsNotNone(ruleset)
        self.assertEqual(ruleset.version_code, 'KE-2026-DEF')

        # Check PAYE Bands
        bands = ruleset.paye_bands.all()
        self.assertEqual(bands.count(), 5)
        self.assertEqual(bands[0].rate_percentage, Decimal('10.00'))
        self.assertEqual(bands[4].rate_percentage, Decimal('35.00'))

        # Check NSSF Tiers
        t1 = ruleset.nssf_tiers.get(tier_name='tier_1')
        self.assertEqual(t1.max_employee_deduction, Decimal('540.00'))
        self.assertEqual(t1.max_employer_contribution, Decimal('540.00'))

        t2 = ruleset.nssf_tiers.get(tier_name='tier_2')
        self.assertEqual(t2.max_employee_deduction, Decimal('5940.00'))
        self.assertEqual(t2.max_employer_contribution, Decimal('5940.00'))

        # Check SHIF & Housing Levy
        self.assertEqual(ruleset.shif_rule.percentage_rate, Decimal('2.75'))
        self.assertEqual(ruleset.housing_levy_rule.employee_rate, Decimal('1.50'))
        self.assertEqual(ruleset.housing_levy_rule.employer_rate, Decimal('1.50'))
        self.assertEqual(ruleset.nita_rule.monthly_employer_levy, Decimal('50.00'))

    def test_dpa_data_subject_request_due_date_calculation(self):
        """Test DSR request sets statutory 30-day resolution deadline."""
        emp = Employee.objects.create(
            business=self.business,
            branch=self.branch,
            first_name='Grace',
            last_name='Muthoni',
            id_number='30291823',
            kra_pin='A098765432Y',
            nssf_number='NSSF-777888',
            job_title='Store Clerk',
            hire_date=timezone.localdate(),
        )
        dsr = DataSubjectRequest.objects.create(
            business=self.business,
            employee=emp,
            request_type='access',
            details='Requesting full copy of personal employment data and payslip history.',
        )
        expected_due = timezone.localdate() + timezone.timedelta(days=30)
        self.assertEqual(dsr.due_date, expected_due)
        self.assertFalse(dsr.is_overdue)

    def test_dpa_data_breach_72_hour_deadline_calculation(self):
        """Test Data Breach Incident sets statutory 72-hour ODPC notification deadline."""
        now = timezone.now()
        incident = DataBreachIncident.objects.create(
            business=self.business,
            title='Unauthorized Access Attempt on Payroll Backup',
            description='Suspicious IP attempted download of payroll export.',
            severity='high',
            detected_at=now,
        )
        expected_deadline = now + timezone.timedelta(hours=72)
        self.assertEqual(incident.odpc_notification_deadline, expected_deadline)

    def test_sensitive_data_access_logging(self):
        """Test SensitiveDataAccessLog captures attribute-level access."""
        emp = Employee.objects.create(
            business=self.business,
            branch=self.branch,
            first_name='Peter',
            last_name='Kariuki',
            id_number='24859102',
            kra_pin='A019283746Z',
            nssf_number='NSSF-112233',
            job_title='Warehouse Supervisor',
            hire_date=timezone.localdate(),
        )
        log = SensitiveDataAccessLog.objects.create(
            business=self.business,
            user=self.user,
            employee=emp,
            data_category='salary_payroll',
            action='view',
            ip_address='192.168.1.100',
            user_agent='Mozilla/5.0',
            reason='Annual compensation review',
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.data_category, 'salary_payroll')

    def test_dynamic_statutory_payroll_calculation(self):
        """Test end-to-end statutory payroll run with PAYE, NSSF, SHIF, Housing Levy, and NITA."""
        from hr.services import PayrollService
        from hr.models import Payroll
        from datetime import date

        emp = Employee.objects.create(
            business=self.business,
            branch=self.branch,
            first_name='Mercy',
            last_name='Chebet',
            id_number='29384756',
            kra_pin='A019283746M',
            nssf_number='NSSF-556677',
            job_title='Operations Lead',
            basic_salary=Decimal('100000.00'),
            house_allowance=Decimal('20000.00'),
            hire_date=date(2026, 1, 1),
        )

        p_start = date(2026, 2, 1)
        p_end = date(2026, 2, 28)
        payrolls = PayrollService.calculate_period(self.business, p_start, p_end)
        self.assertEqual(len(payrolls), 1)

        p = payrolls[0]
        # Gross = 100,000 + 20,000 = 120,000 (prorated for full month)
        self.assertGreater(p.gross_salary, Decimal('0.00'))
        self.assertGreater(p.nssf, Decimal('0.00'))
        self.assertGreater(p.shif, Decimal('0.00'))
        self.assertGreater(p.housing_levy, Decimal('0.00'))
        self.assertGreater(p.paye, Decimal('0.00'))
        self.assertGreater(p.employer_nssf, Decimal('0.00'))
        self.assertGreater(p.employer_housing_levy, Decimal('0.00'))
        self.assertEqual(p.employer_nita, Decimal('50.00'))
        self.assertGreater(p.net_salary, Decimal('0.00'))
        self.assertIsNotNone(p.ruleset_used)

    def test_secondary_employee_no_personal_relief(self):
        """Test secondary employment does not receive KES 2,400 monthly personal relief."""
        from hr.services import PayrollService
        from datetime import date

        primary_emp = Employee.objects.create(
            business=self.business,
            branch=self.branch,
            first_name='Primary',
            last_name='Staff',
            id_number='11223344',
            kra_pin='A011111111P',
            nssf_number='NSSF-111',
            job_title='Cashier',
            basic_salary=Decimal('50000.00'),
            is_secondary_employee=False,
            hire_date=date(2026, 1, 1),
        )
        secondary_emp = Employee.objects.create(
            business=self.business,
            branch=self.branch,
            first_name='Secondary',
            last_name='Staff',
            id_number='55667788',
            kra_pin='A022222222S',
            nssf_number='NSSF-222',
            job_title='Consultant',
            basic_salary=Decimal('50000.00'),
            is_secondary_employee=True,
            hire_date=date(2026, 1, 1),
        )

        p_start = date(2026, 2, 1)
        p_end = date(2026, 2, 28)
        payrolls = PayrollService.calculate_period(self.business, p_start, p_end)
        p_map = {p.employee_id: p for p in payrolls}

        primary_p = p_map[primary_emp.pk]
        secondary_p = p_map[secondary_emp.pk]

        # Secondary employee pays more PAYE because personal relief is omitted
        self.assertGreater(secondary_p.paye, primary_p.paye)

    def test_statutory_exporters_and_p9_generation(self):
        """Test KRA, NSSF, SHA, Housing Levy CSV exporters and Form P9 generation."""
        from hr.services import PayrollService
        from hr.exports import (
            generate_kra_itax_paye_csv, generate_nssf_return_csv,
            generate_sha_return_csv, generate_housing_levy_return_csv,
            generate_bank_eft_csv, generate_mpesa_b2c_csv, get_p9_annual_data
        )
        from datetime import date

        emp = Employee.objects.create(
            business=self.business,
            branch=self.branch,
            first_name='Alice',
            last_name='Waweru',
            id_number='31415926',
            kra_pin='A031415926K',
            nssf_number='NSSF-889900',
            phone_number='+254712345678',
            mpesa_number='0712345678',
            bank_name='Equity Bank',
            bank_code='68',
            bank_account_number='0123456789',
            job_title='Branch Manager',
            basic_salary=Decimal('75000.00'),
            hire_date=date(2026, 1, 1),
        )

        p_start = date(2026, 1, 1)
        p_end = date(2026, 1, 31)
        payrolls = PayrollService.calculate_period(self.business, p_start, p_end)

        # Test KRA PAYE CSV
        kra_csv = generate_kra_itax_paye_csv(payrolls, self.business, p_start, p_end)
        self.assertIn('A031415926K', kra_csv)
        self.assertIn('Alice Waweru', kra_csv)

        # Test NSSF CSV
        nssf_csv = generate_nssf_return_csv(payrolls, self.business, p_start, p_end)
        self.assertIn('NSSF-889900', nssf_csv)

        # Test SHA CSV
        sha_csv = generate_sha_return_csv(payrolls, self.business, p_start, p_end)
        self.assertIn('2.75%', sha_csv)

        # Test Housing Levy CSV
        hl_csv = generate_housing_levy_return_csv(payrolls, self.business, p_start, p_end)
        self.assertIn('Affordable Housing Levy', hl_csv)

        # Test Bank EFT CSV
        eft_csv = generate_bank_eft_csv(payrolls, self.business)
        self.assertIn('Equity Bank', eft_csv)

        # Test M-Pesa B2C CSV
        mpesa_csv = generate_mpesa_b2c_csv(payrolls, self.business)
        self.assertIn('254712345678', mpesa_csv)

        # Test P9 Annual Data
        monthly_data, totals = get_p9_annual_data(emp, 2026)
        self.assertEqual(len(monthly_data), 12)
        self.assertGreater(totals['gross_pay'], Decimal('0.00'))
        self.assertGreater(totals['paye_deducted'], Decimal('0.00'))

