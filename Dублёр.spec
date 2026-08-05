# -*- mode: python ; coding: utf-8 -*-
# Конфигурация для macOS: --onedir (полная .app), thin-сборка под текущую архитектуру.
# psutil включён; universal2 отключён из-за C-расширений (fat binary). ijson — только чистый Python-бэкенд.

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ui_forms/about_dialog.ui', 'ui_forms'),
        ('assets/animations', 'assets/animations'),
    ],
    hiddenimports=[
        'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtUiTools',
        'psutil', 'ijson', 'ijson.backends.python', 'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ijson: только C/yajl-бэкенды исключены, используется чистый Python-бэкенд
        'ijson.backends._yajl2',
        'ijson.backends.yajl2_c',
        'ijson.backends.yajl2_cffi',
        'ijson.backends.yajl2',
        'ijson.backends.yajl',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Dублёр',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Dублёр',
)

app = BUNDLE(
    coll,
    name='Dублёр.app',
    icon='icon.icns',
    bundle_identifier='com.filmbackup.dubler',
)
