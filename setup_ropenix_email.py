"""
Quick setup script for Ropenix Kenya email configuration
Run this after creating your .env file with Gmail app password
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from pos.models import BusinessEmailSettings, Business, Supplier, Customer
from django.core.mail import send_mail
from django.conf import settings


def main():
    print("=" * 60)
    print("Ropenix Kenya - Email Configuration Setup")
    print("=" * 60)
    print()
    
    # Check email configuration
    print("1. Checking email configuration...")
    print(f"   Email Backend: {settings.EMAIL_BACKEND}")
    print(f"   SMTP Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT}")
    print(f"   From Email: {settings.DEFAULT_FROM_EMAIL}")
    
    if settings.EMAIL_HOST_USER:
        print(f"   SMTP User: {settings.EMAIL_HOST_USER}")
        if settings.EMAIL_HOST_USER == 'ropenixkenya@gmail.com':
            print("   ✅ Correct email configured!")
        else:
            print(f"   ⚠️  Expected: ropenixkenya@gmail.com")
    else:
        print("   ❌ EMAIL_HOST_USER not configured!")
        print("   Please create .env file with your Gmail app password")
        return
    
    if not settings.EMAIL_HOST_PASSWORD:
        print("   ❌ EMAIL_HOST_PASSWORD not configured!")
        print("   Please add your Gmail app password to .env file")
        return
    else:
        print("   ✅ SMTP password configured")
    
    print()
    
    # Test email sending
    print("2. Testing email connection...")
    try:
        send_mail(
            subject='Ropenix POS - Email Test',
            message='This is a test email from your Ropenix POS system. Email configuration is working!',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['ropenixkenya@gmail.com'],
            fail_silently=False,
        )
        print("   ✅ Test email sent successfully!")
        print("   Check ropenixkenya@gmail.com inbox")
    except Exception as e:
        print(f"   ❌ Failed to send test email: {str(e)}")
        print()
        print("   Troubleshooting:")
        print("   - Verify your Gmail app password is correct")
        print("   - Check that 2-factor authentication is enabled")
        print("   - Make sure there are no spaces in the password")
        return
    
    print()
    
    # Configure business email settings
    print("3. Configuring business email settings...")
    try:
        business = Business.objects.first()
        if not business:
            print("   ❌ No business found! Please create a business first.")
            return
        
        print(f"   Business: {business.name}")
        
        settings_obj, created = BusinessEmailSettings.objects.get_or_create(
            business=business,
            defaults={
                'admin_emails': 'ropenixkenya@gmail.com',
                'manager_emails': 'ropenixkenya@gmail.com',
                'send_purchase_orders': True,
                'send_payment_confirmations': True,
                'send_grn_notifications': True,
                'send_license_reminders': True,
                'send_low_stock_alerts': True,
                'send_daily_summaries': True,
            }
        )
        
        if created:
            print("   ✅ Email settings created!")
        else:
            print("   ✅ Email settings already exist")
        
        print(f"   Admin emails: {settings_obj.admin_emails}")
        print(f"   Manager emails: {settings_obj.manager_emails}")
        print(f"   Purchase orders: {'Enabled' if settings_obj.send_purchase_orders else 'Disabled'}")
        print(f"   Payment confirmations: {'Enabled' if settings_obj.send_payment_confirmations else 'Disabled'}")
        print(f"   GRN notifications: {'Enabled' if settings_obj.send_grn_notifications else 'Disabled'}")
        print(f"   License reminders: {'Enabled' if settings_obj.send_license_reminders else 'Disabled'}")
        print(f"   Low stock alerts: {'Enabled' if settings_obj.send_low_stock_alerts else 'Disabled'}")
        print(f"   Daily summaries: {'Enabled' if settings_obj.send_daily_summaries else 'Disabled'}")
        
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        return
    
    print()
    
    # Check suppliers
    print("4. Checking suppliers...")
    suppliers = Supplier.objects.filter(business=business)
    suppliers_with_email = suppliers.exclude(email='').exclude(email__isnull=True)
    
    print(f"   Total suppliers: {suppliers.count()}")
    print(f"   Suppliers with email: {suppliers_with_email.count()}")
    
    if suppliers_with_email.exists():
        print("   Suppliers with email configured:")
        for supplier in suppliers_with_email[:5]:
            print(f"     - {supplier.name}: {supplier.email}")
        if suppliers_with_email.count() > 5:
            print(f"     ... and {suppliers_with_email.count() - 5} more")
    else:
        print("   ⚠️  No suppliers have email configured")
        print("   Add supplier emails to enable automatic notifications")
    
    print()
    
    # Check customers
    print("5. Checking customers...")
    customers = Customer.objects.filter(business=business)
    customers_with_email = customers.exclude(email='').exclude(email__isnull=True)
    
    print(f"   Total customers: {customers.count()}")
    print(f"   Customers with email: {customers_with_email.count()}")
    
    if customers_with_email.exists():
        print(f"   ✅ {customers_with_email.count()} customers can receive receipts via email")
    else:
        print("   ⚠️  No customers have email configured")
        print("   Add customer emails to enable receipt emailing")
    
    print()
    
    # Summary
    print("=" * 60)
    print("Setup Complete! 🎉")
    print("=" * 60)
    print()
    print("✅ Email system is configured and ready to use!")
    print()
    print("What happens now:")
    print("  • Purchase orders will be emailed to suppliers automatically")
    print("  • Payment confirmations will be sent automatically")
    print("  • GRN notifications will be sent automatically")
    print("  • You can email receipts to customers manually")
    print()
    print("Scheduled tasks (optional):")
    print("  • License expiry check: python manage.py check_license_expiry")
    print("  • Low stock alerts: python manage.py check_low_stock")
    print("  • Daily summary: python manage.py send_daily_summary")
    print()
    print("Next steps:")
    print("  1. Add supplier emails to enable automatic notifications")
    print("  2. Add customer emails to enable receipt emailing")
    print("  3. Set up Windows Task Scheduler for automated emails")
    print("  4. Test by creating a purchase order or making a payment")
    print()
    print("For detailed instructions, see: ROPENIX_EMAIL_SETUP_GUIDE.md")
    print()


if __name__ == '__main__':
    main()
