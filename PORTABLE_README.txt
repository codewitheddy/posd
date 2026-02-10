================================================================================
                    POS SYSTEM - PORTABLE VERSION
                           Version 1.3.0
================================================================================

WHAT IS THIS?
-------------
This is a portable version of the POS (Point of Sale) System. It can run on
any Windows computer with Python installed, or you can install Python if needed.

QUICK START (3 STEPS)
---------------------

STEP 1: Install Python (if not already installed)
   - Download from: https://www.python.org/downloads/
   - Install Python 3.8 or higher
   - IMPORTANT: Check "Add Python to PATH" during installation
   - Restart computer after installation

STEP 2: Run Setup
   - Double-click: PORTABLE_SETUP.bat
   - Wait for dependencies to install
   - Choose whether to load sample data

STEP 3: Start POS System
   - Double-click: START_POS.bat
   - Browser opens automatically
   - Create admin user when prompted
   - Start using!

FEATURES
--------
✓ Product Management (with barcode support)
✓ Inventory Tracking (stock levels & alerts)
✓ Point of Sale (fast checkout)
✓ Invoice Generation (PDF & print)
✓ Sales Reports (daily summaries)
✓ CSV Bulk Upload (add products in bulk)
✓ Kenya VAT Support (16%)

SYSTEM REQUIREMENTS
-------------------
- Windows 10 or higher
- Python 3.8 or higher
- 4 GB RAM minimum
- 500 MB free disk space
- Internet (only for initial setup)

FOLDER STRUCTURE
----------------
POS_System_Portable/
├── PORTABLE_SETUP.bat      ← Run this first
├── START_POS.bat            ← Run this to start
├── PORTABLE_README.txt      ← This file
├── USER_GUIDE.txt           ← Detailed user guide
├── manage.py                ← Django management
├── requirements.txt         ← Dependencies
├── pos/                     ← Application code
├── pos_system/              ← Settings
├── db.sqlite3               ← Database (created on setup)
└── Documentation/           ← All guides (.md files)

FIRST TIME USE
--------------
1. After starting, create an admin user:
   - Username: admin (or your choice)
   - Email: (optional)
   - Password: (choose a strong password)

2. Access the system:
   - URL: http://127.0.0.1:8000
   - Login with your admin credentials

3. Add products:
   - Click "Products" → "Add Product"
   - Or use "Bulk Upload" for multiple products

4. Make your first sale:
   - Click "New Sale"
   - Select products
   - Complete sale
   - Print invoice

BACKUP YOUR DATA
----------------
IMPORTANT: Backup regularly!

To backup:
1. Copy the file: db.sqlite3
2. Save to USB drive, cloud storage, or external drive
3. Keep multiple backups

To restore:
1. Close POS System
2. Replace db.sqlite3 with your backup
3. Restart POS System

TROUBLESHOOTING
---------------

Problem: Python not found
Solution: Install Python from python.org
         Make sure "Add Python to PATH" is checked

Problem: Dependencies won't install
Solution: Run as Administrator
         Check internet connection

Problem: Port 8000 already in use
Solution: Close other applications
         Or edit START_POS.bat to use different port

Problem: Browser doesn't open
Solution: Manually open http://127.0.0.1:8000

Problem: Can't login
Solution: Create new superuser:
         python manage.py createsuperuser

UPDATING
--------
To update to a new version:
1. Backup db.sqlite3
2. Extract new version to new folder
3. Copy db.sqlite3 to new folder
4. Run PORTABLE_SETUP.bat
5. Run START_POS.bat

DOCUMENTATION
-------------
Detailed guides included:
- USER_GUIDE.txt - Complete user manual
- README.md - Full documentation
- QUICKSTART.md - Quick start guide
- BARCODE_FEATURE.md - Barcode scanning guide
- INVENTORY_MANAGEMENT.md - Stock management guide
- CSV_BULK_UPLOAD.md - Bulk upload guide

SUPPORT
-------
For help:
1. Read USER_GUIDE.txt
2. Check documentation files
3. Visit: https://docs.djangoproject.com/

RUNNING FROM USB
----------------
Yes! You can run this from a USB drive:
1. Copy entire folder to USB
2. Run PORTABLE_SETUP.bat (first time only)
3. Run START_POS.bat to use
4. Data stays on USB
5. Use on any computer

OFFLINE USE
-----------
After initial setup, the system works completely offline.
Internet is only needed for:
- Initial Python installation
- Initial dependency installation
- Updates (optional)

SECURITY
--------
- Use strong passwords
- Backup regularly
- Don't share admin credentials
- Keep USB drive secure (if using)

LICENSE
-------
See LICENSE.txt for full license information.

CREDITS
-------
Built with:
- Django 4.2.7 (Web Framework)
- Bootstrap 5 (UI Framework)
- ReportLab (PDF Generation)
- SQLite (Database)

================================================================================

Thank you for using POS System!

For the latest version and updates, visit our website.

================================================================================
