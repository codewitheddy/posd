# Render Deployment Checklist

Use this checklist to ensure smooth deployment to Render.

## Pre-Deployment

- [ ] Code is working locally
- [ ] All tests pass (if you have tests)
- [ ] `requirements.txt` is up to date
- [ ] `.gitignore` excludes sensitive files
- [ ] Environment variables are documented

## GitHub Setup

- [ ] Create GitHub repository
- [ ] Push code to GitHub
- [ ] Verify all files are committed
- [ ] Check `build.sh` is executable (`chmod +x build.sh`)

## Render Account Setup

- [ ] Create Render account at https://render.com
- [ ] Connect GitHub account to Render
- [ ] Verify email address

## Deployment Method

Choose one:

### Option A: Blueprint (Recommended)
- [ ] Verify `render.yaml` exists
- [ ] Click "New +" → "Blueprint"
- [ ] Select your repository
- [ ] Click "Apply"
- [ ] Wait for deployment

### Option B: Manual
- [ ] Create PostgreSQL database
- [ ] Copy Internal Database URL
- [ ] Create Web Service
- [ ] Set environment variables
- [ ] Deploy

## Post-Deployment

- [ ] Check deployment logs for errors
- [ ] Wait for "Deploy live" message
- [ ] Visit your app URL
- [ ] Create admin user via Shell
- [ ] Test login functionality
- [ ] Test POS features
- [ ] Check admin panel works
- [ ] Verify static files load correctly

## Configuration

- [ ] Update `ALLOWED_HOSTS` with your Render URL
- [ ] Set `DEBUG=False`
- [ ] Verify `SECRET_KEY` is set
- [ ] Check database connection
- [ ] Test CORS settings (if using API)

## Testing

- [ ] Create test product
- [ ] Process test sale
- [ ] Check reports
- [ ] Test user management
- [ ] Verify loyalty program
- [ ] Test offline functionality (if applicable)

## Production Readiness (Optional)

- [ ] Upgrade to paid plan (no spin down)
- [ ] Set up external media storage (S3/Cloudinary)
- [ ] Configure database backups
- [ ] Set up monitoring/alerts
- [ ] Add custom domain
- [ ] Configure SSL (auto-provided by Render)
- [ ] Set up error tracking (Sentry)
- [ ] Create backup admin user

## Documentation

- [ ] Update README with deployment info
- [ ] Document environment variables
- [ ] Create user guide for deployed version
- [ ] Share app URL with team/clients

## Maintenance

- [ ] Set up auto-deploy from GitHub
- [ ] Schedule regular database backups
- [ ] Monitor app performance
- [ ] Check logs regularly
- [ ] Plan for scaling if needed

---

## Quick Commands Reference

### Create Admin User (in Render Shell)
```bash
python manage.py createsuperuser
```

### Collect Static Files
```bash
python manage.py collectstatic --no-input
```

### Run Migrations
```bash
python manage.py migrate
```

### Check Database Connection
```bash
python manage.py dbshell
```

### View Logs
```bash
# In Render dashboard, click "Logs" tab
```

---

## Estimated Timeline

- GitHub setup: 5 minutes
- Render deployment: 5-10 minutes
- Testing: 10-15 minutes
- **Total: ~30 minutes**

---

## Need Help?

- 📖 Read `RENDER_DEPLOYMENT.md` for detailed guide
- 🔗 Visit https://render.com/docs
- 💬 Check Render Community Forum
- 📧 Contact Render support

---

**Status**: [ ] Not Started | [ ] In Progress | [ ] Completed ✅
