# Docker Deployment Guide

## Important: You Have Two Options

### Option 1: Native Python (Recommended - Simpler)
✅ Use `render.yaml` + `build.sh` (already configured)  
✅ No Docker needed  
✅ Faster deployment  
✅ See `RENDER_DEPLOYMENT.md`

### Option 2: Docker (Advanced)
Use this guide if you prefer Docker or need containerization.

---

## Local Development with Docker

### Prerequisites
- Docker Desktop installed
- Docker Compose installed

### Quick Start

```bash
# Build and start containers
docker-compose up --build

# Visit http://localhost:8000
```

### Create Admin User

```bash
# In another terminal
docker-compose exec web python manage.py createsuperuser
```

### Stop Containers

```bash
docker-compose down
```

---

## Deploy to Render with Docker

### Step 1: Update render.yaml for Docker

Replace the content of `render.yaml` with:

```yaml
services:
  - type: web
    name: pos-system-docker
    runtime: docker
    plan: free
    dockerfilePath: ./Dockerfile
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: pos-db
          property: connectionString
      - key: SECRET_KEY
        generateValue: true
      - key: DEBUG
        value: False
      - key: ALLOWED_HOSTS
        sync: false
    autoDeploy: true

  - type: pgsql
    name: pos-db
    plan: free
    databaseName: pos_system
    databaseUser: pos_user
```

### Step 2: Push to GitHub

```bash
git add .
git commit -m "Add Docker support"
git push
```

### Step 3: Deploy on Render

1. Go to https://render.com/dashboard
2. New + → Blueprint
3. Connect your repository
4. Click "Apply"

---

## Docker Commands Reference

### Local Development

```bash
# Build and start
docker-compose up --build

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop containers
docker-compose down

# Remove volumes (reset database)
docker-compose down -v
```

### Django Management Commands

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic

# Django shell
docker-compose exec web python manage.py shell

# Access container shell
docker-compose exec web bash
```

### Database Commands

```bash
# Access PostgreSQL
docker-compose exec db psql -U pos_user -d pos_system

# Backup database
docker-compose exec db pg_dump -U pos_user pos_system > backup.sql

# Restore database
docker-compose exec -T db psql -U pos_user pos_system < backup.sql
```

---

## Production Docker Deployment

### Build Production Image

```bash
docker build -t pos-system:latest .
```

### Run Production Container

```bash
docker run -d \
  -p 8000:8000 \
  -e SECRET_KEY=your-secret-key \
  -e DEBUG=False \
  -e DATABASE_URL=postgresql://user:pass@host:5432/db \
  -e ALLOWED_HOSTS=yourdomain.com \
  --name pos-system \
  pos-system:latest
```

---

## Troubleshooting

### Port Already in Use

```bash
# Stop all containers
docker-compose down

# Or change port in docker-compose.yml
ports:
  - "8001:8000"  # Use 8001 instead
```

### Database Connection Issues

```bash
# Check if database is running
docker-compose ps

# View database logs
docker-compose logs db

# Restart database
docker-compose restart db
```

### Static Files Not Loading

```bash
# Collect static files
docker-compose exec web python manage.py collectstatic --no-input

# Restart web container
docker-compose restart web
```

### Reset Everything

```bash
# Stop and remove everything
docker-compose down -v

# Rebuild from scratch
docker-compose up --build
```

---

## Which Deployment Method Should You Use?

### Use Native Python (render.yaml + build.sh) if:
- ✅ You want simplicity
- ✅ You're new to deployment
- ✅ You don't need Docker features
- ✅ You want faster builds

### Use Docker if:
- ✅ You need consistent environments
- ✅ You're deploying to multiple platforms
- ✅ You have complex dependencies
- ✅ You're familiar with Docker

---

## Current Setup

Your project is configured for **both methods**:

- **Native Python**: `render.yaml` (default), `build.sh`
- **Docker**: `Dockerfile`, `docker-compose.yml`

Choose the one that fits your needs!

---

## Quick Comparison

| Feature | Native Python | Docker |
|---------|--------------|--------|
| Setup Complexity | Simple | Moderate |
| Build Time | Fast | Slower |
| Local Development | Use venv | Use containers |
| Deployment | Direct | Containerized |
| Best For | Most users | Advanced users |

---

**Recommendation**: Start with native Python deployment (see `RENDER_DEPLOYMENT.md`). Add Docker later if needed.
