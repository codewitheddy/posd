from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from pos.models import Business, BusinessMembership, Expense, ExpenseCategory


class ExpenseModuleAuditTests(TestCase):

	def setUp(self):
		self.owner = User.objects.create_user(username='owner', password='pass123')
		self.manager = User.objects.create_user(username='manager', password='pass123')
		self.cashier = User.objects.create_user(username='cashier', password='pass123')
		self.viewer = User.objects.create_user(username='viewer', password='pass123')

		self.other_owner = User.objects.create_user(username='other_owner', password='pass123')

		self.business = Business.objects.create(name='Biz One', slug='biz-one', owner=self.owner)
		self.other_business = Business.objects.create(name='Biz Two', slug='biz-two', owner=self.other_owner)

		BusinessMembership.objects.create(user=self.owner, business=self.business, role='owner', is_active=True)
		BusinessMembership.objects.create(user=self.manager, business=self.business, role='manager', is_active=True)
		BusinessMembership.objects.create(user=self.cashier, business=self.business, role='cashier', is_active=True)
		BusinessMembership.objects.create(user=self.viewer, business=self.business, role='viewer', is_active=True)
		BusinessMembership.objects.create(user=self.other_owner, business=self.other_business, role='owner', is_active=True)

		self.cat_one = ExpenseCategory.objects.create(business=self.business, name='Office', is_predefined=False)
		self.cat_two = ExpenseCategory.objects.create(business=self.other_business, name='Other Biz Cat', is_predefined=False)

	def test_cashier_cannot_create_expense(self):
		self.client.force_login(self.cashier)
		response = self.client.post(reverse('expense_create', kwargs={'slug': self.business.slug}), {
			'category': self.cat_one.pk,
			'description': 'Snacks',
			'amount': '100',
			'expense_date': str(date.today()),
			'payment_method': 'cash',
		})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(Expense.objects.filter(business=self.business).count(), 0)

	def test_create_rejects_cross_business_category(self):
		self.client.force_login(self.manager)
		with patch('pos.financial_views.render', return_value=HttpResponse('form', status=200)):
			response = self.client.post(reverse('expense_create', kwargs={'slug': self.business.slug}), {
				'category': self.cat_two.pk,
				'description': 'Cross tenant category attack',
				'amount': '100',
				'expense_date': str(date.today()),
				'payment_method': 'cash',
			})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(Expense.objects.filter(business=self.business).count(), 0)

	def test_edit_rejects_negative_amount(self):
		expense = Expense.objects.create(
			business=self.business,
			category=self.cat_one,
			description='Internet',
			amount=Decimal('1000.00'),
			expense_date=date.today(),
			payment_method='cash',
			recorded_by=self.owner,
		)

		self.client.force_login(self.manager)
		with patch('pos.financial_views.render', return_value=HttpResponse('form', status=200)):
			response = self.client.post(reverse('expense_edit', kwargs={'slug': self.business.slug, 'pk': expense.pk}), {
				'category': self.cat_one.pk,
				'description': 'Internet',
				'amount': '-5',
				'expense_date': str(date.today()),
				'payment_method': 'cash',
			})
		self.assertEqual(response.status_code, 200)

		expense.refresh_from_db()
		self.assertEqual(expense.amount, Decimal('1000.00'))

	def test_export_respects_category_and_payment_filters(self):
		cat_two_local = ExpenseCategory.objects.create(business=self.business, name='Transport', is_predefined=False)
		Expense.objects.create(
			business=self.business,
			category=self.cat_one,
			description='Office rent',
			amount=Decimal('500.00'),
			expense_date=date.today(),
			payment_method='cash',
			recorded_by=self.owner,
		)
		Expense.objects.create(
			business=self.business,
			category=cat_two_local,
			description='Fuel',
			amount=Decimal('700.00'),
			expense_date=date.today(),
			payment_method='mpesa',
			recorded_by=self.owner,
		)

		self.client.force_login(self.manager)
		response = self.client.get(reverse('expense_export_csv', kwargs={'slug': self.business.slug}), {
			'period': 'month',
			'category': str(cat_two_local.pk),
			'payment_method': 'mpesa',
		})
		self.assertEqual(response.status_code, 200)

		body = response.content.decode('utf-8')
		self.assertIn('Fuel', body)
		self.assertNotIn('Office rent', body)

	def test_create_rejects_invalid_attachment_type(self):
		self.client.force_login(self.manager)
		bad_file = SimpleUploadedFile('malware.exe', b'not-a-real-exe', content_type='application/octet-stream')
		with patch('pos.financial_views.render', return_value=HttpResponse('form', status=200)):
			response = self.client.post(reverse('expense_create', kwargs={'slug': self.business.slug}), {
				'category': self.cat_one.pk,
				'description': 'Test with bad attachment',
				'amount': '200',
				'expense_date': str(date.today()),
				'payment_method': 'cash',
				'attachment': bad_file,
			})

		self.assertEqual(response.status_code, 200)
		self.assertFalse(Expense.objects.filter(description='Test with bad attachment').exists())

	def test_viewer_cannot_access_finance_pages(self):
		self.client.force_login(self.viewer)

		for url_name in ('expense_list', 'profit_dashboard', 'pl_statement'):
			response = self.client.get(reverse(url_name, kwargs={'slug': self.business.slug}))
			self.assertEqual(response.status_code, 302)
			self.assertIn(reverse('dashboard', kwargs={'slug': self.business.slug}), response.url)

	def test_pl_export_custom_period_respects_date_range(self):
		self.client.force_login(self.manager)
		# In-range expense
		Expense.objects.create(
			business=self.business,
			category=self.cat_one,
			description='In range',
			amount=Decimal('100.00'),
			expense_date=date(2026, 4, 5),
			payment_method='cash',
			recorded_by=self.owner,
		)
		# Out-of-range expense
		Expense.objects.create(
			business=self.business,
			category=self.cat_one,
			description='Out of range',
			amount=Decimal('900.00'),
			expense_date=date(2026, 3, 5),
			payment_method='cash',
			recorded_by=self.owner,
		)

		response = self.client.get(reverse('pl_statement', kwargs={'slug': self.business.slug}), {
			'period': 'custom',
			'date_from': '2026-04-01',
			'date_to': '2026-04-30',
			'export': 'csv',
		})
		self.assertEqual(response.status_code, 200)

		body = response.content.decode('utf-8')
		self.assertIn('Period: 2026-04-01 to 2026-04-30', body)
		self.assertIn('Total Expenses,100', body)
		self.assertNotIn('Total Expenses,1000', body)

	def test_expense_export_rejects_oversized_custom_range(self):
		self.client.force_login(self.manager)
		response = self.client.get(reverse('expense_export_csv', kwargs={'slug': self.business.slug}), {
			'period': 'custom',
			'date_from': '2024-01-01',
			'date_to': '2026-04-30',
		})
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse('expense_list', kwargs={'slug': self.business.slug}), response.url)

	def test_pl_export_rejects_oversized_custom_range(self):
		self.client.force_login(self.manager)
		response = self.client.get(reverse('pl_statement', kwargs={'slug': self.business.slug}), {
			'period': 'custom',
			'date_from': '2024-01-01',
			'date_to': '2026-04-30',
			'export': 'csv',
		})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse('pl_statement', kwargs={'slug': self.business.slug}))
