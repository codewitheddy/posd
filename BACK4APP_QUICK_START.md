# 🚀 Back4App Quick Start (10 Minutes)

## Step 1: Push to GitHub (2 minutes)

```bash
git init
git add .
git commit -m "Ready for Back4App"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

## Step 2: Create Back4App App (3 minutes)

1. Go to https://www.back4app.com/dashboard
2. Click **"Build new app"**
3. Select **"Container as a Service"**
4. Choose **"GitHub"** → Connect your repo
5. Select your repository and branch

## Step 3: Add PostgreSQL Database (2 minutes)

1. In app dashboard → **"Database"**
2. Click **"Add Database"** → **"PostgreSQL"**
3. Choose **Free** plan
4. Click **"Create"**
5. Copy the **Connection String**

## Step 4: Set Environment Variables (2 minutes)

Go to **"Environment Variables"** and add:

```
SECRET_KEY = [Click "Generate Random String"]
DEBUG = False
DATABASE_URL = [Paste PostgreSQL connection string from Step 3]
ALLOWED_HOSTS = your-app-name.back4app.io
PORT = 8000
```

## Step 5: Deploy (1 minute)

1. Click **"Deploy"** button
2. Wait 5-10 minutes ⏳
3. Watch the build logs

## Step 6: Create Admin User

Once deployed, go to **"Console"** and run:

```bash
python manage.py createsuperuser
```

## Done! 🎉

Your app is live at: `https://your-app-name.back4app.io`

---

## What You Get (Free Tier)

✅ Django POS System running  
✅ PostgreSQL database  
✅ HTTPS enabled  
✅ Auto-deploy on git push  
✅ 256MB RAM (good for testing)  

## Need More Details?

Read `BACK4APP_DEPLOYMENT.md` for the complete guide.

---

**That's it!** Your POS system is now live on Back4App. 🌐
