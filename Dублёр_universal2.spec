# -*- mode: python ; coding: utf-8 -*-
# Сборка universal2 (один .app для Intel x86_64 и Apple Silicon arm64).
# Использовать с Python и venv из python.org: .venv_universal2 (см. BUILD_INSTRUCTIONS.md).
# psutil в excludes: типичный pip-пакет на Apple Silicon — thin (arm64), из-за чего universal2 падает.
# Если lipo подтвердил fat для psutil — можно убрать psutil из excludes ниже.

import re
from pathlib import Path


main_window_source = Path(SPECPATH) / 'ui_new' / 'main_window_new.py'
version_match = re.search(
    r'^\s*APP_VERSION\s*=\s*"([^"]+)"',
    main_window_source.read_text(encoding='utf-8'),
    re.MULTILINE,
)
if version_match is None:
    raise RuntimeError(f'APP_VERSION не найден в {main_window_source}')
app_version = version_match.group(1)


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
        'ijson', 'ijson.backends.python', 'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ijson: только C/yajl-бэкенды
        'ijson.backends._yajl2',
        'ijson.backends.yajl2_c',
        'ijson.backends.yajl2_cffi',
        'ijson.backends.yajl2',
        'ijson.backends.yajl',
        # psutil: C-расширение часто thin; убрать из excludes, если lipo показал fat
        'psutil',
        'psutil._psutil_osx',
        'psutil._psosx',
        'psutil._psposix',
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
    name='Dubler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='universal2',
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
    name='Dubler',
)

app = BUNDLE(
    coll,
    name='Dubler.app',
    icon='icon.icns',
    bundle_identifier='com.filmbackup.dubler',
    info_plist={
        'CFBundleDisplayName': 'Dублёр',
        'CFBundleName': 'Dублёр',
        'CFBundleShortVersionString': app_version,
        'CFBundleVersion': app_version,
    },
)
