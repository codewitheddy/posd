# Data migration to assign existing loyalty rewards to businesses

from django.db import migrations


def assign_rewards_to_first_business(apps, schema_editor):
    """Assign all loyalty rewards without a business to the first business"""
    LoyaltyReward = apps.get_model('pos', 'LoyaltyReward')
    Business = apps.get_model('pos', 'Business')
    
    # Get rewards without a business
    rewards_without_business = LoyaltyReward.objects.filter(business__isnull=True)
    
    if rewards_without_business.exists():
        # Get the first business (or create a default one if none exists)
        first_business = Business.objects.first()
        
        if first_business:
            # Assign all rewards to the first business
            rewards_without_business.update(business=first_business)
            print(f"Assigned {rewards_without_business.count()} loyalty rewards to business: {first_business.name}")
        else:
            print("Warning: No businesses found. Loyalty rewards remain unassigned.")
            print("Please create a business and manually assign the rewards.")


def reverse_assignment(apps, schema_editor):
    """Reverse the assignment (set business to null)"""
    LoyaltyReward = apps.get_model('pos', 'LoyaltyReward')
    LoyaltyReward.objects.all().update(business=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0034_add_business_to_loyalty_reward'),
    ]

    operations = [
        migrations.RunPython(assign_rewards_to_first_business, reverse_assignment),
    ]
