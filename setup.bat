@echo off
echo ========================================
echo POS System Setup Script
echo ========================================
echo.

echo Step 1: Installing dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Error installing dependencies!
    pause
    exit /b 1
)
echo.

echo Step 2: Running migrations...
python manage.py makemigrations
python manage.py migrate
if %errorlevel% neq 0 (
    echo Error running migrations!
    pause
    exit /b 1
)
echo.

echo Step 3: Loading sample data...
python manage.py seed_data
echo.

echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Create admin user: python manage.py createsuperuser
echo 2. Start server: python manage.py runserver
echo 3. Open browser: http://127.0.0.1:8000/
echo.
pause
