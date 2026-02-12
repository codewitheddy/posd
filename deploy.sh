#!/bin/bash
# Production Deployment Script for POS System

set -e  # Exit on error

echo "========================================="
echo "POS System Production Deployment"
echo "========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}Error: Do not run this script as root${NC}"
    exit 1
fi

# Check environment variables
echo -e "${YELLOW}Checking environment variables...${NC}"
required_vars=("SECRET_KEY" "ALLOWED_HOSTS" "DATABASE_URL")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}Error: $var is not set${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ Environment variables OK${NC}"

# Backup database
echo -e "${YELLOW}Creating database backup...${NC}"
python manage.py backup_database || echo -e "${YELLOW}Warning: Backup command not found${NC}"

# Pull latest code
echo -e "${YELLOW}Pulling latest code...${NC}"
git pull origin main

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install -r requirements_production.txt

# Run migrations
echo -e "${YELLOW}Running database migrations...${NC}"
python manage.py migrate --noinput

# Collect static files
echo -e "${YELLOW}Collecting static files...${NC}"
python manage.py collectstatic --noinput --clear

# Run security check
echo -e "${YELLOW}Running security check...${NC}"
python manage.py check --deploy

# Run tests (optional - comment out if too slow)
# echo -e "${YELLOW}Running tests...${NC}"
# python manage.py test --parallel

# Restart application
echo -e "${YELLOW}Restarting application...${NC}"
if [ -f "/etc/systemd/system/pos.service" ]; then
    sudo systemctl restart pos
    echo -e "${GREEN}✓ Application restarted${NC}"
else
    echo -e "${YELLOW}Warning: systemd service not found. Please restart manually.${NC}"
fi

# Clear cache (if using Redis)
if [ ! -z "$REDIS_URL" ]; then
    echo -e "${YELLOW}Clearing cache...${NC}"
    python manage.py shell -c "from django.core.cache import cache; cache.clear()"
    echo -e "${GREEN}✓ Cache cleared${NC}"
fi

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Check application logs: tail -f logs/django_error.log"
echo "2. Monitor application: systemctl status pos"
echo "3. Test critical paths"
echo ""
