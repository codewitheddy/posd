"""
POS System Launcher
This script starts the Django development server for the POS system
"""
import os
import sys
import django
import webbrowser
import time
from threading import Timer

def open_browser():
    """Open browser after server starts"""
    time.sleep(2)  # Wait for server to start
    webbrowser.open('http://127.0.0.1:8000')

def main():
    """Main entry point for the POS system"""
    # Set up Django environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pos_system.settings')
    
    # Get the base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base_dir)
    
    # Setup Django
    django.setup()
    
    # Import Django management
    from django.core.management import execute_from_command_line
    
    print("=" * 60)
    print("POS SYSTEM - Point of Sale")
    print("=" * 60)
    print("\nStarting server...")
    print("The application will open in your browser automatically.")
    print("\nServer URL: http://127.0.0.1:8000")
    print("\nPress CTRL+C to stop the server")
    print("=" * 60)
    print()
    
    # Open browser after delay
    Timer(2.0, open_browser).start()
    
    # Start Django development server
    try:
        execute_from_command_line(['manage.py', 'runserver', '--noreload'])
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        print("Thank you for using POS System!")
        sys.exit(0)

if __name__ == '__main__':
    main()
