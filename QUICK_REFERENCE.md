# POS System Quick Reference

## 🚀 Quick Commands

### Development
```bash
# Start development server
python manage.py runserver

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic
```

### Production
```bash
# Deploy
./deploy.sh

# Check status
sudo systemctl status pos

# View logs
tail -f logs/django_error.log

# Restart application
sudo systemctl restart pos
```

### Database
```bash
# Backup
python manage.py backup_database

# Shell
python manage.py shell

# SQL shell
python manage.py dbshell
```

---

## 📁 Important Files

| File | Purpose |
|------|---------|
| `settings.py` | Development settings |
| `settings_production.py` | Production settings |
| `requirements.txt` | Development dependencies |
| `requirements_production.txt` | Production dependencies |
| `deploy.sh` | Deployment script |
| `.env` | Environment variables (never commit!) |

---

## 🔐 Environment Variables

```bash
# Required
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=postgresql://...

# Optional
DEBUG=False
REDIS_URL=redis://localhost:6379/1
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-password
ADMIN_EMAIL=admin@yourdomain.com
```

---

## 🛠️ Troubleshooting

### Application Won't Start
```bash
# Check logs
sudo journalctl -u pos -n 50

# Test manually
gunicorn pos_system.wsgi:application
```

### Database Issues
```bash
# Test connection
psql -U pos_user -d pos_db

# Reset migrations (DANGER!)
python manage.py migrate --fake pos zero
python manage.py migrate pos
```

### Static Files Not Loading
```bash
# Recollect
python manage.py collectstatic --clear

# Check permissions
ls -la staticfiles/
```

---

## 📊 Monitoring

### Health Check
```bash
curl https://yourdomain.com/health/
```

### System Status
```bash
# Application
sudo systemctl status pos

# Nginx
sudo systemctl status nginx

# PostgreSQL
sudo systemctl status postgresql

# Redis
sudo systemctl status redis
```

### Logs
```bash
# Application errors
tail -f logs/django_error.log

# Application info
tail -f logs/django_info.log

# Gunicorn
tail -f logs/gunicorn_error.log

# Nginx
tail -f /var/log/nginx/pos_error.log
```

---

## 🔄 Common Tasks

### Update Code
```bash
git pull origin main
pip install -r requirements_production.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart pos
```

### Backup Database
```bash
pg_dump pos_db > backup_$(date +%Y%m%d).sql
```

### Restore Database
```bash
psql pos_db < backup_20260212.sql
```

### Clear Cache
```bash
python manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()
```

---

## 🔒 Security Checklist

- [ ] SECRET_KEY is random
- [ ] DEBUG=False
- [ ] HTTPS enabled
- [ ] Firewall configured
- [ ] Strong passwords
- [ ] Regular backups
- [ ] Monitoring active
- [ ] Dependencies updated

---

## 📞 Support

### Documentation
- OPTIMIZATION_GUIDE.md
- DEPLOYMENT_GUIDE.md
- Django Docs: https://docs.djangoproject.com/

### Emergency Contacts
- System Admin: admin@yourdomain.com
- Support Team: support@yourdomain.com
- On-Call: +254-XXX-XXXXXX

---

## 🎯 Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| Page Load | < 1s | ✓ |
| API Response | < 200ms | ✓ |
| Uptime | 99.9% | ✓ |
| Error Rate | < 0.1% | ✓ |

---

## 📅 Maintenance Schedule

| Task | Frequency | Last Done |
|------|-----------|-----------|
| Check Logs | Daily | - |
| Security Updates | Weekly | - |
| Full Backup | Monthly | - |
| Security Audit | Quarterly | - |

---

**Last Updated:** February 12, 2026
**Version:** 2.0
