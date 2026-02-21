#!/bin/bash
# Don't exit on error - we want to see what fails
set +e

echo "========================================="
echo "Starting POS System deployment..."
echo "========================================="
echo ""

# Check environment
echo "[1/5] Checking environment..."
echo "PORT: ${PORT:-8000}"
echo "DATABASE_URL: ${DATABASE_URL:0:30}..." # Show first 30 chars only
echo "DEBUG: ${DEBUG:-not set}"
echo ""

# Run database migrations
echo "[2/5] Running migrations..."
python manage.py migrate --no-input
MIGRATE_EXIT=$?

if [ $MIGRATE_EXIT -ne 0 ]; then
    echo "❌ ERROR: Migrations failed with exit code $MIGRATE_EXIT"
    echo "Checking if database is accessible..."
    python manage.py dbshell --command="SELECT 1;" 2>&1 || echo "Database connection failed!"
    echo ""
    echo "Trying to continue anyway..."
fi
echo ""

# Collect static files
echo "[3/5] Collecting static files..."
python manage.py collectstatic --no-input
STATIC_EXIT=$?

if [ $STATIC_EXIT -ne 0 ]; then
    echo "⚠️  WARNING: Static files collection failed with exit code $STATIC_EXIT"
    echo "Continuing anyway..."
fi
echo ""

# Setup default data
echo "[4/5] Setting up default data..."
python manage.py setup_multitenant 2>&1 || echo "⚠️  setup_multitenant failed or not needed"
echo ""

# Start gunicorn
echo "[5/5] Starting Gunicorn server..."
echo "Binding to 0.0.0.0:${PORT:-8000}"
echo ""

exec gunicorn pos_system.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level debug \
    --capture-output \
    --enable-stdio-inheritance
