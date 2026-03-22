# cPanel Deployment Guide - Django POS System

Complete guide for deploying your Django POS system to cPanel hosting.

## Prerequisites

- cPanel hosting with Python support (3.11 or higher)
- MySQL database access
- SSH access (recommended)
- Domain name configured

## Step 1: Prepare Your cPanel Account

### 1.1 Create MySQL Database

1. Login to cPanel
2. Go to **MySQL® Databases**
3. Create a new database: `youruser_posdb`
4. Create a database user: `youruser_posuser`
5. Set a strong password
6. Add user to database with ALL PRIVILEGES
7. Note down: database name, username, password

### 1.2 Setup Python Application

1. Go to **Setup Python App** in cPanel
2. Click **Create Application**
3. Configure:
   - Python version: 3.11 (or latest available)
   - Application root: `pos_app/posd`
   - Application URL: `/` (or your preferred path)
   - Application startup file: `passenger_wsgi.py`
   - Application Entry point: `application`
4. Click **Create**
5. Note the virtual environment path shown

## Step 2: Upload Your Code

### Option A: Using Git (Recommended)

```bash
# SSH into your cPanel account
ssh yourusername@yourdomain.com

# Navigate to application directory
cd ~/public_html/pos_app

# Clone your repository
git clone https://github.com/yourusername/your-pos-repo.git posd

# Or if already cloned, pull latest changes
cd posd
git pull origin main
```

### Option B: Using File Manager

1. Compress your `posd` folder locally (zip)
2. Upload via cPanel File Manager to `public_html/pos_app/`
3. Extract the archive
4. Delete the zip file

## Step 3: Configure Environment Variables

### 3.1 Create .env File

```bash
# SSH into your account
cd ~/public_html/pos_app/posd

# Copy example file
cp .env.example .env

# Edit with nano or vi
nano .env
```

### 3.2 Update .env File

```env
# Database Configuration
DATABASE_NAME=youruser_posdb
DATABASE_USER=youruser_posuser
DATABASE_PASSWORD=your_actual_password
DATABASE_HOST=localhost
DATABASE_PORT=3306

# Django Settings
SECRET_KEY=generate-new-secret-key-here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Email Configuration (Mailjet)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=in-v3.mailjet.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_mailjet_api_key
EMAIL_HOST_PASSWORD=your_mailjet_secret_key
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Site URL
SITE_URL=https://yourdomain.com

# Security (if using HTTPS)
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
```

### 3.3 Generate SECRET_KEY

```bash
# In SSH terminal
cd ~/public_html/pos_app/posd
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copy the output and paste it as your SECRET_KEY in .env

## Step 4: Update passenger_wsgi.py

```bash
nano ~/public_html/pos_app/posd/passenger_wsgi.py
```

Replace `yourusername` with your actual cPanel username:

```python
CPANEL_USERNAME = 'your_actual_cpanel_username'
```

Update Python version if different from 3.11:

```python
INTERP = f"/home/{CPANEL_USERNAME}/virtualenv/public_html/pos_app/posd/3.11/bin/python3"
```

## Step 5: Run Deployment Script

```bash
cd ~/public_html/pos_app/posd
chmod +x deploy_cpanel.sh
./deploy_cpanel.sh
```

The script will:
- Activate virtual environment
- Install dependencies
- Collect static files
- Run database migrations
- Setup default data
- Restart the application

## Step 6: Create Superuser

```bash
cd ~/public_html/pos_app/posd
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
python manage.py createsuperuser
```

Follow the prompts to create your admin account.

## Step 7: Configure Registration Settings

```bash
# Configure registration control
python manage.py configure_registration \
  --enable-registration \
  --require-email-verification \
  --admin-emails "youremail@domain.com"

# Generate invitation codes (optional)
python manage.py generate_invitation_codes --count 10
```

## Step 8: Setup SSL Certificate

### Using Let's Encrypt (Free)

1. Go to cPanel **SSL/TLS Status**
2. Find your domain
3. Click **Run AutoSSL**
4. Wait for certificate installation

### Or use cPanel SSL Manager

1. Go to **SSL/TLS**
2. Click **Manage SSL Sites**
3. Select your domain
4. Install certificate

## Step 9: Configure .htaccess (If Needed)

If your app is not at root, create/edit `.htaccess`:

```apache
# ~/public_html/.htaccess
RewriteEngine On
RewriteBase /
RewriteRule ^pos_app/posd/(.*)$ pos_app/posd/$1 [L]
```

## Step 10: Test Your Deployment

1. Visit: `https://yourdomain.com`
2. Test registration: `https://yourdomain.com/register/`
3. Test login: `https://yourdomain.com/login/`
4. Access admin: `https://yourdomain.com/admin/`

## Troubleshooting

### Application Not Loading

1. Check error logs:
```bash
tail -f ~/logs/yourdomain.com.error.log
```

2. Restart application:
```bash
touch ~/public_html/pos_app/posd/tmp/restart.txt
```

### Database Connection Errors

1. Verify database credentials in `.env`
2. Check database exists in cPanel MySQL Databases
3. Verify user has privileges

### Static Files Not Loading

1. Collect static files again:
```bash
cd ~/public_html/pos_app/posd
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
python manage.py collectstatic --noinput
```

2. Check file permissions:
```bash
chmod -R 755 ~/public_html/pos_app/posd/staticfiles
```

### Email Not Sending

1. Verify Mailjet credentials in `.env`
2. Check sender email is verified in Mailjet
3. Test email:
```bash
python manage.py send_test_email youremail@domain.com
```

### Permission Errors

```bash
# Fix permissions
cd ~/public_html/pos_app
chmod -R 755 posd
chmod 600 posd/.env
```

## Maintenance Commands

### Update Application

```bash
cd ~/public_html/pos_app/posd
git pull origin main
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
touch tmp/restart.txt
```

### Backup Database

```bash
cd ~/public_html/pos_app/posd
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
python manage.py backup_database
```

### View Logs

```bash
# Application logs
tail -f ~/logs/yourdomain.com.error.log

# Access logs
tail -f ~/logs/yourdomain.com.access.log
```

### Django Shell

```bash
cd ~/public_html/pos_app/posd
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
python manage.py shell
```

## Performance Optimization

### Enable Redis Caching (If Available)

1. Check if Redis is available in cPanel
2. Update `.env`:
```env
REDIS_URL=redis://localhost:6379/0
```

3. Install redis package:
```bash
pip install django-redis redis
```

### Database Optimization

```bash
# Create indexes
python manage.py migrate

# Analyze database
python manage.py dbshell
ANALYZE TABLE pos_sale, pos_product, pos_purchase;
```

## Security Checklist

- [ ] DEBUG=False in .env
- [ ] Strong SECRET_KEY generated
- [ ] SSL certificate installed
- [ ] SECURE_SSL_REDIRECT=True
- [ ] Database password is strong
- [ ] .env file permissions set to 600
- [ ] Firewall rules configured
- [ ] Regular backups scheduled
- [ ] Mailjet sender email verified
- [ ] Registration rate limits configured

## Support

For issues specific to:
- **cPanel**: Contact your hosting provider
- **Django POS**: Check application logs
- **Email**: Verify Mailjet configuration
- **Database**: Check MySQL error logs

## Quick Reference

```bash
# Activate virtual environment
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate

# Restart application
touch ~/public_html/pos_app/posd/tmp/restart.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
python manage.py createsuperuser

# View logs
tail -f ~/logs/yourdomain.com.error.log
```

---

**Deployment complete! Your Django POS system is now live on cPanel.**
