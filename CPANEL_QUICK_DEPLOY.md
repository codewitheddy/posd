# cPanel Quick Deployment Checklist

Fast deployment guide for experienced users.

## Pre-Deployment (Local)

```bash
# 1. Update requirements.txt
pip freeze > requirements.txt

# 2. Test locally
python manage.py check --deploy
python manage.py test

# 3. Commit and push
git add .
git commit -m "Prepare for cPanel deployment"
git push origin main
```

## cPanel Setup (5 minutes)

### 1. Create MySQL Database
- Database: `youruser_posdb`
- User: `youruser_posuser`
- Password: [strong password]
- Grant ALL PRIVILEGES

### 2. Setup Python App
- Python: 3.11+
- App root: `pos_app/posd`
- Startup file: `passenger_wsgi.py`
- Entry point: `application`

### 3. Upload Code (SSH)

```bash
ssh yourusername@yourdomain.com
cd ~/public_html/pos_app
git clone [your-repo-url] posd
cd posd
```

### 4. Configure Environment

```bash
# Copy and edit .env
cp .env.example .env
nano .env
```

Update these values:
```env
DATABASE_NAME=youruser_posdb
DATABASE_USER=youruser_posuser
DATABASE_PASSWORD=[your-db-password]
SECRET_KEY=[generate-new-key]
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
EMAIL_HOST_USER=[mailjet-api-key]
EMAIL_HOST_PASSWORD=[mailjet-secret]
DEFAULT_FROM_EMAIL=noreply@yourdomain.com
SITE_URL=https://yourdomain.com
```

Generate SECRET_KEY:
```bash
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Update passenger_wsgi.py

```bash
nano passenger_wsgi.py
```

Replace `yourusername` with your actual cPanel username.

### 6. Deploy

```bash
chmod +x deploy_cpanel.sh
./deploy_cpanel.sh
```

### 7. Create Superuser

```bash
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate
python manage.py createsuperuser
```

### 8. Configure Registration

```bash
python manage.py configure_registration \
  --enable-registration \
  --require-email-verification \
  --admin-emails "youremail@domain.com"
```

### 9. Setup SSL

- cPanel → SSL/TLS Status → Run AutoSSL

### 10. Test

- Visit: https://yourdomain.com
- Test registration
- Test login
- Check admin panel

## Quick Commands

```bash
# Activate venv
source ~/virtualenv/public_html/pos_app/posd/3.11/bin/activate

# Restart app
touch ~/public_html/pos_app/posd/tmp/restart.txt

# View logs
tail -f ~/logs/yourdomain.com.error.log

# Update app
cd ~/public_html/pos_app/posd
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
touch tmp/restart.txt
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 500 Error | Check `~/logs/yourdomain.com.error.log` |
| Static files not loading | Run `collectstatic` and check permissions |
| Database error | Verify `.env` database credentials |
| Email not sending | Verify Mailjet credentials and sender email |
| App not restarting | `touch tmp/restart.txt` |

## Done!

Your Django POS system is now live at https://yourdomain.com

Next steps:
1. Configure business settings
2. Add products and categories
3. Setup payment methods
4. Train staff on system usage
