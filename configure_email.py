import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
django.setup()

from pos.models import BusinessEmailSettings, Business

print("Configuring Ropenix Kenya email settings...")
print()

business = Business.objects.first()
if not business:
    print("❌ No business found! Please create a business first.")
    sys.exit(1)

print(f"Business: {business.name}")

settings, created = BusinessEmailSettings.objects.get_or_create(
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
    print("✅ Email settings created!")
else:
    print("✅ Email settings already exist")

print()
print(f"Admin emails: {settings.admin_emails}")
print(f"Manager emails: {settings.manager_emails}")
print()
print("Email notifications enabled:")
print(f"  • Purchase orders: {'✅' if settings.send_purchase_orders else '❌'}")
print(f"  • Payment confirmations: {'✅' if settings.send_payment_confirmations else '❌'}")
print(f"  • GRN notifications: {'✅' if settings.send_grn_notifications else '❌'}")
print(f"  • License reminders: {'✅' if settings.send_license_reminders else '❌'}")
print(f"  • Low stock alerts: {'✅' if settings.send_low_stock_alerts else '❌'}")
print(f"  • Daily summaries: {'✅' if settings.send_daily_summaries else '❌'}")
print()
print("🎉 Configuration complete!")
print()
print("Next steps:")
print("  1. Test: python manage.py send_test_email ropenixkenya@gmail.com")
print("  2. Create a purchase order to test automatic emails")
print("  3. Complete a sale and test the email receipt button")
