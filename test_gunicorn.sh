#!/bin/bash
echo "Testing Gunicorn configuration..."
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Test gunicorn
echo "Running: gunicorn pos_system.wsgi:application --bind 127.0.0.1:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
gunicorn pos_system.wsgi:application --bind 127.0.0.1:8000
