# Render Deployment - Quick Reference

## Essential Commands

### Gunicorn Start Command
```bash
gunicorn pos_system.wsgi:application --bind 0.0.0.0:$PORT
```

### Build Command
```bash
./build.sh
```

### Test Locally (Windows)
```bash
test_gunicorn.bat
```

### Test Locally (Linux/Mac)
```bash
chmod +x test_gunicorn.sh
./test_gunicorn.sh
```

## Project Structure

```
pos_system/              # Django project folder
├── wsgi.py             # WSGI application (pos_system.wsgi:application)
├── settings.py         # Django settings
└── urls.py             # URL configuration

pos/                    # Main app folder
├── models.py
├── views.py
└── ...

manage.py               # Django management
build.sh                # Render build script
render.yaml             # Render configuration
requirements.txt        # Python dependencies
```

## WSGI Path Explained

- **Module**: `pos_system.wsgi` (the wsgi.py file in pos_system folder)
- **Application**: `application` (the WSGI callable in wsgi.py)
- **Full path**: `pos_system.wsgi:application`

## Environment Variables (Render Dashboard)

| Variable | Value | Notes |
|----------|-------|-------|
| `PYTHON_VERSION` | `3.11.0` | Python version |
| `SECRET_KEY` | Auto-generated | Click "Generate" |
| `DEBUG` | `False` | Production mode |
| `DATABASE_URL` | Auto-set | From PostgreSQL service |
| `ALLOWED_HOSTS` | `your-app.onrender.com` | Your Render URL |
| `PORT` | Auto-set | Render provides this |

## Common Issues & Solutions

### Issue: "No module named 'gunicorn'"
**Solution**: Add `gunicorn>=21.2.0` to `requirements.txt` ✅ (Already added)

### Issue: "Application object not found"
**Solution**: Use correct path: `pos_system.wsgi:application` ✅ (Already fixed)

### Issue: "Permission denied: ./build.sh"
**Solution**: 
```bash
chmod +x build.sh
git add build.sh
git commit -m "Make build.sh executable"
git push
```

### Issue: "Static files not loading"
**Solution**: WhiteNoise is configured ✅ (Already added to middleware)

### Issue: "Database connection failed"
**Solution**: Use "Internal Database URL" from Render PostgreSQL dashboard

## Testing Before Deploy

### 1. Test Gunicorn Locally
```bash
# Windows
test_gunicorn.bat

# Linux/Mac
./test_gunicorn.sh
```

### 2. Test with Production Settings
```bash
# Set environment variables
set DEBUG=False
set SECRET_KEY=test-key-12345
set DATABASE_URL=sqlite:///db.sqlite3
set ALLOWED_HOSTS=localhost,127.0.0.1

# Run with gunicorn
gunicorn pos_system.wsgi:application --bind 127.0.0.1:8000
```

### 3. Visit http://localhost:8000
- Should see your POS system
- Static files should load
- Login should work

## Deployment Workflow

```
Local Changes → Git Push → Render Auto-Deploy → Live in 2-5 min
```

### Step by Step:
```bash
# 1. Make changes
# 2. Test locally
python manage.py runserver

# 3. Commit and push
git add .
git commit -m "Your changes"
git push

# 4. Render automatically:
#    - Detects push
#    - Runs build.sh
#    - Starts gunicorn
#    - Deploys new version
```

## Render Dashboard URLs

- **Dashboard**: https://dashboard.render.com
- **Your App**: https://your-app-name.onrender.com
- **Admin Panel**: https://your-app-name.onrender.com/admin/
- **API Docs**: https://your-app-name.onrender.com/api/docs/

## Shell Commands (Render Dashboard → Shell)

```bash
# Create superuser
python manage.py createsuperuser

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input

# Check database
python manage.py dbshell

# Django shell
python manage.py shell

# Check installed packages
pip list

# View environment variables
env
```

## File Checklist

- ✅ `render.yaml` - Render configuration
- ✅ `build.sh` - Build script (executable)
- ✅ `requirements.txt` - Includes gunicorn, whitenoise, dj-database-url
- ✅ `pos_system/wsgi.py` - WSGI application
- ✅ `pos_system/settings.py` - Updated for production
- ✅ `.gitignore` - Excludes sensitive files

## Support Resources

- **Render Docs**: https://render.com/docs/deploy-django
- **Django Deployment**: https://docs.djangoproject.com/en/stable/howto/deployment/
- **Gunicorn Docs**: https://docs.gunicorn.org/

## Quick Links

- 📖 Full Guide: `RENDER_DEPLOYMENT.md`
- ✅ Checklist: `DEPLOYMENT_CHECKLIST.md`
- 🚀 Quick Deploy: `QUICK_DEPLOY.md`

---

**Need help?** Check the logs in Render dashboard → Your Service → Logs tab
