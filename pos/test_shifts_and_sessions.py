from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from pos.models import (
    Business, BusinessMembership, Branch, POSTerminal,
    POSSession, Product, Category, PaymentMethod, Sale, ZReport
)
from pos.zreport_service import ZReportService


class ShiftsAndSessionsIsolationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='shift_owner', password='ownerpass123')
        self.cashier1 = User.objects.create_user(username='cashier_alice', password='alicepass123')
        self.cashier2 = User.objects.create_user(username='cashier_bob', password='bobpass123')
        self.cashier3 = User.objects.create_user(username='cashier_charlie', password='charliepass123')

        self.business = Business.objects.create(
            name='Multi-Shift Retail Store',
            slug='multi-shift-retail',
            owner=self.owner,
        )

        BusinessMembership.objects.create(user=self.owner, business=self.business, role='owner')
        BusinessMembership.objects.create(user=self.cashier1, business=self.business, role='cashier')
        BusinessMembership.objects.create(user=self.cashier2, business=self.business, role='cashier')
        BusinessMembership.objects.create(user=self.cashier3, business=self.business, role='cashier')

        self.branch = Branch.objects.create(
            business=self.business,
            name='Central Branch',
            code='BR-CENTRAL',
        )

        self.terminal1 = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch,
            name='Register 01',
            terminal_code='REG-01',
            device_token='token-reg-01-uuid',
            is_active=True,
        )

        self.terminal2 = POSTerminal.objects.create(
            business=self.business,
            branch=self.branch,
            name='Register 02',
            terminal_code='REG-02',
            device_token='token-reg-02-uuid',
            is_active=True,
        )

        self.category = Category.objects.create(
            business=self.business,
            name='Groceries',
        )

        self.product_apple = Product.objects.create(
            business=self.business,
            category=self.category,
            name='Fresh Apples',
            product_code='APP-001',
            unit_price=Decimal('100.00'),
            cost_price=Decimal('70.00'),
            stock_quantity=100,
        )

        self.product_juice = Product.objects.create(
            business=self.business,
            category=self.category,
            name='Orange Juice',
            product_code='JUC-001',
            unit_price=Decimal('175.00'),
            cost_price=Decimal('120.00'),
            stock_quantity=100,
        )

        self.pay_cash = PaymentMethod.objects.filter(
            business=self.business, code='CASH'
        ).first()
        if not self.pay_cash:
            self.pay_cash = PaymentMethod.objects.create(
                business=self.business,
                name='Cash',
                code='CASH',
                is_active=True,
            )

    def test_two_cashiers_open_shifts_with_different_opening_balances(self):
        """Cashier 1 and Cashier 2 open distinct shifts with 500 and 1000 float."""
        # Alice opens shift on Register 1
        self.client.force_login(self.cashier1)
        self.client.cookies['pos_terminal_token'] = self.terminal1.device_token

        resp1 = self.client.post(reverse('terminal_session_open'), {
            'opening_cash': '500.00',
            'notes': 'Alice morning shift',
        })
        self.assertEqual(resp1.status_code, 302)

        session1 = POSSession.objects.filter(cashier=self.cashier1, status='open').first()
        self.assertIsNotNone(session1)
        self.assertEqual(session1.opening_cash, Decimal('500.00'))

        # Bob opens shift on Register 2
        self.client.force_login(self.cashier2)
        self.client.cookies['pos_terminal_token'] = self.terminal2.device_token

        resp2 = self.client.post(reverse('terminal_session_open'), {
            'opening_cash': '1000.00',
            'notes': 'Bob morning shift',
        })
        self.assertEqual(resp2.status_code, 302)

        session2 = POSSession.objects.filter(cashier=self.cashier2, status='open').first()
        self.assertIsNotNone(session2)
        self.assertEqual(session2.opening_cash, Decimal('1000.00'))

        # Both sessions exist and are separate
        self.assertNotEqual(session1.id, session2.id)
        self.assertEqual(POSSession.objects.filter(business=self.business, status='open').count(), 2)

    def test_sales_and_close_shift_drawer_totals_are_strictly_isolated(self):
        """Verify sales made by Cashier 1 attach to Shift 1 and Cashier 2 to Shift 2."""
        # 1. Open both shifts
        session1 = POSSession.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal1,
            opened_by=self.cashier1,
            cashier=self.cashier1,
            opening_cash=Decimal('500.00'),
            status='open',
        )

        session2 = POSSession.objects.create(
            business=self.business,
            branch=self.branch,
            terminal=self.terminal2,
            opened_by=self.cashier2,
            cashier=self.cashier2,
            opening_cash=Decimal('1000.00'),
            status='open',
        )

        # 2. Alice sells 2 x Apples (200 KES Cash)
        self.client.force_login(self.cashier1)
        self.client.cookies['pos_terminal_token'] = self.terminal1.device_token
        # Access POS to populate session state
        self.client.get(reverse('pos_screen'))

        resp_sale1 = self.client.post(reverse('complete_sale'), {
            'items': [f"{self.product_apple.id},2,100.00"],
            'payments': [f"{self.pay_cash.id},200.00,CASH"],
            'amount_paid': '200.00',
            'change_given': '0.00',
        })
        self.assertEqual(resp_sale1.status_code, 302)

        # 3. Bob sells 2 x Juice (350 KES Cash)
        self.client.force_login(self.cashier2)
        self.client.cookies['pos_terminal_token'] = self.terminal2.device_token
        self.client.get(reverse('pos_screen'))

        resp_sale2 = self.client.post(reverse('complete_sale'), {
            'items': [f"{self.product_juice.id},2,175.00"],
            'payments': [f"{self.pay_cash.id},350.00,CASH"],
            'amount_paid': '350.00',
            'change_given': '0.00',
        })
        self.assertEqual(resp_sale2.status_code, 302)

        # 4. Verify sales are bound to distinct sessions
        sale1 = Sale.objects.filter(cashier=self.cashier1).first()
        sale2 = Sale.objects.filter(cashier=self.cashier2).first()

        self.assertEqual(sale1.session, session1)
        self.assertEqual(sale1.total, Decimal('200.00'))
        self.assertEqual(sale2.session, session2)
        self.assertEqual(sale2.total, Decimal('350.00'))

        self.assertEqual(session1.sales.count(), 1)
        self.assertEqual(session2.sales.count(), 1)

        # 5. Check Alice's Close Shift Preview: Float 500 + Sales 200 = Expected 700
        self.client.force_login(self.cashier1)
        resp_close_preview1 = self.client.get(reverse('terminal_session_close'))
        self.assertEqual(resp_close_preview1.status_code, 200)
        self.assertEqual(resp_close_preview1.context['expected_cash'], Decimal('700.00'))
        self.assertEqual(resp_close_preview1.context['session'].opening_cash, Decimal('500.00'))
        self.assertEqual(resp_close_preview1.context['report_data']['sales_summary']['gross_sales'], 200.0)

        # 6. Check Bob's Close Shift Preview: Float 1000 + Sales 350 = Expected 1350
        self.client.force_login(self.cashier2)
        resp_close_preview2 = self.client.get(reverse('terminal_session_close'))
        self.assertEqual(resp_close_preview2.status_code, 200)
        self.assertEqual(resp_close_preview2.context['expected_cash'], Decimal('1350.00'))
        self.assertEqual(resp_close_preview2.context['session'].opening_cash, Decimal('1000.00'))
        self.assertEqual(resp_close_preview2.context['report_data']['sales_summary']['gross_sales'], 350.0)

        # 7. Alice closes her shift
        self.client.force_login(self.cashier1)
        resp_close1 = self.client.post(reverse('terminal_session_close'), {
            'closing_cash': '700.00',
            'notes': 'Alice shift closed on balance',
        })
        self.assertEqual(resp_close1.status_code, 302)

        session1.refresh_from_db()
        self.assertEqual(session1.status, 'closed')
        zreport1 = ZReport.objects.filter(session=session1).first()
        self.assertIsNotNone(zreport1)
        self.assertEqual(zreport1.report_data['sales_summary']['gross_sales'], 200.0)
        self.assertEqual(zreport1.report_data['cash_management']['opening_float'], 500.0)
        self.assertEqual(zreport1.report_data['cash_management']['expected_cash'], 700.0)

        # 8. Bob's shift is STILL OPEN and can be closed cleanly without error
        session2.refresh_from_db()
        self.assertEqual(session2.status, 'open')

        self.client.force_login(self.cashier2)
        resp_close2 = self.client.post(reverse('terminal_session_close'), {
            'closing_cash': '1350.00',
            'notes': 'Bob shift closed on balance',
        })
        self.assertEqual(resp_close2.status_code, 302)

        session2.refresh_from_db()
        self.assertEqual(session2.status, 'closed')
        zreport2 = ZReport.objects.filter(session=session2).first()
        self.assertIsNotNone(zreport2)
        self.assertEqual(zreport2.report_data['sales_summary']['gross_sales'], 350.0)
        self.assertEqual(zreport2.report_data['cash_management']['opening_float'], 1000.0)
        self.assertEqual(zreport2.report_data['cash_management']['expected_cash'], 1350.0)

    def test_cashier_without_shift_redirected_to_open_shift(self):
        """Cashier 3 without an open shift cannot access POS screen directly."""
        self.client.force_login(self.cashier3)
        response = self.client.get(reverse('pos_screen'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terminal_session_open'), response.url)

    def test_front_office_zreport_view_and_exports(self):
        """Verify /pos/shift/zreport/ loads correctly and cashier can print/export PDF without error."""
        # 1. Open shift for Alice
        self.client.force_login(self.cashier1)
        self.client.cookies['pos_terminal_token'] = self.terminal1.device_token
        self.client.post(reverse('terminal_session_open'), {
            'opening_cash': '500.00',
        })
        session = ZReportService.get_current_session(self.business, user=self.cashier1)
        self.assertIsNotNone(session)

        # 2. Close shift to generate Z-Report
        resp_close = self.client.post(reverse('terminal_session_close'), {
            'closing_cash': '500.00',
            'notes': 'Closed for shift report test',
        })
        self.assertEqual(resp_close.status_code, 302)

        zreport = ZReport.objects.filter(session=session).first()
        self.assertIsNotNone(zreport)

        # 3. Load /pos/shift/zreport/ (must render without NoReverseMatch)
        resp_zreport_page = self.client.get(reverse('front_office_zreport'))
        self.assertEqual(resp_zreport_page.status_code, 200)
        self.assertTemplateUsed(resp_zreport_page, 'pos/front_office/shift_zreport.html')
        self.assertContains(resp_zreport_page, f"Z-Report #{zreport.z_number}")

        # 4. Check print thermal slip
        resp_print = self.client.get(reverse('zreport_print', kwargs={'z_number': zreport.z_number}))
        self.assertEqual(resp_print.status_code, 200)

        # 5. Check PDF export and alias
        resp_pdf = self.client.get(reverse('zreport_export_pdf', kwargs={'z_number': zreport.z_number}))
        self.assertEqual(resp_pdf.status_code, 200)

        resp_pdf_alias = self.client.get(reverse('zreport_pdf', kwargs={'z_number': zreport.z_number}))
        self.assertEqual(resp_pdf_alias.status_code, 200)

