# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules

datas = [
    ('agentos/desktop/static', 'agentos/desktop/static'),
    ('agentos.yaml', '.'),
]

# Only include optional local persona markdown if present locally
if os.path.isfile('agentos/persona/SOUL.md'):
    datas.append(('agentos/persona/SOUL.md', 'agentos/persona'))

hiddenimports = [
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.http.h11_impl',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.protocols.websockets.wsproto_impl',
    'uvicorn.lifespans',
    'uvicorn.lifespans.auto',
    'uvicorn.lifespans.on',
    'fastapi',
    'fastapi.responses',
    'fastapi.staticfiles',
    'starlette',
    'starlette.responses',
    'starlette.staticfiles',
    'starlette.middleware',
    'starlette.middleware.cors',
    'pydantic',
    'webview',
    'webview.platforms.winforms',
    'clr',
    'pythonnet',
    'yaml',
    'rich',
    'sqlite3',
    'asyncio',
]
hiddenimports += collect_submodules('agentos')

a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'torch', 'pandas'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AgentOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
