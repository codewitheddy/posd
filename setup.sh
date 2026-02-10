#!/bin/bash

echo "========================================"
echo "POS System Setup Script"
echo "========================================"
echo ""

echo "Step 1: Installing dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "Error installing dependencies!"
    exit 1
fi
echo ""

echo "Step 2: Running migrations..."
python manage.py makemigrations
python manage.py migrate
if [ $? -ne 0 ]; then
    echo "Error running migrations!"
    exit 1
fi
echo ""

echo "Step 3: Loading sample data..."
python manage.py seed_data
echo ""

echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Create admin user: python manage.py createsuperuser"
echo "2. Start server: python manage.py runserver"
echo "3. Open browser: http://127.0.0.1:8000/"
echo ""
