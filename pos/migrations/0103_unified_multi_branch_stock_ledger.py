from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


def backfill_multi_branch_data(apps, schema_editor):
    Business = apps.get_model('pos', 'Business')
    Branch = apps.get_model('pos', 'Branch')
    BranchMembership = apps.get_model('pos', 'BranchMembership')
    BranchStock = apps.get_model('pos', 'BranchStock')
    Product = apps.get_model('pos', 'Product')
    StockMovement = apps.get_model('pos', 'StockMovement')
    POSTerminal = apps.get_model('pos', 'POSTerminal')
    BusinessMembership = apps.get_model('pos', 'BusinessMembership')

    for business in Business.objects.all():
        # 1. Ensure HQ Branch exists
        hq_branch = Branch.objects.filter(business=business, is_hq=True).first()
        if not hq_branch:
            hq_branch = Branch.objects.filter(business=business, is_default=True).first()
        if not hq_branch:
            hq_branch = Branch.objects.filter(business=business).first()
        if not hq_branch:
            hq_branch = Branch.objects.create(
                business=business,
                name='Main Branch (HQ)',
                code='HQ-001',
                address=getattr(business, 'address', 'Central Headquarters') or 'Central Headquarters',
                phone=getattr(business, 'phone', '') or '',
                email=getattr(business, 'email', '') or '',
                is_active=True,
                is_default=True,
                is_hq=True,
            )
        else:
            if not hq_branch.is_hq:
                hq_branch.is_hq = True
                hq_branch.save(update_fields=['is_hq'])

        # 2. Link unassigned terminals to HQ
        POSTerminal.objects.filter(business=business, branch__isnull=True).update(branch=hq_branch)

        # 3. Backfill Product inventory into HQ BranchStock and create initial ledger entries
        for product in Product.objects.filter(business=business):
            b_stock, created = BranchStock.objects.get_or_create(
                branch=hq_branch,
                product=product,
                defaults={
                    'quantity': product.stock_quantity or Decimal('0.000'),
                    'average_cost': product.cost_price or Decimal('0.00'),
                    'reorder_level': getattr(product, 'low_stock_threshold', Decimal('10.000')) or Decimal('10.000'),
                }
            )
            if not created and (b_stock.average_cost == 0 and product.cost_price):
                b_stock.average_cost = product.cost_price
                b_stock.save(update_fields=['average_cost'])

            # Create initial StockMovement ledger record if none exists
            if not StockMovement.objects.filter(branch=hq_branch, product=product).exists() and b_stock.quantity != 0:
                StockMovement.objects.create(
                    business=business,
                    branch=hq_branch,
                    product=product,
                    quantity_delta=b_stock.quantity,
                    unit_cost=b_stock.average_cost,
                    total_cost=(b_stock.quantity * b_stock.average_cost).quantize(Decimal('0.01')),
                    movement_type='initial_count',
                    balance_after=b_stock.quantity,
                    resulted_in_negative_stock=b_stock.quantity < 0,
                    note='Initial stock count backfilled during multi-branch migration',
                )

        # 4. Backfill user memberships to HQ
        for bm in BusinessMembership.objects.filter(business=business):
            if not BranchMembership.objects.filter(user=bm.user, branch__business=business).exists():
                role = 'branch_manager' if bm.role in ('owner', 'admin', 'manager') else 'cashier'
                BranchMembership.objects.create(
                    user=bm.user,
                    branch=hq_branch,
                    role=role,
                    is_home_branch=True,
                    is_active=bm.is_active,
                )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0102_backfill_print_receipt_permissions'),
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Branch fields
        migrations.AddField(
            model_name='branch',
            name='is_hq',
            field=models.BooleanField(default=False, help_text='Designates this branch as the central HQ. Exactly one branch per business can be HQ.'),
        ),
        # BranchMembership fields
        migrations.AddField(
            model_name='branchmembership',
            name='is_home_branch',
            field=models.BooleanField(default=False, help_text='Default home branch for initial user scoping'),
        ),
        migrations.AlterField(
            model_name='branchmembership',
            name='role',
            field=models.CharField(
                choices=[
                    ('cashier', 'Cashier'), ('branch_manager', 'Branch Manager'),
                    ('hq_admin', 'HQ Admin'), ('manager', 'Manager'),
                    ('stock_manager', 'Stock Manager'), ('sales', 'Sales Associate'),
                    ('viewer', 'Viewer')
                ],
                default='cashier',
                max_length=20
            ),
        ),
        # BranchStock fields
        migrations.AddField(
            model_name='branchstock',
            name='average_cost',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Moving weighted average cost per unit', max_digits=12),
        ),
        migrations.AddField(
            model_name='branchstock',
            name='reorder_level',
            field=models.DecimalField(decimal_places=3, default=Decimal('10.000'), help_text='Branch-specific reorder trigger level', max_digits=10),
        ),
        # StockMovement model
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity_delta', models.DecimalField(decimal_places=3, help_text='Signed (+ for increase, - for decrease)', max_digits=10)),
                ('unit_cost', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('total_cost', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('movement_type', models.CharField(choices=[
                    ('sale', 'Sale'), ('sale_return', 'Sale Return'),
                    ('purchase_in', 'Purchase / GRN In'), ('supplier_return_out', 'Supplier Return Out'),
                    ('hq_dispatch_out', 'HQ Dispatch Out'), ('branch_receipt_in', 'Branch Receipt In'),
                    ('transfer_out', 'Transfer Out'), ('transfer_in', 'Transfer In'),
                    ('manual_adjustment', 'Manual Adjustment'), ('damage_writeoff', 'Damage Write-off'),
                    ('expiry_writeoff', 'Expiry Write-off'), ('initial_count', 'Initial Stock Count')
                ], db_index=True, max_length=30)),
                ('object_id', models.CharField(blank=True, max_length=64, null=True)),
                ('reference_number', models.CharField(blank=True, help_text='Human readable document number', max_length=100)),
                ('balance_after', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('resulted_in_negative_stock', models.BooleanField(default=False)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='pos.branch')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_movements', to='pos.business')),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='contenttypes.contenttype')),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='stock_movements', to=settings.AUTH_USER_MODEL)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='pos.product')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['business', '-created_at'], name='pos_stockmv_busines_idx'),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['branch', 'product', '-created_at'], name='pos_stockmv_branch_p_idx'),
        ),
        migrations.AddIndex(
            model_name='stockmovement',
            index=models.Index(fields=['movement_type', '-created_at'], name='pos_stockmv_movtype_idx'),
        ),
        # StockRequisition model
        migrations.CreateModel(
            name='StockRequisition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference_number', models.CharField(editable=False, max_length=30, unique=True)),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending Approval'), ('approved', 'Approved'),
                    ('rejected', 'Rejected'), ('dispatched', 'In Transit / Dispatched'),
                    ('partially_fulfilled', 'Partially Fulfilled'), ('fulfilled', 'Fulfilled'),
                    ('cancelled', 'Cancelled')
                ], db_index=True, default='pending', max_length=25)),
                ('notes', models.TextField(blank=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='requisitions_approved', to=settings.AUTH_USER_MODEL)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_requisitions', to='pos.business')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requisitions_requested', to=settings.AUTH_USER_MODEL)),
                ('requesting_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requisitions_made', to='pos.branch')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='stockrequisition',
            index=models.Index(fields=['business', '-created_at'], name='pos_stockrq_busines_idx'),
        ),
        migrations.AddIndex(
            model_name='stockrequisition',
            index=models.Index(fields=['requesting_branch', 'status'], name='pos_stockrq_branch_s_idx'),
        ),
        # StockRequisitionItem model
        migrations.CreateModel(
            name='StockRequisitionItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('approved_quantity', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('dispatched_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), max_digits=10)),
                ('received_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), max_digits=10)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requisition_items', to='pos.product')),
                ('requisition', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='pos.stockrequisition')),
            ],
        ),
        # StockTransferRequest model
        migrations.CreateModel(
            name='StockTransferRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference_number', models.CharField(editable=False, max_length=30, unique=True)),
                ('reason', models.TextField(blank=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('status', models.CharField(choices=[
                    ('pending', 'Pending Approval'), ('approved', 'Approved'),
                    ('rejected', 'Rejected'), ('dispatched', 'In Transit / Dispatched'),
                    ('partially_received', 'Partially Received'), ('completed', 'Completed'),
                    ('cancelled', 'Cancelled')
                ], db_index=True, default='pending', max_length=25)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transfers_approved', to=settings.AUTH_USER_MODEL)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transfer_requests', to='pos.business')),
                ('destination_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfer_requests_in', to='pos.branch')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers_requested', to=settings.AUTH_USER_MODEL)),
                ('source_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfer_requests_out', to='pos.branch')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='stocktransferrequest',
            index=models.Index(fields=['business', '-created_at'], name='pos_stocktr_busreq_idx'),
        ),
        migrations.AddIndex(
            model_name='stocktransferrequest',
            index=models.Index(fields=['source_branch', 'status'], name='pos_stocktr_src_st_idx'),
        ),
        migrations.AddIndex(
            model_name='stocktransferrequest',
            index=models.Index(fields=['destination_branch', 'status'], name='pos_stocktr_dst_st_idx'),
        ),
        # StockTransferItem model
        migrations.CreateModel(
            name='StockTransferItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('approved_quantity', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('dispatched_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), max_digits=10)),
                ('received_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), max_digits=10)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfer_items', to='pos.product')),
                ('transfer_request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='pos.stocktransferrequest')),
            ],
        ),
        # Dispatch model
        migrations.CreateModel(
            name='Dispatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference_number', models.CharField(editable=False, max_length=30, unique=True)),
                ('dispatched_at', models.DateTimeField(auto_now_add=True)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[
                    ('in_transit', 'In Transit'), ('partially_received', 'Partially Received'),
                    ('received', 'Received / Completed'), ('cancelled', 'Cancelled')
                ], db_index=True, default='in_transit', max_length=25)),
                ('notes', models.TextField(blank=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dispatches', to='pos.business')),
                ('destination_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='dispatches_in', to='pos.branch')),
                ('dispatched_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='dispatches_sent', to=settings.AUTH_USER_MODEL)),
                ('received_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dispatches_received', to=settings.AUTH_USER_MODEL)),
                ('requisition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dispatches', to='pos.stockrequisition')),
                ('source_branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='dispatches_out', to='pos.branch')),
                ('transfer_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dispatches', to='pos.stocktransferrequest')),
            ],
            options={
                'ordering': ['-dispatched_at'],
            },
        ),
        migrations.AddIndex(
            model_name='dispatch',
            index=models.Index(fields=['business', '-dispatched_at'], name='pos_dispatch_bus_idx'),
        ),
        migrations.AddIndex(
            model_name='dispatch',
            index=models.Index(fields=['source_branch', 'status'], name='pos_dispatch_src_st_idx'),
        ),
        migrations.AddIndex(
            model_name='dispatch',
            index=models.Index(fields=['destination_branch', 'status'], name='pos_dispatch_dst_st_idx'),
        ),
        # DispatchItem model
        migrations.CreateModel(
            name='DispatchItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dispatched_quantity', models.DecimalField(decimal_places=3, max_digits=10)),
                ('unit_cost', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Moving avg unit cost at source branch at shipment time', max_digits=12)),
                ('received_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), max_digits=10)),
                ('discrepancy_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), max_digits=10)),
                ('discrepancy_reason', models.TextField(blank=True)),
                ('dispatch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='pos.dispatch')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='dispatch_items', to='pos.product')),
            ],
        ),
        # Run backfill
        migrations.RunPython(backfill_multi_branch_data, reverse_backfill),
    ]
