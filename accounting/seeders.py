"""
Default Kenyan SME Chart of Accounts & Fiscal Period Provisioning
Standards: IFRS for SMEs / ICPAK Practice
"""
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from core.models.organization import Company
from accounting.models import (
    Account, AccountType, AccountCategory, NormalBalance,
    FiscalYear, FiscalPeriod
)


KENYA_SME_DEFAULT_ACCOUNTS = [
    # ─── 1000: ASSETS ────────────────────────────────────────────────────────
    # Cash & Bank Equivalents
    {'code': '1010', 'name': 'Cash in Till / Cash Drawer', 'type': AccountType.ASSET, 'cat': AccountCategory.CASH_AND_BANK, 'norm': NormalBalance.DEBIT, 'tag': 'cash_till', 'is_rec': True, 'is_sys': True, 'desc': 'Physical currency held in POS cash drawers'},
    {'code': '1020', 'name': 'Main Safe / Petty Cash Float', 'type': AccountType.ASSET, 'cat': AccountCategory.CASH_AND_BANK, 'norm': NormalBalance.DEBIT, 'tag': 'petty_cash', 'is_rec': True, 'is_sys': True, 'desc': 'Cash held in main store safe and petty cash drawer'},
    {'code': '1030', 'name': 'Bank Account - Primary Commercial', 'type': AccountType.ASSET, 'cat': AccountCategory.CASH_AND_BANK, 'norm': NormalBalance.DEBIT, 'tag': 'bank_primary', 'is_rec': True, 'is_sys': True, 'desc': 'Primary commercial operating bank account'},
    {'code': '1040', 'name': 'M-Pesa Till / Paybill Settlement Clearing', 'type': AccountType.ASSET, 'cat': AccountCategory.CASH_AND_BANK, 'norm': NormalBalance.DEBIT, 'tag': 'mpesa_clearing', 'is_rec': True, 'is_sys': True, 'desc': 'M-Pesa Collections clearing account prior to bank sweep'},
    {'code': '1050', 'name': 'Card & Electronic Payment Clearing', 'type': AccountType.ASSET, 'cat': AccountCategory.CASH_AND_BANK, 'norm': NormalBalance.DEBIT, 'tag': 'card_clearing', 'is_rec': True, 'is_sys': True, 'desc': 'Credit / Debit card settlement clearing account'},
    
    # Receivables & Current Assets
    {'code': '1100', 'name': 'Accounts Receivable (Trade Debtors)', 'type': AccountType.ASSET, 'cat': AccountCategory.ACCOUNTS_RECEIVABLE, 'norm': NormalBalance.DEBIT, 'tag': 'ar', 'is_rec': False, 'is_sys': True, 'desc': 'Trade receivables for customer credit sales'},
    {'code': '1110', 'name': 'Allowance for Expected Credit Losses (Bad Debts)', 'type': AccountType.ASSET, 'cat': AccountCategory.ACCOUNTS_RECEIVABLE, 'norm': NormalBalance.CREDIT, 'tag': 'ar_allowance', 'is_rec': False, 'is_sys': True, 'desc': 'Contra-asset provision for doubtful accounts'},
    {'code': '1200', 'name': 'Merchandise Inventory / Stock on Hand', 'type': AccountType.ASSET, 'cat': AccountCategory.INVENTORY, 'norm': NormalBalance.DEBIT, 'tag': 'inventory', 'is_rec': False, 'is_sys': True, 'desc': 'Retail and wholesale merchandise stock valuation'},
    {'code': '1250', 'name': 'Goods in Transit (Inter-Branch Transfers)', 'type': AccountType.ASSET, 'cat': AccountCategory.INVENTORY, 'norm': NormalBalance.DEBIT, 'tag': 'inventory_git', 'is_rec': False, 'is_sys': True, 'desc': 'Stock dispatched between branches awaiting receipt'},
    {'code': '1300', 'name': 'Prepaid Rent & Operating Expenses', 'type': AccountType.ASSET, 'cat': AccountCategory.CURRENT_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'prepayments', 'is_rec': False, 'is_sys': False, 'desc': 'Advance payments for rent, insurance, and services'},
    {'code': '1310', 'name': 'Staff Salary Advances', 'type': AccountType.ASSET, 'cat': AccountCategory.CURRENT_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'staff_advances', 'is_rec': False, 'is_sys': True, 'desc': 'Outstanding short-term staff salary advances'},
    
    # Statutory Tax Credits (Assets)
    {'code': '1400', 'name': 'KRA VAT Input Tax Claimable (16%)', 'type': AccountType.ASSET, 'cat': AccountCategory.STATUTORY_TAX_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'vat_input', 'is_rec': False, 'is_sys': True, 'desc': 'VAT paid on supplier purchases eligible for input offset'},
    {'code': '1410', 'name': 'Withholding VAT Tax Credits (2%)', 'type': AccountType.ASSET, 'cat': AccountCategory.STATUTORY_TAX_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'wht_vat_credit', 'is_rec': False, 'is_sys': True, 'desc': 'WHT VAT deducted by appointed corporate withholding agents'},
    {'code': '1420', 'name': 'Withholding Income Tax Credits (5%)', 'type': AccountType.ASSET, 'cat': AccountCategory.STATUTORY_TAX_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'wht_income_credit', 'is_rec': False, 'is_sys': True, 'desc': 'Withholding tax deducted on management/consulting fees'},
    
    # Property, Plant & Equipment (Fixed Assets)
    {'code': '1500', 'name': 'Property, Plant & Equipment (PPE)', 'type': AccountType.ASSET, 'cat': AccountCategory.FIXED_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'ppe', 'is_rec': False, 'is_sys': True, 'desc': 'Capital equipment, premises, and core business assets'},
    {'code': '1510', 'name': 'POS Hardware, Computers & Printers', 'type': AccountType.ASSET, 'cat': AccountCategory.FIXED_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'fixed_pos_hardware', 'is_rec': False, 'is_sys': True, 'desc': 'POS terminals, barcode scanners, and receipt printers'},
    {'code': '1520', 'name': 'Store Furniture, Shelving & Display Fixtures', 'type': AccountType.ASSET, 'cat': AccountCategory.FIXED_ASSET, 'norm': NormalBalance.DEBIT, 'tag': 'fixed_furniture', 'is_rec': False, 'is_sys': False, 'desc': 'Racks, counters, chillers, and shop furnishings'},
    {'code': '1590', 'name': 'Accumulated Depreciation - PPE & Equipment', 'type': AccountType.ASSET, 'cat': AccountCategory.ACCUMULATED_DEPRECIATION, 'norm': NormalBalance.CREDIT, 'tag': 'accum_depreciation', 'is_rec': False, 'is_sys': True, 'desc': 'Cumulative historical depreciation contra-asset'},

    # ─── 2000: LIABILITIES ───────────────────────────────────────────────────
    # Trade & Operational Payables
    {'code': '2000', 'name': 'Accounts Payable (Trade Creditors)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.ACCOUNTS_PAYABLE, 'norm': NormalBalance.CREDIT, 'tag': 'ap', 'is_rec': False, 'is_sys': True, 'desc': 'Trade payables owed to stock and service suppliers'},
    {'code': '2050', 'name': 'Goods Received Not Invoiced (GRNI Clearing)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.ACCOUNTS_PAYABLE, 'norm': NormalBalance.CREDIT, 'tag': 'grni', 'is_rec': False, 'is_sys': True, 'desc': 'Received inventory awaiting supplier invoice match'},
    
    # Kenyan Statutory Remittances & Tax Liabilities
    {'code': '2100', 'name': 'KRA VAT Output Tax Payable (16%)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'vat_output', 'is_rec': False, 'is_sys': True, 'desc': 'VAT collected on standard rated taxable sales'},
    {'code': '2110', 'name': 'KRA PAYE Tax Payable', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'paye_payable', 'is_rec': False, 'is_sys': True, 'desc': 'PAYE deducted from staff payroll awaiting 9th of month remit'},
    {'code': '2120', 'name': 'NSSF Contributions Payable (Tier I & II)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'nssf_payable', 'is_rec': False, 'is_sys': True, 'desc': 'Employee & matching employer NSSF contributions'},
    {'code': '2130', 'name': 'SHA / SHIF Contributions Payable (2.75%)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'shif_payable', 'is_rec': False, 'is_sys': True, 'desc': 'Social Health Insurance Fund deductions'},
    {'code': '2140', 'name': 'Affordable Housing Levy Payable (1.5% + 1.5%)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'housing_levy_payable', 'is_rec': False, 'is_sys': True, 'desc': 'Affordable Housing Levy employee & employer contributions'},
    {'code': '2150', 'name': 'HELB Student Loan Deductions Payable', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'helb_payable', 'is_rec': False, 'is_sys': True, 'desc': 'Higher Education Loans Board employee deductions'},
    {'code': '2160', 'name': 'NITA Employer Training Levy Payable', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'nita_payable', 'is_rec': False, 'is_sys': True, 'desc': 'NITA statutory employer training levy (KES 50/staff/month)'},
    {'code': '2170', 'name': 'Withholding VAT Payable (2%)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'wht_vat_payable', 'is_rec': False, 'is_sys': True, 'desc': 'WHT VAT withheld on supplier disbursements'},
    {'code': '2180', 'name': 'Withholding Income Tax Payable (5%/3%/20%)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.STATUTORY_TAX_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'wht_income_payable', 'is_rec': False, 'is_sys': True, 'desc': 'Withholding income tax withheld on professional/contract services'},
    
    # Payroll & Customer Liabilities
    {'code': '2200', 'name': 'Net Salaries Payable (Payroll Clearing)', 'type': AccountType.LIABILITY, 'cat': AccountCategory.PAYROLL_CLEARING, 'norm': NormalBalance.CREDIT, 'tag': 'net_salaries_payable', 'is_rec': False, 'is_sys': True, 'desc': 'Net salary disbursements due to employees'},
    {'code': '2300', 'name': 'Customer Advance Deposits & Store Credits', 'type': AccountType.LIABILITY, 'cat': AccountCategory.CURRENT_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'customer_deposits', 'is_rec': False, 'is_sys': True, 'desc': 'Customer prepayments, layaways, and store credit balances'},
    {'code': '2400', 'name': 'Accrued Operating Expenses & Provisions', 'type': AccountType.LIABILITY, 'cat': AccountCategory.CURRENT_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'accrued_expenses', 'is_rec': False, 'is_sys': False, 'desc': 'Accruals for rent, utilities, and audit fees'},
    {'code': '2500', 'name': 'Bank Loans & Commercial Borrowings', 'type': AccountType.LIABILITY, 'cat': AccountCategory.LONG_TERM_LIABILITY, 'norm': NormalBalance.CREDIT, 'tag': 'long_term_debt', 'is_rec': False, 'is_sys': False, 'desc': 'Long term commercial financing facilities'},

    # ─── 3000: EQUITY ────────────────────────────────────────────────────────
    {'code': '3000', 'name': 'Owner Capital / Paid-Up Share Capital', 'type': AccountType.EQUITY, 'cat': AccountCategory.EQUITY, 'norm': NormalBalance.CREDIT, 'tag': 'share_capital', 'is_rec': False, 'is_sys': True, 'desc': 'Owner initial and injected equity capital'},
    {'code': '3100', 'name': 'Retained Earnings / Accumulated Profit', 'type': AccountType.EQUITY, 'cat': AccountCategory.RETAINED_EARNINGS, 'norm': NormalBalance.CREDIT, 'tag': 'retained_earnings', 'is_rec': False, 'is_sys': True, 'desc': 'Cumulative prior year profits rolled into reserves'},
    {'code': '3200', 'name': 'Owner Drawings & Dividends Paid', 'type': AccountType.EQUITY, 'cat': AccountCategory.OWNER_DRAWING, 'norm': NormalBalance.DEBIT, 'tag': 'owner_drawings', 'is_rec': False, 'is_sys': True, 'desc': 'Capital drawings and dividends disbursed to proprietors'},
    {'code': '3900', 'name': 'Current Year Earnings (P&L Summary Account)', 'type': AccountType.EQUITY, 'cat': AccountCategory.RETAINED_EARNINGS, 'norm': NormalBalance.CREDIT, 'tag': 'pnl_summary', 'is_rec': False, 'is_sys': True, 'desc': 'System closing account for annual profit & loss roll'},

    # ─── 4000: REVENUE / INCOME ──────────────────────────────────────────────
    {'code': '4000', 'name': 'POS Sales Revenue - Standard Rated (16%)', 'type': AccountType.INCOME, 'cat': AccountCategory.OPERATING_REVENUE, 'norm': NormalBalance.CREDIT, 'tag': 'sales_standard', 'is_rec': False, 'is_sys': True, 'desc': 'Revenue from standard rated taxable retail/wholesale sales'},
    {'code': '4010', 'name': 'POS Sales Revenue - Zero Rated (0%)', 'type': AccountType.INCOME, 'cat': AccountCategory.OPERATING_REVENUE, 'norm': NormalBalance.CREDIT, 'tag': 'sales_zero_rated', 'is_rec': False, 'is_sys': True, 'desc': 'Revenue from zero-rated goods (e.g. basic foodstuffs/exports)'},
    {'code': '4020', 'name': 'POS Sales Revenue - Exempt', 'type': AccountType.INCOME, 'cat': AccountCategory.OPERATING_REVENUE, 'norm': NormalBalance.CREDIT, 'tag': 'sales_exempt', 'is_rec': False, 'is_sys': True, 'desc': 'Revenue from exempt non-VAT transactions'},
    {'code': '4100', 'name': 'Sales Discounts Allowed', 'type': AccountType.INCOME, 'cat': AccountCategory.SALES_DISCOUNT, 'norm': NormalBalance.DEBIT, 'tag': 'sales_discounts', 'is_rec': False, 'is_sys': True, 'desc': 'Discounts and promotional concessions granted to buyers'},
    {'code': '4110', 'name': 'Sales Returns & Customer Refunds', 'type': AccountType.INCOME, 'cat': AccountCategory.SALES_DISCOUNT, 'norm': NormalBalance.DEBIT, 'tag': 'sales_returns', 'is_rec': False, 'is_sys': True, 'desc': 'Merchandise returned by customers'},
    {'code': '4200', 'name': 'Delivery & Handling Service Income', 'type': AccountType.INCOME, 'cat': AccountCategory.OTHER_INCOME, 'norm': NormalBalance.CREDIT, 'tag': 'service_income', 'is_rec': False, 'is_sys': False, 'desc': 'Income from delivery fees and handling charges'},
    {'code': '4900', 'name': 'Cash Over / Short (Till Variances)', 'type': AccountType.INCOME, 'cat': AccountCategory.OTHER_INCOME, 'norm': NormalBalance.CREDIT, 'tag': 'cash_over_short', 'is_rec': False, 'is_sys': True, 'desc': 'Net cashier cash drawer overage or shortage variances'},

    # ─── 5000: COST OF SALES (DIRECT COSTS) ──────────────────────────────────
    {'code': '5000', 'name': 'Cost of Goods Sold (COGS)', 'type': AccountType.EXPENSE, 'cat': AccountCategory.COST_OF_SALES, 'norm': NormalBalance.DEBIT, 'tag': 'cogs', 'is_rec': False, 'is_sys': True, 'desc': 'Direct purchase cost of inventory items sold'},
    {'code': '5100', 'name': 'Inventory Shrinkage, Spoilage & Breakages', 'type': AccountType.EXPENSE, 'cat': AccountCategory.COST_OF_SALES, 'norm': NormalBalance.DEBIT, 'tag': 'inventory_spoilage', 'is_rec': False, 'is_sys': True, 'desc': 'Inventory write-offs due to expiry, damage, or stock count deficits'},
    {'code': '5200', 'name': 'Inbound Freight & Clearing Duties', 'type': AccountType.EXPENSE, 'cat': AccountCategory.COST_OF_SALES, 'norm': NormalBalance.DEBIT, 'tag': 'inbound_freight', 'is_rec': False, 'is_sys': False, 'desc': 'Direct carriage and transport costs for incoming stock'},
    {'code': '5300', 'name': 'Purchase Discounts Received', 'type': AccountType.EXPENSE, 'cat': AccountCategory.COST_OF_SALES, 'norm': NormalBalance.CREDIT, 'tag': 'purchase_discounts', 'is_rec': False, 'is_sys': True, 'desc': 'Discounts granted by suppliers on prompt settlement'},

    # ─── 6000: OPERATING & ADMINISTRATIVE EXPENSES ───────────────────────────
    # Payroll & Employee Costs
    {'code': '6000', 'name': 'Salaries & Wages Expense (Basic Pay)', 'type': AccountType.EXPENSE, 'cat': AccountCategory.PAYROLL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'salaries_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Gross basic salaries and wages paid to employees'},
    {'code': '6010', 'name': 'Staff Allowances (House, Transport, Medical)', 'type': AccountType.EXPENSE, 'cat': AccountCategory.PAYROLL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'allowances_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Taxable and non-taxable staff allowances'},
    {'code': '6020', 'name': 'Staff Bonuses, Overtime & Commission', 'type': AccountType.EXPENSE, 'cat': AccountCategory.PAYROLL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'overtime_bonus_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Performance commissions, overtime, and bonuses'},
    {'code': '6030', 'name': 'Employer NSSF Contributions Expense', 'type': AccountType.EXPENSE, 'cat': AccountCategory.PAYROLL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'employer_nssf_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Employer statutory NSSF pension matching contribution'},
    {'code': '6040', 'name': 'Employer Housing Levy Expense (1.5%)', 'type': AccountType.EXPENSE, 'cat': AccountCategory.PAYROLL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'employer_housing_levy_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Employer Affordable Housing Levy matching portion'},
    {'code': '6050', 'name': 'Employer NITA Training Levy Expense', 'type': AccountType.EXPENSE, 'cat': AccountCategory.PAYROLL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'employer_nita_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Employer NITA flat levy per employee'},
    {'code': '6060', 'name': 'Staff Welfare, Training & Meals', 'type': AccountType.EXPENSE, 'cat': AccountCategory.PAYROLL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'staff_welfare_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Staff development, safety gear, and daily tea/meals'},

    # General & Store Operating Expenses
    {'code': '6100', 'name': 'Store Rent & Property Rates', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'rent_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Shop and warehouse rental charges'},
    {'code': '6110', 'name': 'Electricity, Water & Utilities', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'utilities_expense', 'is_rec': False, 'is_sys': False, 'desc': 'KPLC power and county water utility bills'},
    {'code': '6120', 'name': 'Internet, Telephone & Airtime', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'communication_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Fibre internet, mobile data, and staff airtime'},
    {'code': '6200', 'name': 'Marketing, Branding & Signage', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'marketing_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Advertising, flyers, social media, and shop signage'},
    {'code': '6210', 'name': 'POS Thermal Rolls & Packaging Bags', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'packaging_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Thermal receipt paper, carrier bags, and packing material'},
    {'code': '6300', 'name': 'Bank Charges & M-Pesa Transaction Fees', 'type': AccountType.EXPENSE, 'cat': AccountCategory.FINANCIAL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'bank_fees_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Commercial bank ledger fees, EFT charges, and M-Pesa tariffs'},
    {'code': '6400', 'name': 'County Business Permits & Licenses', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'licenses_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Single Business Permit, fire safety, and signage permits'},
    {'code': '6500', 'name': 'Legal, Audit & Professional Consulting', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'professional_fees_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Tax filing consultancy, external audit, and legal fees'},
    {'code': '6600', 'name': 'Repairs & Premises Maintenance', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'repairs_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Electrical repairs, painting, and equipment maintenance'},
    {'code': '6700', 'name': 'Commercial Insurance (Fire & Burglary)', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'insurance_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Annual store and merchandise insurance coverage'},
    {'code': '6800', 'name': 'Depreciation Expense - POS Hardware & Assets', 'type': AccountType.EXPENSE, 'cat': AccountCategory.DEPRECIATION_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'depreciation_expense', 'is_rec': False, 'is_sys': True, 'desc': 'Monthly depreciation allocation for fixed assets'},
    {'code': '6900', 'name': 'General Office & Miscellaneous Expenses', 'type': AccountType.EXPENSE, 'cat': AccountCategory.OPERATING_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'miscellaneous_expense', 'is_rec': False, 'is_sys': False, 'desc': 'Sundry office supplies and incidental store expenses'},
    
    # ─── 7000: OTHER INCOME ──────────────────────────────────────────────────
    {'code': '7000', 'name': 'Interest Income & Investment Returns', 'type': AccountType.INCOME, 'cat': AccountCategory.OTHER_INCOME, 'norm': NormalBalance.CREDIT, 'tag': 'interest_income', 'is_rec': False, 'is_sys': False, 'desc': 'Bank interest earned and short-term investment gains'},
    
    # ─── 8000: FINANCE COSTS & CORPORATE TAX ─────────────────────────────────
    {'code': '8000', 'name': 'Finance Costs & Loan Interest Expense', 'type': AccountType.EXPENSE, 'cat': AccountCategory.FINANCIAL_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'finance_costs', 'is_rec': False, 'is_sys': False, 'desc': 'Bank loan interest and financial borrowing costs'},
    {'code': '8100', 'name': 'Corporate Income Tax Provision / Expense (30%)', 'type': AccountType.EXPENSE, 'cat': AccountCategory.TAX_EXPENSE, 'norm': NormalBalance.DEBIT, 'tag': 'tax_provision', 'is_rec': False, 'is_sys': True, 'desc': 'Annual corporate income tax provision per KRA assessment'},
]


@transaction.atomic
def seed_default_chart_of_accounts(company: Company) -> int:
    """
    Provisions the standard Kenyan SME Chart of Accounts for a tenant Company.
    Idempotent: Skips accounts that already exist by code.
    """
    created_count = 0
    for item in KENYA_SME_DEFAULT_ACCOUNTS:
        account, created = Account.objects.get_or_create(
            company=company,
            code=item['code'],
            defaults={
                'name': item['name'],
                'account_type': item['type'],
                'category': item['cat'],
                'normal_balance': item['norm'],
                'currency': 'KES',
                'is_system': item['is_sys'],
                'system_tag': item['tag'],
                'is_reconciliation': item['is_rec'],
                'is_active': True,
                'description': item['desc'],
            }
        )
        if created:
            created_count += 1
    return created_count


@transaction.atomic
def seed_fiscal_year(company: Company, year: int = None) -> FiscalYear:
    """
    Provisions the standard Kenyan Fiscal Year (Jan 1 to Dec 31) with 12 monthly periods.
    """
    if not year:
        year = timezone.localdate().year

    fy_name = f"FY {year}"
    start_d = date(year, 1, 1)
    end_d = date(year, 12, 31)

    fiscal_year, _ = FiscalYear.objects.get_or_create(
        company=company,
        name=fy_name,
        defaults={
            'start_date': start_d,
            'end_date': end_d,
            'is_closed': False,
        }
    )

    # Provision 12 Calendar Month Periods
    month_names = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]

    for month_idx in range(1, 13):
        p_start = date(year, month_idx, 1)
        if month_idx == 12:
            p_end = date(year, 12, 31)
        else:
            # First day of next month minus 1 day
            p_end = date(year, month_idx + 1, 1) - timezone.timedelta(days=1)

        p_name = f"{month_names[month_idx - 1]} {year}"
        FiscalPeriod.objects.get_or_create(
            company=company,
            fiscal_year=fiscal_year,
            period_number=month_idx,
            defaults={
                'name': p_name,
                'start_date': p_start,
                'end_date': p_end,
                'is_closed': False,
                'is_adjustment_period': False,
            }
        )

    return fiscal_year
