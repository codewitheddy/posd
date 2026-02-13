# Back4App Quick Setup Guide

## 🚀 Deploy POS System to Back4App (No Authentication)

### Step 1: Set Environment Variable

1. Go to your Back4App dashboard
2. Select your app
3. Navigate to: **Server Settings** → **Environment Variables**
4. Click **Add Variable**
5. Add:
   ```
   Key: TEST_MODE
   Value: True
   ```
6. Click **Save**

### Step 2: That's It!

The middleware is already configured. When `TEST_MODE=True`, the app will:
- ✅ Automatically log users in as superuser
- ✅ Bypass all authentication requirements
- ✅ Allow immediate access to all features

---

## 📋 Complete Back4App Environment Variables

Set these in Back4App dashboard:

```bash
# Required
TEST_MODE=True                    # Bypass authentication
SECRET_KEY=your-random-secret-key # Generate a new one

# Optional (Back4App provides DATABASE_URL automatically)
DEBUG=False
ALLOWED_HOSTS=your-app.b4a.run
```

---

## 🔑 Generate Secret Key

Run this in Python:

```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

Or use this online: https://djecrety.ir/

---

## 📦 Deploy to Back4App

### Option 1: Via Git (Recommended)

```bash
# Get your Back4App Git URL from dashboard
git remote add back4app <your-git-url>

# Push to Back4App
git push back4app main
```

### Option 2: Via Back4App CLI

```bash
# Install Back4App CLI
npm install -g back4app-cli

# Login
back4app login

# Deploy
back4app deploy
```

---

## 🔧 After Deployment

### Run Migrations

In Back4App Console:

```bash
cd posd
python manage.py migrate
python manage.py collectstatic --noinput
```

### Create Initial Data (Optional)

```bash
python manage.py setup_business
python manage.py setup_payment_methods
python manage.py seed_data
```

---

## ✅ Verify Deployment

1. Visit: `https://your-app.b4a.run`
2. Should load directly without login
3. Check logs for: `⚠️ TEST_MODE ENABLED`

---

## 🔒 Security Note

**TEST_MODE is for demo/testing only!**

For production:
1. Set `TEST_MODE=False`
2. Use proper authentication
3. Enable security features

---

## 🐛 Troubleshooting

### Still Asking for Login?

**Check:**
1. TEST_MODE is set to `True` (not `true` or `1`)
2. App was restarted after setting variable
3. Check logs for TEST_MODE message

**Fix:**
```bash
# In Back4App console
echo $TEST_MODE  # Should show: True
```

### Database Errors?

**Run migrations:**
```bash
cd posd
python manage.py migrate
```

### Static Files Not Loading?

**Collect static files:**
```bash
cd posd
python manage.py collectstatic --noinput
```

---

## 📞 Need Help?

Check the detailed guide: `BACK4APP_NO_AUTH_GUIDE.md`
