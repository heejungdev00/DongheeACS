# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# aiohttp 관련 숨겨진 모듈 수집
datas_aiohttp, binaries_aiohttp, hiddenimports_aiohttp = collect_all('aiohttp')
datas_yaml, binaries_yaml, hiddenimports_yaml = collect_all('yaml')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries_aiohttp + binaries_yaml,
    datas=[
        ('static', 'static'),
        ('modules', 'modules'),
    ] + datas_aiohttp + datas_yaml,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'fastapi',
        'aiohttp',
        'aiosqlite',
        'pymodbus',
        'yaml',
        'multipart',
        'email.mime.multipart',
    ] + hiddenimports_aiohttp + hiddenimports_yaml,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    exclude_binaries=True,
    name='ANT_Interface_System',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ANT_Interface_System',
)