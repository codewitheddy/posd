from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0080_apikey'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('code', models.CharField(max_length=20)),
                ('address', models.TextField()),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('is_active', models.BooleanField(default=True)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branches', to='pos.business')),
            ],
            options={
                'verbose_name_plural': 'branches',
                'unique_together': {('business', 'name'), ('business', 'code')},
            },
        ),
        migrations.CreateModel(
            name='BranchMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('manager', 'Manager'), ('stock_manager', 'Stock Manager'), ('cashier', 'Cashier'), ('sales', 'Sales Associate'), ('viewer', 'Viewer')], max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='pos.branch')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('user', 'branch')},
            },
        ),
        migrations.CreateModel(
            name='BranchStock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.DecimalField(decimal_places=3, default=0, max_digits=10)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_records', to='pos.branch')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_stocks', to='pos.product')),
            ],
            options={
                'unique_together': {('branch', 'product')},
            },
        ),
        migrations.AddIndex(
            model_name='branchstock',
            index=models.Index(fields=['branch', 'product'], name='pos_branchs_branch__idx'),
        ),
        migrations.CreateModel(
            name='StockTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(editable=False, max_length=30, unique=True)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('in_transit', 'In Transit'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending', max_length=20)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_transfers', to='pos.business')),
                ('destination_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_in', to='pos.branch')),
                ('initiated_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='initiated_transfers', to=settings.AUTH_USER_MODEL)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='pos.product')),
                ('source_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_out', to='pos.branch')),
            ],
        ),
        migrations.AddIndex(
            model_name='stocktransfer',
            index=models.Index(fields=['business', '-created_at'], name='pos_stocktr_busines_idx'),
        ),
        migrations.AddIndex(
            model_name='stocktransfer',
            index=models.Index(fields=['source_branch', 'status'], name='pos_stocktr_source__idx'),
        ),
        migrations.AddIndex(
            model_name='stocktransfer',
            index=models.Index(fields=['destination_branch', 'status'], name='pos_stocktr_dest___idx'),
        ),
        migrations.CreateModel(
            name='BranchPriceOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.DecimalField(decimal_places=2, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='price_overrides', to='pos.branch')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='price_overrides', to='pos.product')),
            ],
            options={
                'unique_together': {('branch', 'product')},
            },
        ),
        # Nullable branch FK on existing models
        migrations.AddField(
            model_name='sale',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sales', to='pos.branch'),
        ),
        migrations.AddField(
            model_name='purchase',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchases', to='pos.branch'),
        ),
        migrations.AddField(
            model_name='stockadjustment',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_adjustments', to='pos.branch'),
        ),
        migrations.AddField(
            model_name='possession',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pos_sessions', to='pos.branch'),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='branch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to='pos.branch'),
        ),
    ]
