"""
Unit Tests for Core Scoping, Permissions, Settings, and Security
"""
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from core.models import (
    Company,
    Branch,
    CompanyMembership,
    BranchMembership,
    UserProfile,
    CoreSetting,
    SensitiveDataAccessLog,
    LoginAuditLog,
)
from core.scoping import (
    get_current_company,
    get_current_branch,
    get_user_branches,
    CompanyBranchScopeMixin,
)
from core.settings_store import SettingStore
from core.security import (
    log_sensitive_access,
    record_login_attempt,
    mask_sensitive_value,
)


class ScopingAndSecurityTests(TestCase):
    """Test suite for tenant/branch scoping, typed settings, and security logs."""

    def setUp(self):
        self.factory = RequestFactory()
        
        # Create Companies
        self.company_a = Company.objects.create(name='Company Alpha', slug='company-alpha', kra_pin='P051234567A')
        self.company_b = Company.objects.create(name='Company Beta', slug='company-beta', kra_pin='P059876543B')

        # Create Branches for Company A
        self.branch_hq = Branch.objects.create(company=self.company_a, name='Nairobi HQ', code='HQ', is_headquarters=True)
        self.branch_west = Branch.objects.create(company=self.company_a, name='Westlands Branch', code='WST', is_headquarters=False)

        # Create Users
        self.user_owner = User.objects.create_user(username='owner_a', email='owner@alpha.com')
        self.user_staff = User.objects.create_user(username='staff_wst', email='staff@alpha.com')
        self.user_other = User.objects.create_user(username='user_b', email='user@beta.com')

        # Create Memberships
        CompanyMembership.objects.create(company=self.company_a, user=self.user_owner, role=CompanyMembership.ROLE_OWNER)
        CompanyMembership.objects.create(company=self.company_a, user=self.user_staff, role=CompanyMembership.ROLE_STAFF)
        BranchMembership.objects.create(branch=self.branch_west, user=self.user_staff, is_primary=True)

        CompanyMembership.objects.create(company=self.company_b, user=self.user_other, role=CompanyMembership.ROLE_STAFF)

        # Create UserProfiles
        self.profile_owner = UserProfile.objects.create(user=self.user_owner)
        self.profile_staff = UserProfile.objects.create(user=self.user_staff)
        self.profile_staff.set_pin('1234')
        self.profile_staff.save()

    def test_company_resolution_from_request(self):
        """Test that get_current_company resolves active company from user membership."""
        request = self.factory.get('/')
        request.user = self.user_owner
        company = get_current_company(request)
        self.assertEqual(company, self.company_a)

        request_b = self.factory.get('/')
        request_b.user = self.user_other
        company_b = get_current_company(request_b)
        self.assertEqual(company_b, self.company_b)

    def test_branch_scoping_isolation(self):
        """Test that user only receives assigned branches."""
        staff_branches = get_user_branches(self.user_staff, self.company_a)
        self.assertEqual(list(staff_branches), [self.branch_west])

        # Owner has access to all branches of the company
        owner_branches = get_user_branches(self.user_owner, self.company_a)
        self.assertEqual(set(owner_branches), {self.branch_hq, self.branch_west})

    def test_user_pin_authentication_and_lockout(self):
        """Test PIN hashing and account lockout after repeated failed attempts."""
        self.assertTrue(self.profile_staff.check_pin('1234'))
        self.assertFalse(self.profile_staff.check_pin('9999'))

        # Simulate 5 failed attempts
        for _ in range(5):
            self.profile_staff.record_failed_attempt(max_attempts=5, lockout_minutes=15)

        self.assertTrue(self.profile_staff.is_locked())

        # Reset attempts on successful login
        self.profile_staff.reset_failed_attempts()
        self.assertFalse(self.profile_staff.is_locked())
        self.assertEqual(self.profile_staff.failed_login_attempts, 0)

    def test_typed_settings_store_hierarchical_resolution(self):
        """
        Verify setting resolution order:
        Branch Override -> Company Override -> Global Default.
        """
        # 1. Global Default
        SettingStore.set('pos', 'vat_rate', '16.0', value_type=CoreSetting.TYPE_DECIMAL)
        val = SettingStore.get('pos', 'vat_rate', company=self.company_a)
        self.assertEqual(val, Decimal('16.0'))

        # 2. Company Override for Company A
        SettingStore.set('pos', 'vat_rate', '14.0', value_type=CoreSetting.TYPE_DECIMAL, company=self.company_a)
        val_a = SettingStore.get('pos', 'vat_rate', company=self.company_a)
        self.assertEqual(val_a, Decimal('14.0'))

        # Company B still gets global default
        val_b = SettingStore.get('pos', 'vat_rate', company=self.company_b)
        self.assertEqual(val_b, Decimal('16.0'))

        # 3. Branch Override for Westlands
        SettingStore.set('pos', 'vat_rate', '0.0', value_type=CoreSetting.TYPE_DECIMAL, company=self.company_a, branch=self.branch_west)
        val_west = SettingStore.get('pos', 'vat_rate', company=self.company_a, branch=self.branch_west)
        self.assertEqual(val_west, Decimal('0.0'))

        # HQ branch still gets Company A override
        val_hq = SettingStore.get('pos', 'vat_rate', company=self.company_a, branch=self.branch_hq)
        self.assertEqual(val_hq, Decimal('14.0'))

    def test_sensitive_access_logging(self):
        """Test logging sensitive field access for Kenya DPA 2019 compliance."""
        request = self.factory.get('/')
        request.user = self.user_owner
        request.company = self.company_a

        log = log_sensitive_access(
            request=request,
            entity_type='hr.Employee',
            entity_id='101',
            fields_accessed=['basic_salary', 'kra_pin'],
            reason='Monthly payroll verification',
        )

        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.user_owner)
        self.assertEqual(log.entity_id, '101')
        self.assertIn('basic_salary', log.fields_accessed)

    def test_mask_sensitive_value_utility(self):
        """Test masking PII fields."""
        masked_pin = mask_sensitive_value('A001234567Z', visible_end_chars=4)
        self.assertEqual(masked_pin, '*******567Z')

        masked_short = mask_sensitive_value('123', visible_end_chars=4)
        self.assertEqual(masked_short, '***')
