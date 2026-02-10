@echo off
echo ========================================
echo POS System - Build Executable
echo ========================================
echo.

echo Step 1: Installing build dependencies...
python -m pip install -r requirements_build.txt
if %errorlevel% neq 0 (
    echo Error installing dependencies!
    pause
    exit /b 1
)
echo.

echo Step 2: Collecting static files...
python manage.py collectstatic --noinput
echo.

echo Step 3: Running migrations...
python manage.py migrate
echo.

echo Step 4: Building executable with PyInstaller...
pyinstaller pos_system.spec --clean
if %errorlevel% neq 0 (
    echo Error building executable!
    pause
    exit /b 1
)
echo.

echo ========================================
echo Build Complete!
echo ========================================
echo.
echo Executable location: dist\POS_System\POS_System.exe
echo.
echo Next steps:
echo 1. Test the executable: cd dist\POS_System ^&^& POS_System.exe
echo 2. Create installer (optional): Run create_installer.bat
echo.
pause
