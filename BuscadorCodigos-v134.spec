# -*- mode: python ; coding: utf-8 -*-
#
# Build "onedir": el .exe queda junto a una carpeta _internal/ con todas las
# dependencias (numpy, pandas, playwright, etc). A diferencia del build
# "onefile" anterior, esto NO se autoextrae a una carpeta temporal en cada
# arranque, asi que abre mucho mas rapido y sin el pico de CPU/disco que
# generaba el driver de Playwright (~100 MB) al reextraerse cada vez.
#
# El instalador/actualizador automatico de la app (ver
# _extract_update_package en buscador_codigos.py) espera que cada release en
# GitHub incluya un asset .zip con el CONTENIDO de esta carpeta de salida
# (BuscadorCodigos-v134.exe + _internal/), ya sea zipeando la carpeta en si o
# zipeando su contenido directamente.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


datas = collect_data_files("playwright")
hiddenimports = collect_submodules("playwright")


a = Analysis(
    ['buscador_codigos.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name='BuscadorCodigos-v134',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BuscadorCodigos-v134',
)

