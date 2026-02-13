# Back4App Database Persistence Issue - SOLUTION

## Problem
When redeploying on Back4App, all created businesses are lost except the admin user.

## Root Cause Analysis

Your configuration is **CORRECT**:
- ✅ `settings.py` uses `DATABASE_URL` for PostgreSQL
- ✅ `requirements.txt` has `psycopg2-binary` and `dj-database-url`
- ✅ Database should persist across deployments

The issue is likely caused by:
1. **Running destructive commands** during deployment (flush, syncdb, reset_db)
2. **Deleting migration files** after initial deployment
3. **DATABASE_URL not being set** in Back4App environment variables

## Immediate Solution

### Step 1: Verify DATABASE_URL is Set

**In Back4App Console:**
```bash
echo $DATABASE_URL
```

**Expected output:**
```
postgres://username:password@host:port/database
```

**If empty or shows SQLite:**
- Go to Back4App Dashboard → Your App → Database
- Add a PostgreSQL database
- DATABASE_URL will be automatically set

### Step 2: Check What Commands Run on Deployment

**In Back4App Dashboard:**
1. Go to **Server Settings** → **Custom Build** or **Deploy Settings**
2. Check the deployment commands
3. **Remove any of these dangerous commands:**
   - ❌ `python manage.py flush`
   - ❌ `python manage.py migrate --run-syncdb`
   - ❌ `python manage.py reset_db`
   - ❌ `python manage.py migrate --fake-initial`

4. **Only use these safe commands:**
   - ✅ `python manage.py migrate`
   - ✅ `python manage.py collectstatic --noinput`

### Step 3: Use the Safe Deployment Script

**File created**: `posd/deploy_back4app.sh`

This script:
- ✅ Checks DATABASE_URL is set
- ✅ Runs only safe migrations
- ✅ Collects static files
- ✅ Verifies data exists after deployment
- ❌ Never deletes or flushes data

**To use:**
```bash
# In Back4App Console
cd posd
bash deploy_back4app.sh
```

### Step 4: Backup Before Each Deployment

**Create backup:**
```bash
cd posd
python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.Permission \
  --indent 2 > backup_$(date +%Y%m%d_%H%M%S).json
```

**Restore if needed:**
```bash
python manage.py loaddata backup_20260213_120000.json
```

## Prevention Checklist

Before each deployment:

- [ ] DATABASE_URL is set in Back4App environment variables
- [ ] No destructive commands in deployment script
- [ ] All migration files are committed to git
- [ ] Created a database backup
- [ ] Tested migrations locally first

## Quick Fix If Data is Already Lost

1. **Check if data still exists in database:**
   ```bash
   cd posd
   python manage.py dbshell
   SELECT COUNT(*) FROM pos_business;
   SELECT COUNT(*) FROM auth_user;
   \q
   ```

2. **If data exists but not showing:**
   - Restart the application
   - Check middleware is working
   - Verify business filtering in views

3. **If data is truly lost:**
   - Restore from backup (if you have one)
   - Or recreate businesses manually
   - Then follow prevention steps above

## Files Created

1. **BACK4APP_DATABASE_PERSISTENCE_FIX.md** - Detailed troubleshooting guide
2. **posd/DEPLOY_BACK4APP_CHECKLIST.md** - Deployment checklist
3. **posd/deploy_back4app.sh** - Safe deployment script

## Common Mistakes to Avoid

1. ❌ Running `python manage.py flush` on production
2. ❌ Using `--run-syncdb` flag with migrate
3. ❌ Deleting migration files after deployment
4. ❌ Not setting DATABASE_URL environment variable
5. ❌ Using SQLite in production (loses data on redeploy)

## Verification Steps

After next deployment:

1. **Before deployment:**
   ```bash
   # Count businesses
   python manage.py shell -c "from pos.models import Business; print(Business.objects.count())"
   ```

2. **Deploy using safe script:**
   ```bash
   bash deploy_back4app.sh
   ```

3. **After deployment:**
   ```bash
   # Count businesses again - should be same number
   python manage.py shell -c "from pos.models import Business; print(Business.objects.count())"
   ```

## Status

✅ **Configuration is correct** - Your settings.py and requirements.txt are properly configured

⚠️ **Action needed** - Follow the steps above to ensure safe deployments

📋 **Use the checklist** - Follow `DEPLOY_BACK4APP_CHECKLIST.md` for every deployment

🔧 **Use the script** - Run `deploy_back4app.sh` instead of manual commands
