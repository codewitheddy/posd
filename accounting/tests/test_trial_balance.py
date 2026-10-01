"""
Unit Tests for Trial Balance & General Ledger Reporting
Enforces the Mathematical Zero-Difference Invariant and Running Balances.
"""
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth.models import User

from core.models.organization import Company, Branch
from accounting.models import (
    Account, AccountType, NormalBalance, JournalEntry, JournalEntryStatus
)
from accounting.seeders import seed_default_chart_of_accounts, seed_fiscal_year
from accounting import api
from accounting.selectors import TrialBalanceSelector, GeneralLedgerSelector


class TrialBalanceTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Great Rift Wholesalers', slug='rift-wholesalers')
        self.branch = Branch.objects.create(company=self.company, name='Eldoret Branch', code='ELD')
        self.user = User.objects.create_user(username='chief_accountant', password='password123')
        seed_default_chart_of_accounts(self.company)
        self.fiscal_year = seed_fiscal_year(self.company, year=2026)

    def test_trial_balance_zero_difference_invariant(self):
        """
        Post multiple multi-legged transactions across Asset, Liability, Equity, Income, Expense.
        Verify that total debits equals total credits with EXACT 0.00 difference invariant.
        """
        # 1. Capital Injection: Bank (1020) Dr 1,000,000 / Share Capital (3000) Cr 1,000,000
        api.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='CAP-01',
            date_val=date(2026, 1, 5),
            lines=[
                {'account_code': '1020', 'debit': Decimal('1000000.00'), 'credit': Decimal('0.00')},
                {'account_code': '3000', 'debit': Decimal('0.00'), 'credit': Decimal('1000000.00')},
            ],
            narration='Initial Capital'
        )

        # 2. Inventory Purchase on Credit: Inventory (1200) Dr 400,000 / Accounts Payable (2000) Cr 400,000
        api.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='PURCH-01',
            date_val=date(2026, 1, 10),
            lines=[
                {'account_code': '1200', 'debit': Decimal('400000.00'), 'credit': Decimal('0.00')},
                {'account_code': '2000', 'debit': Decimal('0.00'), 'credit': Decimal('400000.00')},
            ],
            narration='Inventory restock on credit'
        )

        # 3. Sales with VAT:
        # Bank (1020) Dr 232,000
        # Sales (4000) Cr 200,000
        # VAT Output (2100) Cr 32,000
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='SALE-01',
            date_val=date(2026, 1, 15),
            lines=[
                {'account_code': '1020', 'debit': Decimal('232000.00'), 'credit': Decimal('0.00')},
                {'account_code': '4000', 'debit': Decimal('0.00'), 'credit': Decimal('200000.00')},
                {'account_code': '2100', 'debit': Decimal('0.00'), 'credit': Decimal('32000.00')},
            ],
            narration='Product sales with 16% VAT'
        )

        # 4. COGS Recognition: COGS (5000) Dr 120,000 / Inventory (1200) Cr 120,000
        api.post_journal(
            company=self.company,
            source_module='pos',
            source_ref='COGS-01',
            date_val=date(2026, 1, 15),
            lines=[
                {'account_code': '5000', 'debit': Decimal('120000.00'), 'credit': Decimal('0.00')},
                {'account_code': '1200', 'debit': Decimal('0.00'), 'credit': Decimal('120000.00')},
            ],
            narration='Cost of goods sold'
        )

        # 5. Operating Expense: Rent (6100) Dr 50,000 / Bank (1020) Cr 50,000
        api.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='RENT-01',
            date_val=date(2026, 1, 20),
            lines=[
                {'account_code': '6100', 'debit': Decimal('50000.00'), 'credit': Decimal('0.00')},
                {'account_code': '1020', 'debit': Decimal('0.00'), 'credit': Decimal('50000.00')},
            ],
            narration='Office rent'
        )

        # Execute Trial Balance Selector
        tb_data = TrialBalanceSelector.get_trial_balance(self.company, as_of_date=date(2026, 1, 31))

        self.assertTrue(tb_data['is_balanced'], "Trial balance is not balanced!")
        self.assertEqual(tb_data['difference'], Decimal('0.00'), "Trial balance difference is not 0.00!")
        self.assertEqual(tb_data['total_debits'], tb_data['total_credits'])

        # Verify specific account ending balances
        rows = {r['account_code']: r for r in tb_data['rows']}

        # Bank (1020): +1,000,000 (Dr) + 232,000 (Dr) - 50,000 (Cr) = 1,182,000 Dr
        self.assertEqual(rows['1020']['closing_debit'], Decimal('1182000.00'))
        self.assertEqual(rows['1020']['closing_credit'], Decimal('0.00'))

        # Inventory (1200): +400,000 (Dr) - 120,000 (Cr) = 280,000 Dr
        self.assertEqual(rows['1200']['closing_debit'], Decimal('280000.00'))

        # Accounts Payable (2000): 400,000 Cr
        self.assertEqual(rows['2000']['closing_credit'], Decimal('400000.00'))

        # Share Capital (3000): 1,000,000 Cr
        self.assertEqual(rows['3000']['closing_credit'], Decimal('1000000.00'))

        # Sales (4000): 200,000 Cr
        self.assertEqual(rows['4000']['closing_credit'], Decimal('200000.00'))

        # COGS (5000): 120,000 Dr
        self.assertEqual(rows['5000']['closing_debit'], Decimal('120000.00'))

        # Rent (6100): 50,000 Dr
        self.assertEqual(rows['6100']['closing_debit'], Decimal('50000.00'))

        # VAT Output (2100): 32,000 Cr
        self.assertEqual(rows['2100']['closing_credit'], Decimal('32000.00'))

        # Sum verification:
        # Debits = 1,182,000 (Bank) + 280,000 (Inv) + 120,000 (COGS) + 50,000 (Rent) = 1,632,000
        # Credits = 400,000 (AP) + 1,000,000 (Equity) + 200,000 (Sales) + 32,000 (VAT) = 1,632,000
        self.assertEqual(tb_data['total_debits'], Decimal('1632000.00'))
        self.assertEqual(tb_data['total_credits'], Decimal('1632000.00'))

    def test_general_ledger_running_balances(self):
        """Verify that GeneralLedgerSelector returns ordered transactions with correct running balances."""
        bank_acct = Account.objects.get(company=self.company, code='1020')

        # Entry 1: Deposit 50,000
        api.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='DEP-01',
            date_val=date(2026, 2, 1),
            lines=[
                {'account': bank_acct, 'debit': Decimal('50000.00'), 'credit': Decimal('0.00')},
                {'account_code': '3000', 'debit': Decimal('0.00'), 'credit': Decimal('50000.00')},
            ],
            narration='Deposit'
        )

        # Entry 2: Withdrawal 15,000
        api.post_journal(
            company=self.company,
            source_module='manual',
            source_ref='WDR-01',
            date_val=date(2026, 2, 5),
            lines=[
                {'account_code': '6000', 'debit': Decimal('15000.00'), 'credit': Decimal('0.00')},
                {'account': bank_acct, 'debit': Decimal('0.00'), 'credit': Decimal('15000.00')},
            ],
            narration='Salary payment'
        )

        gl_data = GeneralLedgerSelector.get_account_ledger(
            company=self.company,
            account_id=bank_acct.pk,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28)
        )

        self.assertEqual(len(gl_data['entries']), 2)
        # Entry 1 running balance: 50,000.00
        self.assertEqual(gl_data['entries'][0]['running_balance'], Decimal('50000.00'))
        # Entry 2 running balance: 35,000.00
        self.assertEqual(gl_data['entries'][1]['running_balance'], Decimal('35000.00'))
        self.assertEqual(gl_data['closing_balance'], Decimal('35000.00'))
