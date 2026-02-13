#!/bin/bash
# Safe deployment script for Back4App
# This script ONLY runs safe commands that preserve data

set -e  # Exit on error

echo "🚀 Starting Back4App deployment..."
echo "⚠️  This script will NOT delete any existing data"
echo ""

# Navigate to project directory
cd "$(dirname "$0")"

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ ERROR: DATABASE_URL is not set!"
    echo "   This means you're using SQLite, which will lose data on redeploy."
    echo "   Please set DATABASE_URL in Back4App environment variables."
    exit 1
fi

echo "✓ DATABASE_URL is set (using PostgreSQL)"
echo ""

# Run migrations (SAFE - only applies new migrations, doesn't drop tables)
echo "📦 Running migrations..."
python manage.py migrate --noinput

if [ $? -eq 0 ]; then
    echo "✓ Migrations completed successfully"
else
    echo "❌ Migration failed!"
    exit 1
fi
echo ""

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

if [ $? -eq 0 ]; then
    echo "✓ Static files collected"
else
    echo "❌ Static file collection failed!"
    exit 1
fi
echo ""

# Verify data exists
echo "🔍 Verifying database data..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
from pos.models import Business

User = get_user_model()
user_count = User.objects.count()
business_count = Business.objects.count()

print(f"✓ Users in database: {user_count}")
print(f"✓ Businesses in database: {business_count}")

if user_count == 0:
    print("⚠️  WARNING: No users found! Database might be empty.")
if business_count == 0:
    print("⚠️  WARNING: No businesses found! Database might be empty.")
EOF

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Next steps:"
echo "   1. Visit your app URL to verify it's working"
echo "   2. Login and check that your businesses are still there"
echo "   3. If data is missing, restore from backup:"
echo "      python manage.py loaddata backup_YYYYMMDD_HHMMSS.json"
