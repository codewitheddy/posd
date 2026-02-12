# POS System Deployment Guide

## Quick Start

### 1. Pre-Deployment Checklist

```bash
# Run all checks before deploying
python manage.py check --deploy
python manage.py test
python manage.py makemigrations --check
```

### 2. Environment Variables

Create `.env` file (never commit this!):

```bash
# Security
SECRET_KEY=your-secret-key-here-make-it-long-and-random
DEBUG=False

# Hosts
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/pos_db

# Email (for error notifications)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
ADMIN_EMAIL=admin@yourdomain.com

# Optional: Redis Cache
REDIS_URL=redis://localhost:6379/1

# Optional: CORS
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```

### 3. Generate Secret Key

```python
# Run in Python shell
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

### 4. Deploy

```bash
# Make deploy script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

---

## Detailed Deployment Steps

### Step 1: Server Setup

#### Install System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install python3.11 python3.11-venv python3-pip -y

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Install Nginx
sudo apt install nginx -y

# Install Redis (optional, for caching)
sudo apt install redis-server -y
```

#### Create Application User

```bash
# Create user
sudo useradd -m -s /bin/bash posuser

# Switch to user
sudo su - posuser
```

### Step 2: Application Setup

#### Clone Repository

```bash
cd /home/posuser
git clone https://github.com/yourusername/pos-system.git
cd pos-system/posd
```

#### Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

#### Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements_production.txt
```

### Step 3: Database Setup

#### Create PostgreSQL Database

```bash
# Switch to postgres user
sudo su - postgres

# Create database and user
psql
CREATE DATABASE pos_db;
CREATE USER pos_user WITH PASSWORD 'secure_password';
ALTER ROLE pos_user SET client_encoding TO 'utf8';
ALTER ROLE pos_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE pos_user SET timezone TO 'Africa/Nairobi';
GRANT ALL PRIVILEGES ON DATABASE pos_db TO pos_user;
\q

# Exit postgres user
exit
```

#### Run Migrations

```bash
# As posuser
cd /home/posuser/pos-system/posd
source venv/bin/activate
export DJANGO_SETTINGS_MODULE=pos_system.settings_production
python manage.py migrate
```

#### Create Superuser

```bash
python manage.py createsuperuser
```

### Step 4: Static Files

```bash
# Collect static files
python manage.py collectstatic --noinput
```

### Step 5: Gunicorn Setup

#### Create Gunicorn Configuration

```bash
# /home/posuser/pos-system/posd/gunicorn_config.py
```

```python
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = 'gevent'
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = '/home/posuser/pos-system/posd/logs/gunicorn_access.log'
errorlog = '/home/posuser/pos-system/posd/logs/gunicorn_error.log'
loglevel = 'info'

# Process naming
proc_name = 'pos_system'

# Server mechanics
daemon = False
pidfile = '/home/posuser/pos-system/posd/gunicorn.pid'
user = 'posuser'
group = 'posuser'
tmp_upload_dir = None

# SSL (if terminating SSL at Gunicorn)
# keyfile = '/path/to/key.pem'
# certfile = '/path/to/cert.pem'
```

#### Create Systemd Service

```bash
# /etc/systemd/system/pos.service
```

```ini
[Unit]
Description=POS System Gunicorn Daemon
After=network.target

[Service]
User=posuser
Group=posuser
WorkingDirectory=/home/posuser/pos-system/posd
Environment="PATH=/home/posuser/pos-system/posd/venv/bin"
Environment="DJANGO_SETTINGS_MODULE=pos_system.settings_production"
EnvironmentFile=/home/posuser/pos-system/posd/.env
ExecStart=/home/posuser/pos-system/posd/venv/bin/gunicorn \
    --config /home/posuser/pos-system/posd/gunicorn_config.py \
    pos_system.wsgi:application

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl start pos
sudo systemctl enable pos
sudo systemctl status pos
```

### Step 6: Nginx Setup

#### Create Nginx Configuration

```bash
# /etc/nginx/sites-available/pos
```

```nginx
upstream pos_app {
    server 127.0.0.1:8000 fail_timeout=0;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Logging
    access_log /var/log/nginx/pos_access.log;
    error_log /var/log/nginx/pos_error.log;
    
    # Max upload size
    client_max_body_size 10M;
    
    # Static files
    location /static/ {
        alias /home/posuser/pos-system/posd/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Media files
    location /media/ {
        alias /home/posuser/pos-system/posd/media/;
        expires 1y;
        add_header Cache-Control "public";
    }
    
    # Application
    location / {
        proxy_pass http://pos_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

#### Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/pos /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Step 7: SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal is set up automatically
# Test renewal
sudo certbot renew --dry-run
```

### Step 8: Firewall Setup

```bash
# Allow SSH, HTTP, HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

### Step 9: Automated Backups

#### Create Backup Script

```bash
# /home/posuser/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/home/posuser/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
pg_dump pos_db > "$BACKUP_DIR/db_$DATE.sql"

# Backup media files
tar -czf "$BACKUP_DIR/media_$DATE.tar.gz" /home/posuser/pos-system/posd/media/

# Keep only last 7 days
find $BACKUP_DIR -name "db_*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "media_*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

#### Setup Cron Job

```bash
chmod +x /home/posuser/backup.sh

# Add to crontab
crontab -e

# Add line (daily at 2 AM)
0 2 * * * /home/posuser/backup.sh >> /home/posuser/backup.log 2>&1
```

### Step 10: Monitoring Setup

#### Create Health Check Script

```bash
# /home/posuser/health_check.sh
```

```bash
#!/bin/bash
URL="https://yourdomain.com/health/"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $URL)

if [ $RESPONSE -ne 200 ]; then
    echo "Health check failed: HTTP $RESPONSE"
    # Send alert (email, SMS, etc.)
    echo "POS System health check failed" | mail -s "Alert: POS System Down" admin@yourdomain.com
fi
```

#### Setup Monitoring Cron

```bash
# Check every 5 minutes
*/5 * * * * /home/posuser/health_check.sh
```

---

## Post-Deployment

### 1. Verify Deployment

```bash
# Check application status
sudo systemctl status pos

# Check Nginx status
sudo systemctl status nginx

# Check logs
tail -f /home/posuser/pos-system/posd/logs/gunicorn_error.log
tail -f /var/log/nginx/pos_error.log
```

### 2. Test Critical Paths

- [ ] Login page loads
- [ ] Admin panel accessible
- [ ] POS screen loads
- [ ] Complete a test sale
- [ ] Generate reports
- [ ] Print receipt

### 3. Performance Testing

```bash
# Install Apache Bench
sudo apt install apache2-utils -y

# Test homepage
ab -n 1000 -c 10 https://yourdomain.com/

# Test POS screen (with authentication)
ab -n 100 -c 5 -C "sessionid=your-session-id" https://yourdomain.com/pos/
```

---

## Maintenance

### Daily Tasks
- Monitor error logs
- Check system health
- Verify backups

### Weekly Tasks
- Review performance metrics
- Check disk space
- Update security patches

### Monthly Tasks
- Full system backup
- Security audit
- Performance optimization

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
sudo journalctl -u pos -n 50

# Check Gunicorn
sudo systemctl status pos

# Test manually
cd /home/posuser/pos-system/posd
source venv/bin/activate
gunicorn --bind 127.0.0.1:8000 pos_system.wsgi:application
```

### Database Connection Issues

```bash
# Test database connection
psql -U pos_user -d pos_db -h localhost

# Check DATABASE_URL in .env
cat /home/posuser/pos-system/posd/.env | grep DATABASE_URL
```

### Static Files Not Loading

```bash
# Recollect static files
python manage.py collectstatic --clear --noinput

# Check Nginx configuration
sudo nginx -t

# Check file permissions
ls -la /home/posuser/pos-system/posd/staticfiles/
```

### High Memory Usage

```bash
# Check processes
ps aux | grep gunicorn

# Reduce workers in gunicorn_config.py
# Restart application
sudo systemctl restart pos
```

---

## Rollback Procedure

If deployment fails:

```bash
# 1. Stop application
sudo systemctl stop pos

# 2. Restore database backup
psql -U pos_user -d pos_db < /home/posuser/backups/db_YYYYMMDD_HHMMSS.sql

# 3. Checkout previous version
git checkout previous-tag

# 4. Reinstall dependencies
pip install -r requirements_production.txt

# 5. Run migrations (if needed)
python manage.py migrate

# 6. Restart application
sudo systemctl start pos
```

---

## Security Checklist

- [ ] SECRET_KEY is random and secure
- [ ] DEBUG=False in production
- [ ] ALLOWED_HOSTS configured
- [ ] HTTPS enabled with valid certificate
- [ ] Firewall configured
- [ ] Database password is strong
- [ ] Regular backups enabled
- [ ] Monitoring enabled
- [ ] Error notifications configured
- [ ] Rate limiting enabled
- [ ] Login attempt limiting enabled
- [ ] Security headers configured
- [ ] File upload validation enabled
- [ ] Dependencies up to date

---

## Support

For issues or questions:
1. Check logs first
2. Review troubleshooting section
3. Check GitHub issues
4. Contact support team

---

**Last Updated:** February 12, 2026
**Version:** 2.0
