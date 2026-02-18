"""
Passenger WSGI file for cPanel deployment
Replace 'yourusername' with your actual cPanel username
"""
import os
import sys

# IMPORTANT: Replace 'yourusername' with your actual cPanel username
CPANEL_USERNAME = 'yourusername'

# Add your project directory to the sys.path
project_home = f'/home/{CPANEL_USERNAME}/public_html/pos_app/posd'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set environment variables
os.environ['DJANGO_SETTINGS_MODULE'] = 'pos_system.settings'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')

# Activate virtual environment
# IMPORTANT: Update Python version (3.11) if different
INTERP = f"/home/{CPANEL_USERNAME}/virtualenv/public_html/pos_app/posd/3.11/bin/python3"
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# Import Django application
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
