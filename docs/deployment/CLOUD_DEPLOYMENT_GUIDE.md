# Cloud Deployment Guide - Offline-First POS System

## Overview

Your POS system now supports a hybrid online-offline architecture with automatic data synchronization. This guide covers deploying to cloud providers and configuring the offline-first features.

## Architecture

```
┌─────────────────┐         ┌──────────────────┐
│  Cloud Server   │◄────────┤  Local Browser   │
│  (Django API)   │         │  (IndexedDB)     │
│  PostgreSQL     │────────►│  Service Worker  │
└─────────────────┘         └──────────────────┘
        │                            │
        │                            │
    Internet                    Offline Mode
    Connection                  Auto-Sync
```

## Features

✓ **Offline-First**: Works without internet connection
✓ **Auto-Sync**: Syncs data when connection restored
✓ **Real-Time**: Instant local operations
✓ **Multi-Location**: Support multiple stores
✓ **Conflict Resolution**: Smart data merging
✓ **Background Sync**: Syncs even when tab closed

## Prerequisites

- Python 3.8+
- PostgreSQL 12+ (for production)
- Cloud provider account (AWS/Azure/GCP/DigitalOcean/Heroku)
- Domain name (optional but recommended)
- SSL certificate (required for Service Workers)

## Installation Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

New packages added:
- `djangorestframework` - REST API framework
- `djangorestframework-simplejwt` - JWT authentication
- `django-cors-headers` - CORS support
- `drf-spectacular` - API documentation

### 2. Update Database for Production

Edit `pos_system/settings.py`:

```python
# For PostgreSQL (recommended for production)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'pos_db',
        'USER': 'pos_user',
        'PASSWORD': 'your_secure_password',
        'HOST': 'localhost',  # or your cloud database host
        'PORT': '5432',
    }
}
```

Or use environment variables:

```python
import os

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'pos_db'),
        'USER': os.getenv('DB_USER', 'pos_user'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}
```

### 3. Configure Production Settings

```python
# Security settings
DEBUG = False
SECRET_KEY = os.getenv('SECRET_KEY')  # Use environment variable
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

# CORS settings (update with your domain)
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
    "https://www.yourdomain.com",
]
CORS_ALLOW_ALL_ORIGINS = False  # Set to False in production

# HTTPS settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
```

### 4. Run Migrations

```bash
python manage.py migrate
```

### 5. Create Superuser

```bash
python manage.py createsuperuser
```

### 6. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

## Cloud Provider Deployment

### Option 1: Heroku (Easiest)

1. **Install Heroku CLI**
   ```bash
   # Download from https://devcenter.heroku.com/articles/heroku-cli
   ```

2. **Create Heroku App**
   ```bash
   heroku create your-pos-app
   heroku addons:create heroku-postgresql:hobby-dev
   ```

3. **Set Environment Variables**
   ```bash
   heroku config:set SECRET_KEY="your-secret-key"
   heroku config:set DEBUG=False
   ```

4. **Create Procfile**
   ```
   web: gunicorn pos_system.wsgi --log-file -
   ```

5. **Deploy**
   ```bash
   git push heroku main
   heroku run python manage.py migrate
   heroku run python manage.py createsuperuser
   ```

### Option 2: DigitalOcean App Platform

1. **Create App** via DigitalOcean dashboard
2. **Connect GitHub** repository
3. **Add PostgreSQL** database
4. **Set Environment Variables** in dashboard
5. **Deploy** automatically on push

### Option 3: AWS Elastic Beanstalk

1. **Install EB CLI**
   ```bash
   pip install awsebcli
   ```

2. **Initialize**
   ```bash
   eb init -p python-3.9 pos-system
   ```

3. **Create Environment**
   ```bash
   eb create pos-production
   ```

4. **Deploy**
   ```bash
   eb deploy
   ```

### Option 4: Azure App Service

1. **Install Azure CLI**
2. **Create Resource Group**
   ```bash
   az group create --name pos-rg --location eastus
   ```

3. **Create App Service**
   ```bash
   az webapp up --name your-pos-app --resource-group pos-rg
   ```

### Option 5: Google Cloud Run

1. **Create Dockerfile**
2. **Build Container**
   ```bash
   gcloud builds submit --tag gcr.io/PROJECT-ID/pos-system
   ```

3. **Deploy**
   ```bash
   gcloud run deploy --image gcr.io/PROJECT-ID/pos-system
   ```

## API Endpoints

### Authentication
- `POST /api/v1/auth/token/` - Get JWT token
- `POST /api/v1/auth/token/refresh/` - Refresh token

### Resources
- `GET /api/v1/products/` - List products
- `GET /api/v1/categories/` - List categories
- `GET /api/v1/customers/` - List customers
- `GET /api/v1/sales/` - List sales
- `GET /api/v1/purchases/` - List purchases

### Sync
- `POST /api/v1/sync/pull/` - Pull server updates
- `POST /api/v1/sync/push/` - Push local changes
- `GET /api/v1/sync/status/` - Check sync status

### Documentation
- `GET /api/v1/docs/` - Interactive API documentation
- `GET /api/v1/schema/` - OpenAPI schema

## Testing the API

### Get Authentication Token

```bash
curl -X POST https://yourdomain.com/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your_password"}'
```

Response:
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### List Products

```bash
curl -X GET https://yourdomain.com/api/v1/products/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Sync Data

```bash
curl -X POST https://yourdomain.com/api/v1/sync/pull/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "device-123",
    "last_sync": "2026-02-10T10:00:00Z"
  }'
```

## Offline Mode Setup

### 1. Register Service Worker

Add to your base template:

```html
<script>
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/pos/js/service-worker.js')
        .then(reg => console.log('Service Worker registered'))
        .catch(err => console.error('Service Worker registration failed:', err));
}
</script>
```

### 2. Initialize Offline DB

```javascript
// Initialize on page load
await offlineDB.init();
await syncManager.init();
```

### 3. Handle Offline Sales

```javascript
// Process sale offline
const sale = {
    customer_id: 123,
    items: [...],
    total: 100.00,
    created_at: new Date().toISOString()
};

await offlineDB.queueSale(sale);

// Will auto-sync when online
```

## Monitoring & Maintenance

### Check Sync Status

```javascript
const stats = await syncManager.getSyncStats();
console.log('Unsynced sales:', stats.unsyncedSales);
console.log('Last sync:', stats.lastSync);
```

### Manual Sync

```javascript
await syncManager.syncNow();
```

### View Logs

```bash
# Heroku
heroku logs --tail

# DigitalOcean
doctl apps logs YOUR_APP_ID

# AWS
eb logs
```

## Security Best Practices

1. **Use HTTPS** - Required for Service Workers
2. **Strong SECRET_KEY** - Generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"`
3. **Environment Variables** - Never commit secrets
4. **Database Backups** - Enable automatic backups
5. **Rate Limiting** - Implement API rate limits
6. **Token Expiry** - Configure appropriate JWT lifetimes
7. **CORS** - Restrict to your domain only

## Troubleshooting

### Service Worker Not Registering
- Ensure HTTPS is enabled
- Check browser console for errors
- Verify service-worker.js path

### Sync Failing
- Check authentication token
- Verify API endpoints are accessible
- Check CORS configuration
- Review server logs

### Database Connection Issues
- Verify database credentials
- Check firewall rules
- Ensure database is running
- Test connection manually

## Performance Optimization

1. **Enable Caching**
   ```python
   CACHES = {
       'default': {
           'BACKEND': 'django.core.cache.backends.redis.RedisCache',
           'LOCATION': 'redis://127.0.0.1:6379/1',
       }
   }
   ```

2. **Use CDN** for static files
3. **Enable Gzip** compression
4. **Database Indexing** - Add indexes to frequently queried fields
5. **Connection Pooling** - Configure database connection pooling

## Scaling

### Horizontal Scaling
- Use load balancer
- Multiple app instances
- Shared database
- Redis for session storage

### Vertical Scaling
- Increase server resources
- Optimize database queries
- Use database read replicas

## Cost Estimation

### Heroku
- Hobby: $7/month (1 dyno + PostgreSQL)
- Production: $50/month (2 dynos + PostgreSQL)

### DigitalOcean
- Basic: $12/month (App + Database)
- Professional: $36/month (Scaled resources)

### AWS
- Free Tier: First year free
- Production: $30-100/month (varies)

## Next Steps

1. Deploy to staging environment
2. Test offline functionality
3. Configure monitoring (Sentry, New Relic)
4. Set up CI/CD pipeline
5. Train staff on offline mode
6. Plan backup strategy
7. Configure alerts

## Support

For issues or questions:
- Check API documentation: `/api/v1/docs/`
- Review server logs
- Test with Postman/Insomnia
- Check browser console for client errors

## Conclusion

Your POS system is now cloud-ready with offline-first capabilities. Users can work seamlessly whether online or offline, with automatic synchronization ensuring data consistency across all locations.
