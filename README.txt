============================================================
  DENTAL CLINIC MANAGEMENT SYSTEM
  Complete Patient & Appointment Management
============================================================

QUICK START:
------------
1. Build one-file EXE:
  - Run: build_exe.bat
  - Output: dist\DentalClinicApp.exe

2. Build setup installer EXE (recommended):
  - Install Inno Setup: https://jrsoftware.org/isinfo.php
  - Run: build_installer.bat
  - Output: dist\DentalClinicSetup.exe

3. For development/manual run:
  - py dental_clinic.py
  - OR python dental_clinic.py

MANUAL START:
-------------
If you prefer command line:
  py dental_clinic.py
  OR
  python dental_clinic.py

FEATURES:
---------
✓ Patient Management - Add, view, manage patient records
✓ Appointment Scheduling - Schedule and track appointments
✓ Calendar Reservation View - See appointments in a month-style calendar
✓ Full Patient Profiles - Click a patient to view their complete history
✓ Patient Visits - Create structured visit records with diagnosis and outcomes
✓ Treatment Plans - Manage multi-step treatment plans with status tracking
✓ Treatment Records - Record treatments with costs
✓ Billing & Invoices - Track payments, invoice numbers, and revenue
✓ Revenues / Expense - Track clinic expenses and net profit
✓ Reporting System - Date-range operational summaries
✓ Medical Images Upload - Attach images to patient records
✓ Data Backup - Download the SQLite database backup
✓ Technical Support - Built-in help and troubleshooting tips
✓ Dashboard - Real-time statistics and overview
✓ Auto-Installation - Automatically installs all dependencies

NEW IN THIS VERSION:
--------------------
✓ Appointment calendar view for reservations
✓ Patient profile modal with appointments, visits, treatments, billing, plans, and images
✓ Dedicated Visits module/tab
✓ Treatment Plans, Expenses, Reports, and Support tabs
✓ Create visit records with: chief complaint, diagnosis, procedure summary, follow-up date, outcome
✓ Start a visit directly from an appointment with one click
✓ Visit status workflow: open, completed, follow-up-needed
✓ Dashboard now includes Total Visits metric
✓ Billing invoices now auto-generate invoice numbers

SYSTEM REQUIREMENTS:
--------------------
- Windows 10/11 (or Linux/Mac with Python)
- Python 3.8 or newer
- Internet connection (for initial setup only)

FIRST RUN:
----------
The system will automatically:
1. Check Python installation
2. Install required packages (Flask, Flask-CORS)
3. Create database
4. Open your browser

ACCESS:
-------
Once running, the system opens at:
http://127.0.0.1:5000

STOPPING:
---------
Press CTRL+C in the terminal window to stop the server

TROUBLESHOOTING:
----------------
- If "python not found": Install Python 3.11+ from https://www.python.org/downloads/
- If port 5000 is busy: Change port in dental_clinic.py line 849
- If browser doesn't open: Manually go to http://127.0.0.1:5000

DATA STORAGE:
-------------
All data is stored in: dental_clinic.db
Backup this file to preserve your data!

SUPPORT:
--------
This is a complete, self-contained system.
Everything runs locally on your computer.

BUILDING EXE + INSTALLER (WINDOWS):
-----------------------------------
1. Build one-file EXE:
  - Run: build_exe.bat
  - Output: dist\DentalClinicApp.exe

2. Build setup installer EXE (requires Inno Setup 6):
  - Install Inno Setup: https://jrsoftware.org/isinfo.php
  - Run: build_installer.bat
  - Output: dist\DentalClinicSetup.exe

NOTES:
------
- Dependencies are now tracked in requirements.txt
- Installer script is in clinic_installer.iss
- If the installer step fails, build the app EXE first using build_exe.bat

============================================================
