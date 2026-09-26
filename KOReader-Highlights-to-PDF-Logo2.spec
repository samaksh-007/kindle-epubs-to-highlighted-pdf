# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:/Users/RealS/Documents/Codex/2026-09-26/i-have-an-kindle-with-koreader/work/assets/kindle_highlights_logo.ico', '.'), ('C:/Users/RealS/Documents/Codex/2026-09-26/i-have-an-kindle-with-koreader/work/assets/kindle_highlights_logo.png', '.')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/Users/RealS/Documents/Codex/2026-09-26/i-have-an-kindle-with-koreader/work/koreader_highlight_pdf_app_tabs.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'pandas', 'matplotlib', 'pygame', 'cv2', 'scipy', 'IPython', 'jupyter', 'lxml'],
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
    name='KOReader-Highlights-to-PDF-Logo2',
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
    icon=['C:/Users/RealS/Documents/Codex/2026-09-26/i-have-an-kindle-with-koreader/work/assets/kindle_highlights_logo.ico'],
)
