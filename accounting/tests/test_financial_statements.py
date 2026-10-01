"""
Financial Statements Test Suite (IFRS Income Statement, Classified Balance Sheet, Cash Flows)
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model

from core.models.organization import Company, Branch
from accounting.models import (
    Account, AccountType, NormalBalance,
    FiscalYear, FiscalPeriod,
    JournalEntry, JournalEntryLine, JournalEntryType, JournalEntryStatus
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from accounting import api

User = get_user_model()


class FinancialStatementsTests(TestCase):
    """
    Tests IFRS-compliant Financial Statements:
    - Multi-Period Income Statement (Gross Profit, EBIT, Net Profit)
    - Classified Balance Sheet (Strict Assets = Liabilities + Equity invariant)
    - Statement of Cash Flows (Indirect Method per IAS 7)
    """

    def setUp(self):
        self.company = Company.objects.create(name='Pinnacle Enterprises Ltd', slug='pinnacle-ent')
        self.branch = Branch.objects.create(company=self.company, name='Nairobi HQ', code='NRB-HQ')
        self.user = User.objects.create_user(username='financial_controller', password='password123')

        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

    def test_multi_period_income_statement(self):
        """
        Test Income Statement with Gross Sales, Discounts, COGS, OpEx, and Net Profit.
        """
        # 1. Post Gross Revenue KES 500,000 to Account 4000 (CR) and Cash (DR)
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='REV-MAR-01',
            date_val=date(2026, 3, 10),
            lines=[
                {'account_code': '1010', 'debit': '500000.00', 'credit': '0.00'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '500000.00'},
            ],
            auto_approve=True
        )

        # 2. Post Sales Discount KES 20,000 to Account 4100 (DR)
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='DISC-MAR-01',
            date_val=date(2026, 3, 12),
            lines=[
                {'account_code': '4100', 'debit': '20000.00', 'credit': '0.00'},
                {'account_code': '1010', 'debit': '0.00', 'credit': '20000.00'},
            ],
            auto_approve=True
        )

        # 3. Post Cost of Goods Sold KES 180,000 to Account 5000 (DR) and Inventory (CR)
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='COGS-MAR-01',
            date_val=date(2026, 3, 15),
            lines=[
                {'account_code': '5000', 'debit': '180000.00', 'credit': '0.00'},
                {'account_code': '1200', 'debit': '0.00', 'credit': '180000.00'},
            ],
            auto_approve=True
        )

        # 4. Post Operating Expenses: Rent KES 60,000 (6100), Staff Salaries KES 90,000 (6000)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='OPEX-MAR-01',
            date_val=date(2026, 3, 20),
            lines=[
                {'account_code': '6100', 'debit': '60000.00', 'credit': '0.00'},
                {'account_code': '6000', 'debit': '90000.00', 'credit': '0.00'},
                {'account_code': '1030', 'debit': '0.00', 'credit': '150000.00'},
            ],
            auto_approve=True
        )

        # 5. Post Corporate Income Tax Provision KES 45,000 to Account 8100 (DR) and Tax Liability (CR)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='TAX-MAR-01',
            date_val=date(2026, 3, 31),
            lines=[
                {'account_code': '8100', 'debit': '45000.00', 'credit': '0.00'},
                {'account_code': '2100', 'debit': '0.00', 'credit': '45000.00'},
            ],
            auto_approve=True
        )

        # Generate Income Statement for March 2026
        pnl = api.get_income_statement(
            company=self.company,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31)
        )['primary']

        self.assertEqual(pnl['gross_revenue'], Decimal('500000.00'))
        self.assertEqual(pnl['total_discounts'], Decimal('20000.00'))
        self.assertEqual(pnl['net_revenue'], Decimal('480000.00'))
        self.assertEqual(pnl['total_cogs'], Decimal('180000.00'))
        self.assertEqual(pnl['gross_profit'], Decimal('300000.00'))
        self.assertEqual(pnl['gross_margin_pct'], Decimal('62.50'))  # 300k / 480k = 62.5%

        self.assertEqual(pnl['total_opex'], Decimal('150000.00'))
        self.assertEqual(pnl['operating_profit'], Decimal('150000.00'))  # Gross profit 300k - OpEx 150k = 150k
        self.assertEqual(pnl['profit_before_tax'], Decimal('150000.00'))
        self.assertEqual(pnl['total_tax_expense'], Decimal('45000.00'))
        self.assertEqual(pnl['net_profit'], Decimal('105000.00'))  # 150k - 45k = 105k
        self.assertEqual(pnl['net_margin_pct'], Decimal('21.88'))  # 105k / 480k = 21.875% -> 21.88%

    def test_classified_balance_sheet_mathematical_invariance(self):
        """
        Test Classified Balance Sheet ensuring Assets == Liabilities + Equity
        with exact 0.00 difference under diverse transactions.
        """
        # 1. Owner injects Share Capital KES 1,000,000 into Primary Bank (1030)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='CAP-INIT-01',
            date_val=date(2026, 1, 1),
            lines=[
                {'account_code': '1030', 'debit': '1000000.00', 'credit': '0.00'},
                {'account_code': '3000', 'debit': '0.00', 'credit': '1000000.00'},
            ],
            auto_approve=True
        )

        # 2. Purchase POS Hardware KES 200,000 (1510) via Bank (1030)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='ASSET-POS-01',
            date_val=date(2026, 1, 15),
            lines=[
                {'account_code': '1510', 'debit': '200000.00', 'credit': '0.00'},
                {'account_code': '1030', 'debit': '0.00', 'credit': '200000.00'},
            ],
            auto_approve=True
        )

        # 3. Buy Merchandise Stock on credit KES 300,000 (DR 1200 Inventory, CR 2000 AP)
        api.post_journal(
            company=self.company,
            source_module='ap',
            source_ref='BILL-STOCK-01',
            date_val=date(2026, 2, 1),
            lines=[
                {'account_code': '1200', 'debit': '300000.00', 'credit': '0.00'},
                {'account_code': '2000', 'debit': '0.00', 'credit': '300000.00'},
            ],
            auto_approve=True
        )

        # 4. Sell Stock on credit for KES 450,000 (DR 1100 AR, CR 4000 Sales)
        # and record COGS KES 150,000 (DR 5000 COGS, CR 1200 Inventory)
        api.post_journal(
            company=self.company,
            source_module='ar',
            source_ref='INV-SALE-01',
            date_val=date(2026, 2, 10),
            lines=[
                {'account_code': '1100', 'debit': '450000.00', 'credit': '0.00'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '450000.00'},
            ],
            auto_approve=True
        )
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='COGS-01',
            date_val=date(2026, 2, 10),
            lines=[
                {'account_code': '5000', 'debit': '150000.00', 'credit': '0.00'},
                {'account_code': '1200', 'debit': '0.00', 'credit': '150000.00'},
            ],
            auto_approve=True
        )

        # 5. Pay supplier KES 100,000 from Bank (DR 2000, CR 1030)
        api.post_journal(
            company=self.company,
            source_module='ap',
            source_ref='PAY-VEND-01',
            date_val=date(2026, 2, 25),
            lines=[
                {'account_code': '2000', 'debit': '100000.00', 'credit': '0.00'},
                {'account_code': '1030', 'debit': '0.00', 'credit': '100000.00'},
            ],
            auto_approve=True
        )

        # 6. Customer pays KES 250,000 into Bank (DR 1030, CR 1100)
        api.post_journal(
            company=self.company,
            source_module='ar',
            source_ref='REC-CUST-01',
            date_val=date(2026, 2, 28),
            lines=[
                {'account_code': '1030', 'debit': '250000.00', 'credit': '0.00'},
                {'account_code': '1100', 'debit': '0.00', 'credit': '250000.00'},
            ],
            auto_approve=True
        )

        # 7. Post Depreciation KES 10,000 (DR 6800, CR 1590 Accumulated Depreciation)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='DEP-FEB-01',
            date_val=date(2026, 2, 28),
            lines=[
                {'account_code': '6800', 'debit': '10000.00', 'credit': '0.00'},
                {'account_code': '1590', 'debit': '0.00', 'credit': '10000.00'},
            ],
            auto_approve=True
        )

        # Generate Balance Sheet as of Feb 28, 2026
        bs = api.get_balance_sheet(
            company=self.company,
            as_of_date=date(2026, 2, 28)
        )['primary']

        self.assertIsNotNone(bs)
        self.assertEqual(bs['difference'], Decimal('0.00'))
        self.assertTrue(bs['is_balanced'])

        # Detailed checks:
        # Current Assets:
        # Bank (1030): 1,000,000 - 200,000 - 100,000 + 250,000 = 950,000
        # AR (1100): 450,000 - 250,000 = 200,000
        # Inventory (1200): 300,000 - 150,000 = 150,000
        # Total Current Assets = 950,000 + 200,000 + 150,000 = 1,300,000
        self.assertEqual(bs['current_assets']['total'], Decimal('1300000.00'))

        # Fixed Assets:
        # POS Hardware (1510): 200,000
        # Accumulated Depr (1590): -10,000
        # Net Fixed Assets = 190,000
        self.assertEqual(bs['fixed_assets']['total'], Decimal('190000.00'))

        # Total Assets = 1,300,000 + 190,000 = 1,490,000
        self.assertEqual(bs['total_assets'], Decimal('1490000.00'))

        # Liabilities:
        # AP (2000): 300,000 - 100,000 = 200,000
        self.assertEqual(bs['total_liabilities'], Decimal('200000.00'))

        # Equity:
        # Share Capital (3000): 1,000,000
        # Net Income: Sales (450k) - COGS (150k) - Depr (10k) = 290,000
        # Total Equity = 1,290,000
        self.assertEqual(bs['equity']['total'], Decimal('1290000.00'))
        self.assertEqual(bs['equity']['current_period_net_income'], Decimal('290000.00'))

        # Total Liabilities & Equity = 200,000 + 1,290,000 = 1,490,000
        self.assertEqual(bs['total_liabilities_and_equity'], Decimal('1490000.00'))

    def test_statement_of_cash_flows_indirect_method(self):
        """
        Test Statement of Cash Flows with Operating, Investing, and Financing flows,
        and verify full reconciliation with ending cash balances.
        """
        # Day 1: Owner injects KES 500,000 into Bank (Financing Flow)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='CF-CAP-01',
            date_val=date(2026, 3, 1),
            lines=[
                {'account_code': '1030', 'debit': '500000.00', 'credit': '0.00'},
                {'account_code': '3000', 'debit': '0.00', 'credit': '500000.00'},
            ],
            auto_approve=True
        )

        # Day 5: Buy Equipment KES 100,000 cash from Bank (Investing Flow)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='CF-EQ-01',
            date_val=date(2026, 3, 5),
            lines=[
                {'account_code': '1500', 'debit': '100000.00', 'credit': '0.00'},
                {'account_code': '1030', 'debit': '0.00', 'credit': '100000.00'},
            ],
            auto_approve=True
        )

        # Day 10: Cash Sales KES 200,000 into Till (Operating Flow)
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='CF-SALE-01',
            date_val=date(2026, 3, 10),
            lines=[
                {'account_code': '1010', 'debit': '200000.00', 'credit': '0.00'},
                {'account_code': '4000', 'debit': '0.00', 'credit': '200000.00'},
            ],
            auto_approve=True
        )

        # Day 20: Pay Cash Rent KES 40,000 from Till (Operating Flow)
        api.post_journal(
            company=self.company,
            source_module='gl',
            source_ref='CF-RENT-01',
            date_val=date(2026, 3, 20),
            lines=[
                {'account_code': '6100', 'debit': '40000.00', 'credit': '0.00'},
                {'account_code': '1010', 'debit': '0.00', 'credit': '40000.00'},
            ],
            auto_approve=True
        )

        # Generate Cash Flow Statement for March 2026
        cf = api.get_cash_flow_statement(
            company=self.company,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31)
        )

        self.assertIsNotNone(cf)
        self.assertTrue(cf['summary']['is_reconciled'])
        self.assertEqual(cf['summary']['difference'], Decimal('0.00'))

        # Operating: Net Profit 160k (Sales 200k - Rent 40k)
        self.assertEqual(cf['operating_activities']['net_cash_from_operations'], Decimal('160000.00'))
        # Investing: PPE purchase -100k
        self.assertEqual(cf['investing_activities']['net_cash_from_investing'], Decimal('-100000.00'))
        # Financing: Capital injection +500k
        self.assertEqual(cf['financing_activities']['net_cash_from_financing'], Decimal('500000.00'))

        # Net cash change = 160k - 100k + 500k = 560,000
        self.assertEqual(cf['summary']['net_cash_change'], Decimal('560000.00'))
        self.assertEqual(cf['summary']['ending_cash_actual'], Decimal('560000.00'))
        self.assertEqual(cf['summary']['ending_cash_computed'], Decimal('560000.00'))
