@echo off
title POS System
color 0A

echo.
echo ========================================
echo      POS SYSTEM - Point of Sale
echo ========================================
echo.
echo Starting application...
echo.
echo The POS system will open in your browser.
echo.
echo Server URL: http://127.0.0.1:8000
echo.
echo Press CTRL+C to stop the server
echo ========================================
echo.

python run_server.py

pause
