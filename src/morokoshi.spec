# -*- mode: python ; coding: utf-8 -*-
import os

# App icon lives in docs/icons. Resolve from the spec file location so the build
# does not depend on the current working directory.
ICON_PATH = os.path.abspath(os.path.join(SPECPATH, '..', 'docs', 'icons', 'morokoshi.ico'))
if not os.path.isfile(ICON_PATH):
    raise SystemExit(f'Icon file not found: {ICON_PATH}')


a = Analysis(
    ['morokoshi.py'],
    pathex=[os.path.join(SPECPATH, 'nsf2mid_core')],   # NSF -> MIDI (copied from nsf2mid by tools/sync_nsf2mid.py)
    binaries=[],
    datas=[(ICON_PATH, '.')],
    hiddenimports=['nsf2mid'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='morokoshi',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON_PATH],
)
