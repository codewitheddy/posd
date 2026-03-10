# Generated migration for Kenyan Tax Compliance Integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0061_add_new_zreport_system'),
    ]

    operations = [
        # ===== PRODUCT FIELDS =====
        # HS Code for tax classification
        migrations.AddField(
            model_name='product',
            name='hs_code',
            field=models.CharField(
                blank=True,
                help_text='Harmonized System Code for tax classification (e.g., 0901.21)',
                max_length=20,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='hs_code_description',
            field=models.CharField(
                blank=True,
                help_text='Description of HS Code category',
                max_length=255,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='is_excisable',
            field=models.BooleanField(
                default=False,
                help_text='Whether this product is subject to excise duty'
            ),
        ),
        migrations.AddField(
            model_name='product',
            name='excise_rate',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Excise duty rate percentage',
                max_digits=5
            ),
        ),
        
        # ===== BUSINESS FIELDS =====
        # KRA Registration
        migrations.AddField(
            model_name='business',
            name='kra_pin',
            field=models.CharField(
                blank=True,
                help_text='KRA PIN Number (e.g., A001234567X)',
                max_length=20,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='business',
            name='cu_number',
            field=models.CharField(
                blank=True,
                help_text='Control Unit Number from KRA TIMS',
                max_length=20,
                null=True,
                unique=True
            ),
        ),
        migrations.AddField(
            model_name='business',
            name='cu_serial_number',
            field=models.CharField(
                blank=True,
                help_text='CU Device Serial Number',
                max_length=50,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='business',
            name='tims_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Whether TIMS integration is enabled'
            ),
        ),
        migrations.AddField(
            model_name='business',
            name='tims_last_sync',
            field=models.DateTimeField(
                blank=True,
                help_text='Last successful TIMS sync timestamp',
                null=True
            ),
        ),
        
        # ===== SALE FIELDS =====
        # TIMS Integration
        migrations.AddField(
            model_name='sale',
            name='tims_invoice_number',
            field=models.CharField(
                blank=True,
                help_text='TIMS-generated invoice number',
                max_length=50,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='tims_qr_code',
            field=models.TextField(
                blank=True,
                help_text='TIMS QR code data for receipt',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='tims_verification_url',
            field=models.URLField(
                blank=True,
                help_text='URL for customer to verify invoice on KRA portal',
                max_length=200,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='tims_synced',
            field=models.BooleanField(
                default=False,
                help_text='Whether this sale has been synced to TIMS'
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='tims_sync_date',
            field=models.DateTimeField(
                blank=True,
                help_text='When this sale was synced to TIMS',
                null=True
            ),
        ),
        
        # ===== INDEXES FOR PERFORMANCE =====
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['hs_code'], name='pos_product_hs_code_idx'),
        ),
        migrations.AddIndex(
            model_name='business',
            index=models.Index(fields=['cu_number'], name='pos_business_cu_number_idx'),
        ),
        migrations.AddIndex(
            model_name='sale',
            index=models.Index(fields=['tims_synced', 'created_at'], name='pos_sale_tims_sync_idx'),
        ),
    ]
