# Generated migration for registration control system

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0063_remove_business_pos_business_cu_number_idx_and_more'),
    ]

    operations = [
        # InvitationCode model
        migrations.CreateModel(
            name='InvitationCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, max_length=20, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('max_uses', models.IntegerField(default=1, help_text='Maximum number of times this code can be used')),
                ('uses_count', models.IntegerField(default=0, help_text='Number of times this code has been used')),
                ('valid_from', models.DateTimeField(default=timezone.now)),
                ('valid_until', models.DateTimeField(blank=True, help_text='Leave blank for no expiry', null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('allowed_email_domains', models.TextField(blank=True, help_text='Comma-separated list of allowed email domains')),
                ('notes', models.TextField(blank=True, help_text='Internal notes about this code')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invitation_codes_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        # BusinessRegistration model
        migrations.CreateModel(
            name='BusinessRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(db_index=True, max_length=254, unique=True)),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=20)),
                ('business_name', models.CharField(max_length=200)),
                ('business_type', models.CharField(blank=True, max_length=100)),
                ('kra_pin', models.CharField(blank=True, max_length=20)),
                ('status', models.CharField(choices=[('pending', 'Pending Verification'), ('email_verified', 'Email Verified'), ('pending_approval', 'Pending Admin Approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('completed', 'Completed')], db_index=True, default='pending', max_length=20)),
                ('email_verification_token', models.CharField(blank=True, max_length=100, null=True, unique=True)),
                ('email_verified_at', models.DateTimeField(blank=True, null=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='registration', to='pos.business')),
                ('invitation_code', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='pos.invitationcode')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='registrations_reviewed', to=settings.AUTH_USER_MODEL)),
                ('user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='registration', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        # RegistrationSettings model
        migrations.CreateModel(
            name='RegistrationSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('require_invitation_code', models.BooleanField(default=False, help_text='Require invitation code for registration')),
                ('require_email_verification', models.BooleanField(default=True, help_text='Require email verification before activation')),
                ('require_admin_approval', models.BooleanField(default=False, help_text='Require admin approval for new registrations')),
                ('max_registrations_per_ip_per_day', models.IntegerField(default=3, help_text='Maximum registrations from same IP per day')),
                ('max_registrations_per_email_domain_per_day', models.IntegerField(default=10, help_text='Maximum registrations from same email domain per day')),
                ('blocked_email_domains', models.TextField(blank=True, help_text='Comma-separated list of blocked email domains')),
                ('allowed_email_domains', models.TextField(blank=True, help_text='If set, only these domains are allowed')),
                ('require_kra_pin', models.BooleanField(default=False, help_text='Require KRA PIN for registration')),
                ('require_phone_verification', models.BooleanField(default=False, help_text='Require phone number verification (SMS)')),
                ('notify_admin_on_registration', models.BooleanField(default=True, help_text='Send email to admins on new registration')),
                ('admin_notification_emails', models.TextField(blank=True, help_text='Comma-separated list of admin emails')),
                ('registration_closed_message', models.TextField(blank=True, default='Registration is currently closed. Please contact support for access.')),
                ('registration_enabled', models.BooleanField(default=True, help_text='Enable/disable all registrations')),
            ],
            options={
                'verbose_name': 'Registration Settings',
                'verbose_name_plural': 'Registration Settings',
            },
        ),
        
        # Indexes
        migrations.AddIndex(
            model_name='invitationcode',
            index=models.Index(fields=['code', 'is_active'], name='pos_invitat_code_act_idx'),
        ),
        migrations.AddIndex(
            model_name='invitationcode',
            index=models.Index(fields=['valid_until'], name='pos_invitat_valid_idx'),
        ),
        migrations.AddIndex(
            model_name='businessregistration',
            index=models.Index(fields=['status', 'created_at'], name='pos_busreg_status_idx'),
        ),
        migrations.AddIndex(
            model_name='businessregistration',
            index=models.Index(fields=['email'], name='pos_busreg_email_idx'),
        ),
    ]
