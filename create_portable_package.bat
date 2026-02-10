@echo off
title Create Portable Package
color 0E

echo.
echo ========================================
echo   CREATE PORTABLE PACKAGE
echo ========================================
echo.

REM Create package directory
set PACKAGE_DIR=POS_System_Portable_v1.3.0
if exist %PACKAGE_DIR% rmdir /s /q %PACKAGE_DIR%
mkdir %PACKAGE_DIR%

echo Copying files...

REM Copy essential files
copy PORTABLE_SETUP.bat %PACKAGE_DIR%\
copy START_POS.bat %PACKAGE_DIR%\
copy PORTABLE_README.txt %PACKAGE_DIR%\README.txt
copy USER_GUIDE.txt %PACKAGE_DIR%\
copy LICENSE.txt %PACKAGE_DIR%\
copy manage.py %PACKAGE_DIR%\
copy requirements.txt %PACKAGE_DIR%\
copy run_server.py %PACKAGE_DIR%\
copy sample_products.csv %PACKAGE_DIR%\
copy .env.example %PACKAGE_DIR%\

REM Copy directories
xcopy /E /I /Q pos %PACKAGE_DIR%\pos
xcopy /E /I /Q pos_system %PACKAGE_DIR%\pos_system

REM Create Documentation folder
mkdir %PACKAGE_DIR%\Documentation
copy *.md %PACKAGE_DIR%\Documentation\

REM Clean up Python cache
for /d /r %PACKAGE_DIR% %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q %PACKAGE_DIR%\*.pyc 2>nul

echo.
echo Creating ZIP file...
powershell -command "Compress-Archive -Path '%PACKAGE_DIR%' -DestinationPath '%PACKAGE_DIR%.zip' -Force"

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   PACKAGE CREATED SUCCESSFULLY!
    echo ========================================
    echo.
    echo Package: %PACKAGE_DIR%.zip
    echo Size: 
    powershell -command "(Get-Item '%PACKAGE_DIR%.zip').Length / 1MB | ForEach-Object { '{0:N2} MB' -f $_ }"
    echo.
    echo Contents:
    echo - Portable setup script
    echo - Start script
    echo - Complete POS system
    echo - All documentation
    echo - Sample data
    echo.
    echo Ready to distribute!
    echo.
) else (
    echo.
    echo ERROR: Failed to create ZIP file!
    echo.
)

REM Clean up temporary directory
rmdir /s /q %PACKAGE_DIR%

pause
