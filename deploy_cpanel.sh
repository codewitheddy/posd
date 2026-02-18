#!/bin/bash
# cPanel Deployment Script for Django POS System
# Run this script after uploading code to cPanel via SSH

echo "=========================================="
echo "Django POS System - cPanel Deployment"
echo "=========================================="
echo ""

# Check if we're in the right directory
if [ ! -f "manage.py" ]; then
    echo "❌ Error: manage.py not found. Please run this script from the Django project root."
    exit 1
fi

# Get cPanel username
read -p "Enter your cPanel username: " CPANEL_USERNAME
if [ -z "$CPANEL_USERNAME" ]; then
    echo "❌ Error: cPanel username is required"
    exit 1
fi

# Get Python version
read -p "Enter Python version (e.g., 3.11): " PYTHON_VERSION
if [ -z "$PYTHON_VERSION" ]; then
    PYTHON_VERSION="3.11"
fi

echo ""
echo "Configuration:"
echo "  cPanel Username: $CPANEL_USERNAME"
echo "  Python Version: $PYTHON_VERSION"
echo ""

# Construct virtual environment path
VENV_PATH="/home/$CPANEL_USERNAME/virtualenv/public_html/pos_app/posd/$PYTHON_VERSION"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Error: Virtual environment not found at $VENV_PATH"
    echo "Please create Python app in cPanel first."
    exit 1
fi

echo "✓ Virtual environment found"
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to activate virtual environment"
    exit 1
fi

echo "✓ Virtual environment activated"
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found"
    echo "Please create .env file from .env.example"
    read -p "Continue anyway? (y/n): " CONTINUE
    if [ "$CONTINUE" != "y" ]; then
        exit 1
    fi
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to install dependencies"
    exit 1
fi

echo "✓ Dependencies installed"
echo ""

# Install additional packages for cPanel
echo "Installing additional packages..."
pip install python-dotenv mysqlclient

echo "✓ Additional packages installed"
echo ""

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to collect static files"
    exit 1
fi

echo "✓ Static files collected"
echo ""

# Run migrations
echo "Running database migrations..."
python manage.py migrate

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to run migrations"
    exit 1
fi

echo "✓ Migrations completed"
echo ""

# Setup default data
echo "Setting up default data..."
python manage.py setup_multitenant

echo "✓ Default data setup completed"
echo ""

# Create restart file
echo "Restarting application..."
mkdir -p tmp
touch tmp/restart.txt

echo "✓ Application restarted"
echo ""

echo "=========================================="
echo "✅ Deployment completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Create superuser: python manage.py createsuperuser"
echo "2. Test your application at your domain"
echo "3. Check error logs if issues occur"
echo ""
echo "Useful commands:"
echo "  - View logs: tail -f ~/logs/yourdomain.com.error.log"
echo "  - Restart app: touch ~/public_html/pos_app/posd/tmp/restart.txt"
echo "  - Django shell: python manage.py shell"
echo ""
