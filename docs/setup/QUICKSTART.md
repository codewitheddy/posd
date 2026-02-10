# Quick Start Guide

Get your POS system running in 5 minutes!

## Windows Users

### Option 1: Automated Setup
```cmd
setup.bat
```

### Option 2: Manual Setup
```cmd
python -m pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser
python manage.py runserver
```

## Linux/Mac Users

### Option 1: Automated Setup
```bash
chmod +x setup.sh
./setup.sh
```

### Option 2: Manual Setup
```bash
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser
python manage.py runserver
```

## Access the System

1. **Main Application**: http://127.0.0.1:8000/
2. **Admin Panel**: http://127.0.0.1:8000/admin/

## Default Test Data

After running `seed_data`, you'll have:
- 5 categories (Beverages, Snacks, Groceries, Personal Care, Household)
- 20 sample products with realistic Kenyan prices

## First Steps

1. **Dashboard**: View quick stats and access all features
2. **New Sale**: Click "New Sale" to start selling
3. **Products**: Manage your inventory
4. **Reports**: View daily sales summaries

## Making Your First Sale

1. Go to **New Sale** (POS screen)
2. Click on products to add them to cart
3. Adjust quantities if needed
4. Apply discount (optional)
5. Click **Complete Sale**
6. View/print/download invoice

## Customization

Edit `pos_system/settings.py`:
```python
VAT_RATE = 16  # Change VAT rate
SHOP_NAME = 'Your Shop Name'  # Change shop name
```

## Need Help?

Check the full README.md for detailed documentation.

## Production Deployment

Before going live:
1. Set `DEBUG = False` in settings.py
2. Generate new `SECRET_KEY`
3. Use PostgreSQL instead of SQLite
4. Configure proper hosting (Heroku, DigitalOcean, etc.)

---

**Happy Selling! 🛒**
