# -*- mode: python ; coding: utf-8 -*-
"""
MeetRec — PyInstaller spec file
Genera ejecutable standalone para Windows y Linux.
"""
import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Hidden imports necesarios
hiddenimports = (
    collect_submodules("notebooklm")
    + collect_submodules("httpx")
    + collect_submodules("soundcard")
    + collect_submodules("soundfile")
    + [
        "numpy",
        "cffi",
        "asyncio",
        "json",
        "subprocess",
        "playwright",
        "playwright.sync_api",
        "playwright._impl",
        "playwright._impl._api_types",
    ]
)

a = Analysis(
    ["src/app.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "PIL", "cv2", "torch", "tensorflow"],
    noarchive=False,
    optimize=0,
)

# Si hay ffmpeg bundled en assets/, agregarlo
ffmpeg_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
ffmpeg_bundled = Path("assets") / ffmpeg_name
if ffmpeg_bundled.exists():
    a.datas += [(f"ffmpeg/{ffmpeg_name}", str(ffmpeg_bundled), "DATA")]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MeetRec",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Sin ventana de consola
    icon="assets/icon.ico" if os.path.exists("assets/icon.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MeetRec",
)
