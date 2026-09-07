# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH).parent

datas = [
    (str(root / "frontend"), "frontend"),
    (str(root / "client"), "client"),
    (str(root / "server"), "server"),
]

hiddenimports = [
    "main",
    "security",
    "store",
    "installer",
    "paths",
    "connection_manager",
    "models",
    "config",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "fastapi",
    "starlette",
    "pydantic",
    "jwt",
    "bcrypt",
    "pyotp",
    "qrcode",
    "PIL",
    "cryptography",
    "dotenv",
    "multipart",
    "anyio",
    "sniffio",
    "websockets",
    "httptools",
    "h11",
    "click",
]

a = Analysis(
    [str(root / "desktop" / "am_connect_app.py")],
    pathex=[str(root / "server"), str(root)],
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
    name="AM-CONNECT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
