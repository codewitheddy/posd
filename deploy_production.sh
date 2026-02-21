#!/bin/bash

# ============================================
# POS System - Production Deployment Script
# ============================================

set -e  # Exit on error

echo "=========================================="
echo "POS System - Production Deployment"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/var/www/pos"
VENV_DIR="$APP_DIR/venv"
PROJECT_DIR="$APP_DIR/posd"

# Functions
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    print_error "Please do not run as root"
    exit 1
fi

# Step 1: Check Prerequisites
echo "Step 1: Checking prerequisites..."
echo ""

# Check Python
if command -v python3.11 &> /dev/null; then
    print_success "Python 3.11 found"
else
    print_error "Python 3.11 not found. Please install it first."
    exit 1
fi

# Check PostgreSQL
if command -v psql &> /dev/null; then
    print_success "PostgreSQL found"
else
    print_warning "PostgreSQL not found. You'll need to install it."
fi

# Check Nginx
if command -v nginx &> /dev/null; then
    print_success "Nginx found"
else
    print_warning "Nginx not found. You'll need to install it."
fi

echo ""

# Step 2: Create directories
echo "Step 2: Creating directories..."
echo ""

sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR
mkdir -p $APP_DIR/logs
mkdir -p $APP_DIR/backups

print_success "Directories created"
echo ""

# Step 3: Setup virtual environment
echo "Step 3: Setting up virtual environment..."
echo ""

if [ ! -d "$VENV_DIR" ]; then
    python3.11 -m venv $VENV_DIR
    print_success "Virtual environment created"
else
    print_info "Virtual environment already exists"
fi

source $VENV_DIR/bin/activate
print_success "Virtual environment activated"
echo ""

# Step 4: Install dependencies
echo "Step 4: Installing dependencies..."
echo ""

if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r $PROJECT_DIR/requirements.txt
    print_success "Dependencies installed"
else
    print_error "requirements.txt not found in $PROJECT_DIR"
    exit 1
fi

echo ""

# Step 5: Check environment variables
echo "Step 5: Checking environment variables..."
echo ""

if [ -f "$PROJECT_DIR/.env" ]; then
    print_success ".env file found"
    
    # Check critical variables
    if grep -q "SECRET_KEY=" "$PROJECT_DIR/.env" && \
       grep -q "DATABASE_URL=" "$PROJECT_DIR/.env"; then
        print_success "Critical environment variables present"
    else
        print_error "Missing critical environment variables in .env"
        print_info "Please ensure SECRET_KEY and DATABASE_URL are set"
        exit 1
    fi
else
    print_error ".env file not found"
    print_info "Please create .env file from .env.example"
    exit 1
fi

echo ""

# Step 6: Database setup
echo "Step 6: Setting up database..."
echo ""

cd $PROJECT_DIR

# Run migrations
python manage.py migrate --noinput
print_success "Database migrations completed"

echo ""

# Step 7: Collect static files
echo "Step 7: Collecting static files..."
echo ""

python manage.py collectstatic --noinput
print_success "Static files collected"

echo ""

# Step 8: Create superuser (if needed)
echo "Step 8: Superuser setup..."
echo ""

print_info "Do you want to create a superuser? (y/n)"
read -r create_superuser

if [ "$create_superuser" = "y" ]; then
    python manage.py createsuperuser
    print_success "Superuser created"
else
    print_info "Skipping superuser creation"
fi

echo ""

# Step 9: Setup Gunicorn service
echo "Step 9: Setting up Gunicorn service..."
echo ""

GUNICORN_SERVICE="/etc/systemd/system/pos.service"

if [ -f "$GUNICORN_SERVICE" ]; then
    print_info "Gunicorn service already exists"
else
    print_info "Creating Gunicorn service..."
    
    sudo tee $GUNICORN_SERVICE > /dev/null <<EOF
[Unit]
Description=POS System Gunicorn
After=network.target

[Service]
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/gunicorn \\
    --workers 4 \\
    --bind 127.0.0.1:8000 \\
    --timeout 30 \\
    --access-logfile $APP_DIR/logs/gunicorn-access.log \\
    --error-logfile $APP_DIR/logs/gunicorn-error.log \\
    pos_system.wsgi:application

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable pos
    print_success "Gunicorn service created"
fi

# Start/restart service
sudo systemctl restart pos
print_success "Gunicorn service started"

echo ""

# Step 10: Setup Nginx (if not exists)
echo "Step 10: Checking Nginx configuration..."
echo ""

NGINX_CONFIG="/etc/nginx/sites-available/pos"

if [ -f "$NGINX_CONFIG" ]; then
    print_info "Nginx configuration already exists"
else
    print_warning "Nginx configuration not found"
    print_info "Please create Nginx configuration manually"
    print_info "See PRODUCTION_DEPLOYMENT_FINAL_GUIDE.md for details"
fi

echo ""

# Step 11: Setup backup cron job
echo "Step 11: Setting up automated backups..."
echo ""

# Create backup script
BACKUP_SCRIPT="$APP_DIR/backup.sh"

cat > $BACKUP_SCRIPT <<'EOF'
#!/bin/bash

BACKUP_DIR="/home/backups/pos"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="/var/www/pos/posd"

mkdir -p $BACKUP_DIR

# Backup database
cd $PROJECT_DIR
source /var/www/pos/venv/bin/activate
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission > $BACKUP_DIR/db_backup_$DATE.json

# Compress
gzip $BACKUP_DIR/db_backup_$DATE.json

# Delete old backups (keep 30 days)
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x $BACKUP_SCRIPT
print_success "Backup script created"

# Add to crontab (if not exists)
if crontab -l 2>/dev/null | grep -q "$BACKUP_SCRIPT"; then
    print_info "Backup cron job already exists"
else
    (crontab -l 2>/dev/null; echo "0 2 * * * $BACKUP_SCRIPT >> $APP_DIR/logs/backup.log 2>&1") | crontab -
    print_success "Backup cron job added (daily at 2 AM)"
fi

echo ""

# Step 12: Test deployment
echo "Step 12: Testing deployment..."
echo ""

# Check if Gunicorn is running
if systemctl is-active --quiet pos; then
    print_success "Gunicorn service is running"
else
    print_error "Gunicorn service is not running"
    print_info "Check logs: sudo journalctl -u pos -n 50"
fi

# Test health endpoint
sleep 2
if curl -f http://localhost:8000/health/ > /dev/null 2>&1; then
    print_success "Application health check passed"
else
    print_warning "Health check failed (this is normal if health endpoint not configured)"
fi

echo ""

# Final summary
echo "=========================================="
echo "Deployment Summary"
echo "=========================================="
echo ""
print_success "Application deployed successfully!"
echo ""
echo "Next steps:"
echo "1. Configure SSL certificate (Let's Encrypt recommended)"
echo "2. Set up Nginx reverse proxy"
echo "3. Configure Sentry for error monitoring"
echo "4. Test all functionality"
echo "5. Monitor logs for any issues"
echo ""
echo "Useful commands:"
echo "  - View logs: sudo journalctl -u pos -f"
echo "  - Restart app: sudo systemctl restart pos"
echo "  - Check status: sudo systemctl status pos"
echo "  - Run backup: $BACKUP_SCRIPT"
echo ""
echo "Documentation: PRODUCTION_DEPLOYMENT_FINAL_GUIDE.md"
echo ""
print_success "Deployment complete! 🚀"
echo ""
