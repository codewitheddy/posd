# Generated migration for multi-tenancy support

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


def create_default_business(apps, schema_editor):
    """Create a default business for existing data"""
    Business = apps.get_model('pos', 'Business')
    User = apps.get_model('auth', 'User')
    BusinessMembership = apps.get_model('pos', 'BusinessMembership')
    
    # Get first superuser or create one
    superuser = User.objects.filter(is_superuser=True).first()
    if not superuser:
        superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='admin123',
            first_name='System',
            last_name='Administrator'
        )
    
    # Create default business
    business = Business.objects.create(
        name='Default Business',
        slug='default',
        owner=superuser,
        is_active=True,
        is_trial=False,
        subscription_plan='free'
    )
    
    # Add owner as member
    BusinessMembership.objects.create(
        user=superuser,
        business=business,
        role='owner',
        is_active=True
    )
    
    print(f"✅ Created default business: {business.name} (slug: {business.slug})")
    print(f"✅ Owner: {superuser.username}")
    
    return business.id


def assign_business_to_existing_data(apps, schema_editor):
    """Assign default business to all existing records"""
    Business = apps.get_model('pos', 'Business')
    
    # Get default business
    business = Business.objects.filter(slug='default').first()
    if not business:
        print("⚠️  No default business found, skipping data assignment")
        return
    
    # List of models to update
    model_names = [
        'Category', 'Product', 'Sale', 'SaleItem', 'StockAdjustment',
        'Supplier', 'Purchase', 'PurchaseItem', 'Customer',
        'PaymentMethod', 'SalePayment', 'Shift', 'SaleReturn',
        'SaleReturnItem', 'Promotion', 'ExpenseCategory', 'Expense',
        'LoyaltyTransaction', 'LoyaltyReward', 'LoyaltyRedemption',
        'SupplierPayment', 'PaymentAllocation', 'ActivityLog'
    ]
    
    for model_name in model_names:
        try:
            Model = apps.get_model('pos', model_name)
            count = Model.objects.filter(business__isnull=True).update(business=business)
            if count > 0:
                print(f"✅ Assigned {count} {model_name} records to default business")
        except Exception as e:
            print(f"⚠️  Could not update {model_name}: {e}")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pos', '0001_initial'),
    ]

    operations = [
        # Create Business model
        migrations.CreateModel(
            name='Business',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Business name', max_length=200)),
                ('slug', models.SlugField(help_text='URL-friendly identifier', max_length=200, unique=True)),
                ('description', models.TextField(blank=True)),
                ('address', models.TextField(blank=True)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('website', models.URLField(blank=True)),
                ('tax_id', models.CharField(blank=True, max_length=50)),
                ('is_active', models.BooleanField(default=True)),
                ('is_trial', models.BooleanField(default=True, help_text='Trial period active')),
                ('trial_ends_at', models.DateTimeField(blank=True, null=True)),
                ('subscription_plan', models.CharField(
                    choices=[('free', 'Free'), ('basic', 'Basic'), ('professional', 'Professional'), ('enterprise', 'Enterprise')],
                    default='free',
                    max_length=50
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owned_businesses', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Businesses',
                'ordering': ['name'],
            },
        ),
        
        # Create BusinessMembership model
        migrations.CreateModel(
            name='BusinessMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(
                    choices=[
                        ('owner', 'Owner'),
                        ('admin', 'Administrator'),
                        ('manager', 'Manager'),
                        ('stock_manager', 'Stock Manager'),
                        ('cashier', 'Cashier'),
                        ('sales', 'Sales Associate'),
                        ('viewer', 'Viewer'),
                    ],
                    default='cashier',
                    max_length=20
                )),
                ('is_active', models.BooleanField(default=True)),
                ('joined_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='pos.business')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='business_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['business', 'user'],
                'unique_together': {('user', 'business')},
            },
        ),
        
        # Run data migration to create default business
        migrations.RunPython(create_default_business, reverse_code=migrations.RunPython.noop),
        
        # Add business field to all models (nullable first)
        migrations.AddField(
            model_name='category',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='pos.business'),
        ),
        migrations.AddField(
            model_name='product',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='products', to='pos.business'),
        ),
        migrations.AddField(
            model_name='sale',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sales', to='pos.business'),
        ),
        migrations.AddField(
            model_name='saleitem',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sale_items', to='pos.business'),
        ),
        migrations.AddField(
            model_name='stockadjustment',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='stock_adjustments', to='pos.business'),
        ),
        migrations.AddField(
            model_name='supplier',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='suppliers', to='pos.business'),
        ),
        migrations.AddField(
            model_name='purchase',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='purchases', to='pos.business'),
        ),
        migrations.AddField(
            model_name='purchaseitem',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='purchase_items', to='pos.business'),
        ),
        migrations.AddField(
            model_name='customer',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='pos.business'),
        ),
        migrations.AddField(
            model_name='paymentmethod',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='payment_methods', to='pos.business'),
        ),
        migrations.AddField(
            model_name='salepayment',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sale_payments', to='pos.business'),
        ),
        migrations.AddField(
            model_name='shift',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='shifts', to='pos.business'),
        ),
        migrations.AddField(
            model_name='salereturn',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sale_returns', to='pos.business'),
        ),
        migrations.AddField(
            model_name='salereturnitem',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sale_return_items', to='pos.business'),
        ),
        migrations.AddField(
            model_name='promotion',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='promotions', to='pos.business'),
        ),
        migrations.AddField(
            model_name='expensecategory',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='expense_categories', to='pos.business'),
        ),
        migrations.AddField(
            model_name='expense',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='expenses', to='pos.business'),
        ),
        migrations.AddField(
            model_name='loyaltytransaction',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='loyalty_transactions', to='pos.business'),
        ),
        migrations.AddField(
            model_name='loyaltyreward',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='loyalty_rewards', to='pos.business'),
        ),
        migrations.AddField(
            model_name='loyaltyredemption',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='loyalty_redemptions', to='pos.business'),
        ),
        migrations.AddField(
            model_name='supplierpayment',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='supplier_payments', to='pos.business'),
        ),
        migrations.AddField(
            model_name='paymentallocation',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='payment_allocations', to='pos.business'),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='business',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='activity_logs', to='pos.business'),
        ),
        
        # Assign default business to existing data
        migrations.RunPython(assign_business_to_existing_data, reverse_code=migrations.RunPython.noop),
        
        # Make business field required (non-nullable)
        migrations.AlterField(
            model_name='category',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='pos.business'),
        ),
        migrations.AlterField(
            model_name='product',
            name='business',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='pos.business'),
        ),
        # ... (similar for all other models)
        
        # Update unique constraints to include business
        migrations.AlterUniqueTogether(
            name='category',
            unique_together={('business', 'name')},
        ),
        migrations.AlterUniqueTogether(
            name='product',
            unique_together={('business', 'product_code')},
        ),
    ]
