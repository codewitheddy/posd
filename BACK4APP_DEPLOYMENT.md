# Deploy to Back4App - Complete Guide

Back4App is a great choice for Django apps! It uses Docker containers and provides PostgreSQL database.

## Prerequisites

- Back4App account (free tier available at https://www.back4app.com)
- GitHub account
- Your code pushed to GitHub

**Important: Python Version**
- Default Dockerfile uses **Python 3.12** (required for Django 6.0)
- If you prefer Python 3.11, use `Dockerfile.py311` and `requirements-py311.txt` (Django 5.1)

## Quick Deployment Steps

### Step 1: Prepare Your Repository

Make sure these files exist (already created):
- ✅ `Dockerfile`
- ✅ `.dockerignore`
- ✅ `requirements.txt`

### Step 2: Push to GitHub

```bash
# Initialize git if not already done
git init

# Add all files
git add .

# Commit
git commit -m "Ready for Back4App deployment"

# Add your GitHub repository
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git

# Push to GitHub
git push -u origin main
```

### Step 3: Create Back4App App

1. Go to https://www.back4app.com/dashboard
2. Click **"Build new app"**
3. Select **"Container as a Service"**
4. Choose **"GitHub"** as source
5. Connect your GitHub account
6. Select your repository
7. Select branch (usually `main`)

### Step 4: Configure Build Settings

Back4App will detect your Dockerfile automatically.

**Build Configuration:**
- **Dockerfile Path**: `./Dockerfile` (default)
- **Port**: `8000` (or use environment variable `$PORT`)
- **Region**: Choose closest to your users

### Step 5: Add Environment Variables

In Back4App dashboard, go to **"Environment Variables"** and add:

| Variable | Value | Notes |
|----------|-------|-------|
| `SECRET_KEY` | Generate random string | Use Django secret key generator |
| `DEBUG` | `False` | Production mode |
| `DATABASE_URL` | From Back4App PostgreSQL | See Step 6 |
| `ALLOWED_HOSTS` | `your-app.back4app.io` | Your Back4App domain |
| `PORT` | `8000` | Application port |

### Step 6: Add PostgreSQL Database

1. In your app dashboard, click **"Database"**
2. Click **"Add Database"**
3. Select **"PostgreSQL"**
4. Choose plan (Free tier available)
5. Click **"Create"**
6. Copy the **Connection String** (DATABASE_URL)
7. Add it to environment variables

The connection string format:
```
postgresql://username:password@host:port/database
```

### Step 7: Deploy

1. Click **"Deploy"** button
2. Wait 5-10 minutes for build
3. Monitor logs in real-time
4. Look for "Deploy successful"

### Step 8: Run Initial Setup

After deployment, you need to run migrations and create admin user.

**Option A: Using Back4App CLI**

Install Back4App CLI:
```bash
npm install -g back4app-cli
```

Login and run commands:
```bash
back4app login
back4app run python manage.py migrate
back4app run python manage.py createsuperuser
```

**Option B: Using Web Console**

1. Go to your app dashboard
2. Click **"Console"** or **"Shell"**
3. Run these commands:

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Step 9: Access Your App

Your app will be available at:
```
https://your-app-name.back4app.io
```

Admin panel:
```
https://your-app-name.back4app.io/admin/
```

---

## Back4App-Specific Configuration

### Update Dockerfile for Back4App

Your current Dockerfile should work, but here's an optimized version for Back4App:

```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static files
RUN python manage.py collectstatic --no-input

# Run migrations on startup (optional)
# RUN python manage.py migrate

EXPOSE $PORT

# Use environment variable for port
CMD gunicorn pos_system.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
```

### Create Startup Script (Optional)

Create `start.sh` for automatic migrations:

```bash
#!/bin/bash

# Run migrations
python manage.py migrate --no-input

# Collect static files
python manage.py collectstatic --no-input

# Start gunicorn
gunicorn pos_system.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120
```

Then update Dockerfile CMD:
```dockerfile
CMD ["./start.sh"]
```

---

## Environment Variables Explained

### Required Variables

**SECRET_KEY**
Generate a secure key:
```python
# In Python shell
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

Or use online generator: https://djecrety.ir/

**DATABASE_URL**
Format: `postgresql://user:password@host:port/database`

Example:
```
postgresql://pos_user:mypassword@postgres.back4app.io:5432/pos_system
```

**ALLOWED_HOSTS**
Your Back4App domain:
```
your-app-name.back4app.io
```

For multiple domains:
```
your-app-name.back4app.io,www.yourdomain.com
```

### Optional Variables

```
DJANGO_LOG_LEVEL=INFO
TIME_ZONE=Africa/Nairobi
CORS_ALLOWED_ORIGINS=https://your-frontend.com
```

---

## Back4App Free Tier

**What's Included:**
- ✅ 1 container app
- ✅ 256MB RAM
- ✅ 0.25 vCPU
- ✅ PostgreSQL database (shared)
- ✅ 1GB storage
- ✅ SSL certificate (HTTPS)
- ✅ Custom domain support

**Limitations:**
- Container sleeps after 30 minutes of inactivity
- Cold start takes 10-30 seconds
- Limited resources (good for testing)

**Upgrade for Production:**
- Starter: $5/month (512MB RAM, no sleep)
- Pro: $25/month (1GB RAM, better performance)

---

## Troubleshooting

### Build Fails

**Error: "Dockerfile not found"**
- Make sure Dockerfile is in root directory
- Check file name is exactly `Dockerfile` (no extension)

**Error: "Requirements installation failed"**
- Check `requirements.txt` syntax
- Make sure all packages are available on PyPI

### App Won't Start

**Check logs:**
1. Go to Back4App dashboard
2. Click your app
3. Click **"Logs"** tab
4. Look for error messages

**Common issues:**
- Missing environment variables
- Database connection failed
- Port configuration wrong

### Database Connection Issues

**Error: "could not connect to server"**
- Verify DATABASE_URL is correct
- Check database is running in Back4App dashboard
- Make sure PostgreSQL addon is added

### Static Files Not Loading

**CSS/JS not working:**
- Make sure `collectstatic` runs in Dockerfile
- Check WhiteNoise is in MIDDLEWARE
- Verify STATIC_ROOT is set correctly

---

## Custom Domain (Optional)

To use your own domain:

1. Go to app settings
2. Click **"Domains"**
3. Add your custom domain
4. Update DNS records:
   - Type: CNAME
   - Name: www (or @)
   - Value: your-app-name.back4app.io
5. Wait for DNS propagation (up to 24 hours)
6. SSL certificate is auto-generated

---

## Updating Your App

Back4App auto-deploys when you push to GitHub:

```bash
# Make changes locally
git add .
git commit -m "Update feature X"
git push

# Back4App automatically:
# 1. Detects the push
# 2. Builds new Docker image
# 3. Deploys new version
# 4. Takes ~3-5 minutes
```

---

## Database Backups

### Manual Backup

```bash
# Using Back4App CLI
back4app run pg_dump -U username database > backup.sql

# Or download from dashboard
# Dashboard → Database → Backups → Download
```

### Automatic Backups

Back4App provides automatic daily backups on paid plans.

---

## Monitoring

**Check app health:**
- Dashboard shows CPU, memory, and request metrics
- View real-time logs
- Set up email alerts for downtime

**Database monitoring:**
- Check connection count
- Monitor storage usage
- View slow queries

---

## Cost Estimate

### Testing (Free Tier)
- Container: Free (with limitations)
- PostgreSQL: Free (shared)
- **Total: $0/month**

### Production (Recommended)
- Container (Starter): $5/month
- PostgreSQL (Dedicated): $15/month
- **Total: $20/month**

### With Custom Domain
- Custom domain: Free
- SSL certificate: Free (auto-provided)
- **Total: Still $20/month**

---

## Comparison: Back4App vs Render

| Feature | Back4App | Render |
|---------|----------|--------|
| Free Tier | ✅ Yes | ✅ Yes |
| Docker Support | ✅ Native | ✅ Optional |
| Database | PostgreSQL | PostgreSQL |
| Auto-deploy | ✅ Yes | ✅ Yes |
| Cold Start | ~30 sec | ~60 sec |
| Pricing | From $5/mo | From $7/mo |
| Best For | Docker users | Python users |

---

## Alternative: Back4App Parse Server

If you want to use Back4App's Parse Server (NoSQL) instead of Django:
- Different architecture
- Uses Parse SDK
- Not compatible with this Django app
- Would require complete rewrite

**Recommendation**: Use Back4App Container (this guide) for your Django app.

---

## Next Steps

After successful deployment:

1. ✅ Test all features thoroughly
2. ✅ Set up database backups
3. ✅ Configure external media storage (S3/Cloudinary)
4. ✅ Set up monitoring and alerts
5. ✅ Add custom domain (optional)
6. ✅ Upgrade to paid plan for production

---

## Support Resources

- **Back4App Docs**: https://www.back4app.com/docs
- **Container Docs**: https://www.back4app.com/docs/container
- **Community Forum**: https://community.back4app.com
- **Support**: support@back4app.com

---

## Quick Checklist

- [ ] Code pushed to GitHub
- [ ] Back4App account created
- [ ] App created (Container as a Service)
- [ ] GitHub repository connected
- [ ] PostgreSQL database added
- [ ] Environment variables set
- [ ] App deployed successfully
- [ ] Migrations run
- [ ] Admin user created
- [ ] App tested and working

---

**Ready to deploy?** Follow the steps above and your POS system will be live on Back4App! 🚀

**Estimated time**: 15-20 minutes for first deployment
