# Back4App Deployment Checklist - Preserve Database

## ⚠️ CRITICAL: Never Run These Commands on Back4App

These commands will DELETE your data:
- ❌ `python manage.py flush`
- ❌ `python manage.py migrate --run-syncdb`
- ❌ `python manage.py reset_db`
- ❌ `python manage.py migrate --fake-initial`
- ❌ Deleting migration files after initial deployment

## ✅ Safe Deployment Process

### Before Every Deployment

1. **Backup Your Database**
   ```bash
   # In Back4App Console
   cd posd
   python manage.py dumpdata --natural-foreign --natural-primary \
     -e contenttypes -e auth.Permission \
     --indent 2 > backup_$(date +%Y%m%d_%H%M%S).json
   ```

2. **Test Migrations Locally**
   ```bash
   # On your local machine
   cd posd
   python manage.py makemigrations --dry-run
   python manage.py migrate --plan
   ```

### Deployment Steps

1. **Push Code to Back4App**
   ```bash
   git add .
   git commit -m "Your commit message"
   git push back4app main
   ```

2. **Wait for Build to Complete**
   - Monitor Back4App dashboard
   - Check build logs for errors

3. **Run Migrations (SAFE)**
   ```bash
   # In Back4App Console
   cd posd
   python manage.py migrate
   ```

4. **Collect Static Files**
   ```bash
   cd posd
   python manage.py collectstatic --noinput
   ```

5. **Verify Data Persists**
   ```bash
   cd posd
   python manage.py shell
   ```
   
   In Python shell:
   ```python
   from pos.models import Business, User
   print(f"Users: {User.objects.count()}")
   print(f"Businesses: {Business.objects.count()}")
   # Should show your existing data
   ```

### After Deployment

1. **Test the Application**
   - Visit your app URL
   - Login with existing account
   - Verify businesses are still there
   - Create a test business
   - Redeploy and verify test business persists

2. **Check Logs**
   ```bash
   # In Back4App Console
   tail -f logs/django_info.log
   ```

## 🔧 Back4App Environment Variables

Ensure these are set in Back4App Dashboard → Server Settings → Environment Variables:

```bash
# Required
DATABASE_URL=<automatically provided by Back4App>
SECRET_KEY=<your-secret-key>
ALLOWED_HOSTS=your-app.b4a.run
DEBUG=False

# Optional
TEST_MODE=True  # For demo mode (bypasses authentication)
CSRF_TRUSTED_ORIGINS=https://your-app.b4a.run
```

## 🚨 Troubleshooting Data Loss

### If Data is Missing After Deployment

1. **Check if database still has data:**
   ```bash
   cd posd
   python manage.py dbshell
   ```
   
   In database shell:
   ```sql
   SELECT COUNT(*) FROM pos_business;
   SELECT COUNT(*) FROM auth_user;
   \q
   ```

2. **If data exists in database but not showing:**
   - Check middleware is working
   - Check business filtering in views
   - Restart the application

3. **If data is truly lost:**
   - Restore from backup:
     ```bash
     cd posd
     python manage.py loaddata backup_20260213_120000.json
     ```

### Common Causes of Data Loss

1. **Using SQLite instead of PostgreSQL**
   - Check: `echo $DATABASE_URL` should show postgres://
   - Fix: Ensure DATABASE_URL is set in environment variables

2. **Running destructive commands**
   - Never use flush, syncdb, or reset_db
   - Only use `migrate` command

3. **Deleting migration files**
   - Keep all migration files in git
   - Never delete migrations after initial deployment

4. **Database connection issues**
   - Check DATABASE_URL is correct
   - Verify PostgreSQL service is running

## 📋 Pre-Deployment Checklist

Before each deployment, verify:

- [ ] All migration files are committed to git
- [ ] Tested migrations locally
- [ ] Created database backup
- [ ] No destructive commands in deployment script
- [ ] DATABASE_URL environment variable is set
- [ ] requirements.txt includes psycopg2-binary and dj-database-url

## 🎯 Quick Reference

**Safe commands:**
```bash
python manage.py migrate              # ✅ Apply new migrations
python manage.py collectstatic        # ✅ Collect static files
python manage.py createsuperuser      # ✅ Create admin (if doesn't exist)
python manage.py dumpdata            # ✅ Backup database
python manage.py loaddata            # ✅ Restore database
```

**Dangerous commands (NEVER USE):**
```bash
python manage.py flush               # ❌ Deletes all data
python manage.py migrate --run-syncdb # ❌ Recreates tables
python manage.py reset_db            # ❌ Drops database
```

## 📞 Need Help?

If you continue to lose data:
1. Check Back4App logs for errors
2. Verify DATABASE_URL is set correctly
3. Ensure you're not running destructive commands
4. Contact Back4App support if database is being reset

## ✅ Success Indicators

Your deployment is successful when:
- [ ] Businesses count remains the same before and after deployment
- [ ] Users can login with existing accounts
- [ ] New data persists across deployments
- [ ] No "relation does not exist" errors
- [ ] DATABASE_URL points to PostgreSQL (not SQLite)
