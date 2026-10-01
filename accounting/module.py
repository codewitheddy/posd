"""
Accounting & General Ledger Module Manifest
Registers the module with Platform Core Backoffice navigation, roles, and dashboard.
"""
from core.registry import ModuleManifest, MenuSection, MenuItem, DashboardCard

manifest = ModuleManifest(
    key='accounting',
    name='General Ledger & Accounting',
    version='1.0.0',
    description='IFRS Chart of Accounts, General Ledger, Journals, Fiscal Periods, and Financial Statements',
    icon='bi bi-journal-bookmark',
    dependencies=[],
    permission_prefix='accounting',
    default_roles={
        'Chief Financial Officer': [
            'accounting.view_all',
            'accounting.post_journal',
            'accounting.reverse_journal',
            'accounting.manage_periods',
            'accounting.manage_coa',
            'accounting.view_reports',
        ],
        'Senior Accountant': [
            'accounting.view_all',
            'accounting.post_journal',
            'accounting.reverse_journal',
            'accounting.view_reports',
        ],
        'Staff Accountant / Auditor': [
            'accounting.view_all',
            'accounting.view_reports',
        ],
    },
    menu_sections=[
        MenuSection(
            title='General Ledger',
            order=40,
            items=[
                MenuItem(
                    title='Accounting Hub',
                    url_name='accounting_dashboard',
                    icon='bi bi-speedometer2',
                    order=10
                ),
                MenuItem(
                    title='Chart of Accounts',
                    url_name='accounting_account_list',
                    icon='bi bi-diagram-3',
                    order=20
                ),
                MenuItem(
                    title='Journal Entries',
                    url_name='accounting_journal_list',
                    icon='bi bi-journal-text',
                    order=30
                ),
                MenuItem(
                    title='Fiscal Periods',
                    url_name='accounting_period_list',
                    icon='bi bi-calendar3-range',
                    order=40
                ),
            ],
        ),
        MenuSection(
            title='Financial Reports',
            order=45,
            items=[
                MenuItem(
                    title='Trial Balance',
                    url_name='accounting_trial_balance',
                    icon='bi bi-file-earmark-spreadsheet',
                    order=10
                ),
                MenuItem(
                    title='General Ledger Report',
                    url_name='accounting_general_ledger',
                    icon='bi bi-file-text',
                    order=20
                ),
            ],
        ),
    ],
    dashboard_cards=[],
    url_prefix='/accounting/',
)
