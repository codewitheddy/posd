# Production Deployment Guide

## Pre-Deployment Checklist

### 1. Security Settings

Edit `pos_system/settings.py`:

```python
# CRITICAL: Set to False in production
DEBUG = False

# Generate a new secret key (use Django's get_random_secret_key())
SECRET_KEY = 'your-new-secret-key-here'

# Add your domain
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
```

### 2. Database Configuration (PostgreSQL)

Install PostgreSQL and update settings:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pos_db',
        'USER': 'pos_user',
        'PASSWORD': 'strong_password_here',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

Install PostgreSQL adapter:
```bash
pip install psycopg2-binary
```

### 3. Static Files

```python
# settings.py
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATIC_URL = '/static/'
```

Collect static files:
```bash
python manage.py collectstatic
```

### 4. Environment Variables

Use environment variables for sensitive data:

```bash
# .env file (never commit this!)
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:password@localhost/dbname
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

Install python-decouple:
```bash
pip install python-decouple
```

Update settings.py:
```python
from decouple import config

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')
```

## Deployment Options

### Option 1: Heroku (Easiest)

1. **Install Heroku CLI**
   ```bash
   # Download from https://devcenter.heroku.com/articles/heroku-cli
   ```

2. **Create Procfile**
   ```
   web: gunicorn pos_system.wsgi
   ```

3. **Install Gunicorn**
   ```bash
   pip install gunicorn
   pip freeze > requirements.txt
   ```

4. **Deploy**
   ```bash
   heroku login
   heroku create your-pos-app
   heroku addons:create heroku-postgresql:mini
   git push heroku main
   heroku run python manage.py migrate
   heroku run python manage.py createsuperuser
   heroku run python manage.py seed_data
   ```

### Option 2: DigitalOcean (VPS)

1. **Create Droplet** (Ubuntu 22.04)

2. **SSH into server**
   ```bash
   ssh root@your-server-ip
   ```

3. **Install dependencies**
   ```bash
   apt update
   apt install python3-pip python3-venv postgresql nginx
   ```

4. **Setup PostgreSQL**
   ```bash
   sudo -u postgres psql
   CREATE DATABASE pos_db;
   CREATE USER pos_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE pos_db TO pos_user;
   \q
   ```

5. **Clone and setup project**
   ```bash
   cd /var/www
   git clone your-repo-url pos
   cd pos
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install gunicorn
   ```

6. **Configure environment**
   ```bash
   nano .env
   # Add your production settings
   ```

7. **Run migrations**
   ```bash
   python manage.py migrate
   python manage.py collectstatic
   python manage.py createsuperuser
   ```

8. **Setup Gunicorn service**
   ```bash
   nano /etc/systemd/system/pos.service
   ```

   ```ini
   [Unit]
   Description=POS System
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/pos
   Environment="PATH=/var/www/pos/venv/bin"
   ExecStart=/var/www/pos/venv/bin/gunicorn --workers 3 --bind unix:/var/www/pos/pos.sock pos_system.wsgi:application

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   systemctl start pos
   systemctl enable pos
   ```

9. **Configure Nginx**
   ```bash
   nano /etc/nginx/sites-available/pos
   ```

   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;

       location = /favicon.ico { access_log off; log_not_found off; }
       
       location /static/ {
           root /var/www/pos;
       }

       location / {
           include proxy_params;
           proxy_pass http://unix:/var/www/pos/pos.sock;
       }
   }
   ```

   ```bash
   ln -s /etc/nginx/sites-available/pos /etc/nginx/sites-enabled
   nginx -t
   systemctl restart nginx
   ```

10. **Setup SSL (Let's Encrypt)**
    ```bash
    apt install certbot python3-certbot-nginx
    certbot --nginx -d yourdomain.com
    ```

### Option 3: PythonAnywhere

1. **Create account** at pythonanywhere.com

2. **Upload code** via Git or file upload

3. **Setup virtual environment**
   ```bash
   mkvirtualenv --python=/usr/bin/python3.10 pos-env
   pip install -r requirements.txt
   ```

4. **Configure web app** in PythonAnywhere dashboard
   - Source code: /home/yourusername/pos
   - Working directory: /home/yourusername/pos
   - WSGI file: Edit to point to pos_system.wsgi

5. **Setup database** (PostgreSQL or MySQL)

6. **Run migrations** in Bash console
   ```bash
   python manage.py migrate
   python manage.py collectstatic
   python manage.py createsuperuser
   ```

## Post-Deployment

### 1. Test Everything
- [ ] Can access the site
- [ ] Admin panel works
- [ ] Can create products
- [ ] Can make sales
- [ ] Invoices generate correctly
- [ ] Reports display properly

### 2. Setup Backups

**Database backup script:**
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump pos_db > /backups/pos_db_$DATE.sql
# Keep only last 7 days
find /backups -name "pos_db_*.sql" -mtime +7 -delete
```

**Cron job:**
```bash
crontab -e
# Add: Daily backup at 2 AM
0 2 * * * /path/to/backup.sh
```

### 3. Monitoring

Install monitoring tools:
- **Sentry**: Error tracking
- **New Relic**: Performance monitoring
- **UptimeRobot**: Uptime monitoring

### 4. Regular Maintenance

```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Restart service
systemctl restart pos
```

## Troubleshooting

### Static files not loading
```bash
python manage.py collectstatic --clear
```

### Database connection errors
Check PostgreSQL is running:
```bash
systemctl status postgresql
```

### Permission errors
```bash
chown -R www-data:www-data /var/www/pos
chmod -R 755 /var/www/pos
```

### Gunicorn not starting
Check logs:
```bash
journalctl -u pos -n 50
```

## Performance Optimization

### 1. Enable caching
```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

### 2. Database optimization
```python
# Use connection pooling
DATABASES['default']['CONN_MAX_AGE'] = 600
```

### 3. Gunicorn workers
```bash
# Formula: (2 x CPU cores) + 1
gunicorn --workers 5 --bind 0.0.0.0:8000 pos_system.wsgi
```

## Security Best Practices

1. **Regular updates**: Keep Django and dependencies updated
2. **Strong passwords**: Enforce strong password policy
3. **HTTPS only**: Always use SSL/TLS
4. **Firewall**: Configure UFW or iptables
5. **Fail2ban**: Protect against brute force attacks
6. **Regular backups**: Automate database backups
7. **Monitoring**: Set up alerts for errors and downtime

## Support

For deployment issues:
1. Check Django logs
2. Check web server logs (Nginx/Apache)
3. Check application logs (Gunicorn)
4. Review Django documentation: https://docs.djangoproject.com/

---

**Good luck with your deployment! 🚀**
