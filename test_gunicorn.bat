@echo off
echo Testing Gunicorn configuration...
echo.

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Test gunicorn
echo Running: gunicorn pos_system.wsgi:application --bind 127.0.0.1:8000
echo.
echo Press Ctrl+C to stop the server
echo.
gunicorn pos_system.wsgi:application --bind 127.0.0.1:8000
