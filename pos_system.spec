# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect Django files
django_datas = collect_data_files('django')
django_hiddenimports = collect_submodules('django')

# Collect application data
app_datas = [
    ('pos/templates', 'pos/templates'),
    ('pos/migrations', 'pos/migrations'),
    ('pos_system', 'pos_system'),
    ('manage.py', '.'),
    ('.env.example', '.'),
    ('db.sqlite3', '.'),
]

# Collect all template files
for root, dirs, files in os.walk('pos/templates'):
    for file in files:
        if file.endswith('.html'):
            file_path = os.path.join(root, file)
            app_datas.append((file_path, root))

a = Analysis(
    ['run_server.py'],
    pathex=[],
    binaries=[],
    datas=django_datas + app_datas,
    hiddenimports=django_hiddenimports + [
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'pos',
        'pos.models',
        'pos.views',
        'pos.urls',
        'pos.admin',
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.lib',
        'reportlab.platypus',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='POS_System',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='POS_System',
)
