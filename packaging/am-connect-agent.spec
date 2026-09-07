# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH).parent

datas = [
    (str(root / "client"), "client"),
]

hiddenimports = [
    "agent",
    "aiohttp",
    "psutil",
    "mss",
    "PIL",
    "dotenv",
    "pynput",
    "pynput.mouse",
    "pynput.keyboard",
]

a = Analysis(
    [str(root / "desktop" / "am_connect_agent.py")],
    pathex=[str(root / "client"), str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AM-CONNECT-Agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)
