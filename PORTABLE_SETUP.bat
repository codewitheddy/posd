@echo off
title POS System - Portable Setup
color 0B

echo.
echo ========================================
echo   POS SYSTEM - PORTABLE SETUP
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed!
    echo.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Python found!
echo.

echo Step 1: Installing dependencies...
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo Error installing dependencies!
    pause
    exit /b 1
)
echo Dependencies installed successfully!
echo.

echo Step 2: Setting up database...
if not exist db.sqlite3 (
    python manage.py migrate --noinput
    echo Database created!
) else (
    echo Database already exists.
)
echo.

echo Step 3: Loading sample data (optional)...
set /p LOAD_DATA="Load sample products? (Y/N): "
if /i "%LOAD_DATA%"=="Y" (
    python manage.py seed_data
    echo Sample data loaded!
)
echo.

echo ========================================
echo   SETUP COMPLETE!
echo ========================================
echo.
echo To start the POS system, run: START_POS.bat
echo.
pause
