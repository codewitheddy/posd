"""
Management command to record a subscription payment
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from pos.models import Business, SubscriptionPayment
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Record a subscription payment for a business'

    def add_arguments(self, parser):
        parser.add_argument('slug', type=str, help='Business slug')
        parser.add_argument('amount', type=float, help='Payment amount')
        parser.add_argument(
            '--currency',
            type=str,
            default='KES',
            help='Currency code (default: KES)',
        )
        parser.add_argument(
            '--method',
            type=str,
            default='mpesa',
            choices=['mpesa', 'bank_transfer', 'cash', 'card', 'paypal', 'other'],
            help='Payment method',
        )
        parser.add_argument(
            '--reference',
            type=str,
            default='',
            help='Payment reference/transaction ID',
        )
        parser.add_argument(
            '--plan',
            type=str,
            default='paid',
            choices=['trial', 'paid'],
            help='Subscription plan',
        )
        parser.add_argument(
            '--months',
            type=int,
            default=12,
            help='Number of months (default: 12 for annual subscription)',
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Payment date (YYYY-MM-DD, default: today)',
        )
        parser.add_argument(
            '--notes',
            type=str,
            default='',
            help='Additional notes',
        )

    def handle(self, *args, **options):
        slug = options['slug']
        amount = options['amount']
        currency = options['currency']
        method = options['method']
        reference = options['reference']
        plan = options['plan']
        months = options['months']
        notes = options['notes']

        # Parse payment date
        if options['date']:
            try:
                payment_date = timezone.make_aware(datetime.strptime(options['date'], '%Y-%m-%d'))
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid date format. Use YYYY-MM-DD'))
                return
        else:
            payment_date = timezone.now()

        # Get business
        try:
            business = Business.objects.get(slug=slug)
        except Business.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Business with slug "{slug}" not found'))
            return

        # Calculate period
        period_start = payment_date.date()
        period_end = (payment_date + timedelta(days=30 * months)).date()

        # Get admin user for recorded_by
        admin_user = User.objects.filter(is_superuser=True).first()

        # Create payment record
        payment = SubscriptionPayment.objects.create(
            business=business,
            amount=amount,
            currency=currency,
            payment_method=method,
            payment_reference=reference,
            payment_date=payment_date,
            period_start=period_start,
            period_end=period_end,
            plan=plan,
            status='completed',
            notes=notes,
            recorded_by=admin_user
        )

        # Display success message
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('PAYMENT RECORDED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('='*60))
        self.stdout.write(f'Business: {business.name}')
        self.stdout.write(f'Amount: {currency} {amount:,.2f}')
        self.stdout.write(f'Payment Method: {payment.get_payment_method_display()}')
        self.stdout.write(f'Reference: {reference or "N/A"}')
        self.stdout.write(f'Payment Date: {payment_date.strftime("%Y-%m-%d")}')
        self.stdout.write(f'Plan: {payment.get_plan_display()}')
        self.stdout.write(f'Period: {period_start} to {period_end}')
        self.stdout.write(f'License Expires: {business.license_expires_at.strftime("%Y-%m-%d %H:%M")}')
        self.stdout.write(f'License Status: {business.license_status}')
        self.stdout.write(self.style.SUCCESS('\n✓ Business license has been updated'))
