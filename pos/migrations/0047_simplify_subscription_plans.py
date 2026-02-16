# Generated migration to simplify subscription plans

from django.db import migrations, models


def update_subscription_plans(apps, schema_editor):
    """Update existing subscription plans to new simplified structure"""
    Business = apps.get_model('pos', 'Business')
    SubscriptionPayment = apps.get_model('pos', 'SubscriptionPayment')
    
    # Update Business subscription_plan
    # Map old plans to new plans:
    # 'free' -> 'trial'
    # 'basic', 'professional', 'enterprise' -> 'paid'
    
    Business.objects.filter(subscription_plan='free').update(subscription_plan='trial')
    Business.objects.filter(subscription_plan__in=['basic', 'professional', 'enterprise']).update(subscription_plan='paid')
    
    # Update SubscriptionPayment plan
    SubscriptionPayment.objects.filter(plan='free').update(plan='trial')
    SubscriptionPayment.objects.filter(plan__in=['basic', 'professional', 'enterprise']).update(plan='paid')


def reverse_update(apps, schema_editor):
    """Reverse migration - map back to old structure"""
    Business = apps.get_model('pos', 'Business')
    SubscriptionPayment = apps.get_model('pos', 'SubscriptionPayment')
    
    # Map back: 'trial' -> 'free', 'paid' -> 'professional'
    Business.objects.filter(subscription_plan='trial').update(subscription_plan='free')
    Business.objects.filter(subscription_plan='paid').update(subscription_plan='professional')
    
    SubscriptionPayment.objects.filter(plan='trial').update(plan='free')
    SubscriptionPayment.objects.filter(plan='paid').update(plan='professional')


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0046_update_subscription_plans'),
    ]

    operations = [
        migrations.AlterField(
            model_name='business',
            name='subscription_plan',
            field=models.CharField(
                choices=[('trial', 'Free Trial (30 Days)'), ('paid', 'Annual Subscription')],
                default='trial',
                max_length=50
            ),
        ),
        migrations.AlterField(
            model_name='subscriptionpayment',
            name='plan',
            field=models.CharField(
                choices=[('trial', 'Free Trial'), ('paid', 'Annual Subscription')],
                max_length=50
            ),
        ),
        migrations.RunPython(update_subscription_plans, reverse_update),
    ]
