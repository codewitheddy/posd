# Production Deployment Checklist - Marid POS

## Pre-Deployment Setup

### 1. Mailjet Email Configuration ✓

Your production Mailjet account is configured:
- **Email**: info@marid.co.ke
- **API Key**: 46f06713bd67184eb3b783098226f0d9
- **Secret Key**: 0317e680de9ee8329fe1452ef11f35a6
- **SMTP Host**: in-v3.mailjet.com

**CRITICAL**: Before deployment, verify sender email in Mailjet:
1. Go to: https://app.mailjet.com/account/sender
2. Add and verify: info@marid.co.ke
3. Check email inbox for verification link
4. Click verification link
5. Wait for "Verified" status

### 2. Environment Configuration

The `.env.production` file has been created with production settings.

**Before deployment, update these values:**

```bash
# Generate new SECRET_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Update in .env.production:
SECRET_KEY=<generated_key>

# Set strong database password
DATABASE_PASSWORD=<strong_password>

# Update domain names
ALLOWED_HOSTS=marid.co.ke,www.marid.co.ke,pos.marid.co.ke
CSRF_TRUSTED_ORIGINS=https://marid.co.ke,https://www.marid.co.ke,https://pos.marid.co.ke
SITE_URL=https://pos.marid.co.ke
```

### 3. Database Setup

#### PostgreSQL (Recommended)

```bash
# On cPanel or server, create PostgreSQL database:
# Database name: marid_pos_db
# Username: marid_pos_user
# Password: <strong_password>

# Update .env.production with actual credentials
```

#### MySQL (Alternative)

```bash
# If PostgreSQL not available, use MySQL:
# Update .env.production:
DATABASE_ENGINE=mysql
DATABASE_PORT=3306
```

### 4. SSL Certificate

Ensure SSL/HTTPS is configured on your domain before enabling security settings in .env.production.

If SSL not ready yet, temporarily set:
```bash
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
```

## Deployment Steps

### Step 1: Upload Files to cPanel

```bash
# Upload entire posd/ directory to your cPanel hosting
# Recommended location: ~/public_html/pos/ or ~/pos/
```

### Step 2: Setup Python Environment

```bash
# SSH into your cPanel server
cd ~/pos  # or your installation directory

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment

```bash
# Copy production environment file
cp .env.production .env

# Edit .env and update:
# - SECRET_KEY (generate new one)
# - DATABASE_PASSWORD (your actual password)
# - ALLOWED_HOSTS (your actual domains)
# - SITE_URL (your actual domain)

# Verify configuration
cat .env
```

### Step 4: Database Migration

```bash
# Run migrations
python manage.py migrate

# Create superuser for admin access
python manage.py createsuperuser
```

### Step 5: Collect Static Files

```bash
# Collect static files
python manage.py collectstatic --noinput
```

### Step 6: Configure Web Server

#### For cPanel with Passenger (Python App)

1. Go to cPanel → Setup Python App
2. Create new application:
   - **Python version**: 3.11 or 3.13
   - **Application root**: /home/username/pos
   - **Application URL**: pos.marid.co.ke (or your subdomain)
   - **Application startup file**: passenger_wsgi.py
   - **Application Entry point**: application

3. Set environment variables in cPanel Python App:
   - Copy all variables from .env file
   - Add each as environment variable

4. Restart the application

### Step 7: Test Email Configuration

```bash
# SSH into server
cd ~/pos
source venv/bin/activate

# Test email
python manage.py check_email_config

# Should show:
# EMAIL_BACKEND: django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST: in-v3.mailjet.com
# DEFAULT_FROM_EMAIL: info@marid.co.ke
# ✓ Test email sent successfully!
```

### Step 8: Configure Registration Settings

```bash
# Configure registration control
python manage.py configure_registration \
  --enable-registration \
  --require-email-verification \
  --admin-emails "info@marid.co.ke" \
  --site-url "https://pos.marid.co.ke"

# Generate invitation codes (optional)
python manage.py generate_invitation_codes \
  --count 10 \
  --max-uses 1 \
  --description "Launch invitation codes"
```

### Step 9: Setup Default Data

```bash
# Setup default business settings
python manage.py setup_business_defaults

# Check system status
python manage.py check --deploy
```

### Step 10: Test Registration Flow

1. Go to: https://pos.marid.co.ke/register/
2. Register a test business
3. Check email inbox for verification link
4. Verify email
5. Check email for login credentials
6. Login and test system

## Post-Deployment

### Security Checklist

- [ ] SSL/HTTPS enabled and working
- [ ] DEBUG=False in .env
- [ ] Strong SECRET_KEY generated
- [ ] Strong database password set
- [ ] ALLOWED_HOSTS configured correctly
- [ ] CSRF_TRUSTED_ORIGINS configured
- [ ] Mailjet sender email verified
- [ ] Admin email notifications working
- [ ] Registration flow tested
- [ ] Login/logout working
- [ ] Password reset working

### Monitoring Setup

```bash
# Setup daily email summaries (optional)
# Add to crontab:
0 8 * * * cd ~/pos && source venv/bin/activate && python manage.py send_daily_summary

# Check license expiry (daily)
0 9 * * * cd ~/pos && source venv/bin/activate && python manage.py check_license_expiry

# Check low stock (daily)
0 10 * * * cd ~/pos && source venv/bin/activate && python manage.py check_low_stock
```

### Backup Setup

```bash
# Setup automated backups
# Add to crontab (daily at 2 AM):
0 2 * * * cd ~/pos && source venv/bin/activate && python manage.py backup_database

# Weekly full backup (Sunday at 3 AM):
0 3 * * 0 cd ~/pos && source venv/bin/activate && python manage.py backup_database --compress
```

## Troubleshooting

### Email Not Sending

1. Check Mailjet dashboard: https://app.mailjet.com/stats
2. Verify sender email status: https://app.mailjet.com/account/sender
3. Check Django logs for errors
4. Test SMTP connection: `python test_mailjet.py`

### Database Connection Issues

1. Verify database credentials in .env
2. Check database exists: `psql -U marid_pos_user -d marid_pos_db`
3. Check PostgreSQL service: `systemctl status postgresql`
4. Review database logs

### Static Files Not Loading

1. Run: `python manage.py collectstatic --noinput`
2. Check STATIC_ROOT in settings.py
3. Verify web server configuration
4. Check file permissions: `chmod -R 755 staticfiles/`

### Registration Rate Limits

If testing multiple registrations:
```bash
# Temporarily disable rate limits
python manage.py configure_registration --rate-limit-ip 100 --rate-limit-domain 100

# Re-enable after testing
python manage.py configure_registration --rate-limit-ip 3 --rate-limit-domain 10
```

## Support Commands

```bash
# List all registrations
python manage.py list_registrations

# Get user credentials
python manage.py get_user_credentials email@example.com

# Reset user password
python manage.py reset_user_password username

# List all users
python manage.py list_users

# Delete business (careful!)
python manage.py delete_business business_id
```

## Production URLs

- **Main Site**: https://pos.marid.co.ke/
- **Registration**: https://pos.marid.co.ke/register/
- **Login**: https://pos.marid.co.ke/login/
- **Admin Panel**: https://pos.marid.co.ke/admin/
- **Registration Admin**: https://pos.marid.co.ke/registration-admin/

## Important Notes

1. **Mailjet Sender Verification**: MUST be completed before any emails will send
2. **SECRET_KEY**: Generate a new one for production, never use the default
3. **Database Backups**: Setup automated backups immediately
4. **SSL Certificate**: Required for production security settings
5. **Rate Limits**: Adjust based on your expected registration volume
6. **Admin Notifications**: Configure admin emails to receive registration alerts

## Next Steps After Deployment

1. Test complete registration flow
2. Create your first business
3. Configure business settings
4. Add products and categories
5. Test POS functionality
6. Train staff on system usage
7. Monitor email delivery
8. Review activity logs
9. Setup regular backups
10. Plan marketing/launch strategy

## Emergency Contacts

- **Mailjet Support**: https://www.mailjet.com/support/
- **cPanel Support**: Contact your hosting provider
- **Database Issues**: Check hosting provider documentation

---

**Deployment Date**: _____________
**Deployed By**: _____________
**Production URL**: https://pos.marid.co.ke/
**Email**: info@marid.co.ke
