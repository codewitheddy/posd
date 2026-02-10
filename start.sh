#!/bin/bash
set -e

echo "Starting POS System deployment..."

# Run database migrations
echo "Running migrations..."
python manage.py migrate --no-input

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

# Create default data if needed (optional)
# echo "Setting up initial data..."
# python manage.py setup_permissions
# python manage.py setup_roles

echo "Starting Gunicorn server..."
# Start gunicorn with environment variable for port
gunicorn pos_system.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
