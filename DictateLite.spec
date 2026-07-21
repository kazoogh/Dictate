# -*- mode: python ; coding: utf-8 -*-
import os

_ICON = os.path.join(os.path.dirname(SPEC), "assets", "dictate.ico")

datas = []
binaries = []
_DLL = os.path.join(os.path.dirname(SPEC), "dictate_native.dll")
if os.path.isfile(_DLL):
    binaries += [(_DLL, '.')]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'ui_qt',
        'icon_loader',
        'audio_devices',
        'native_bridge',
        'startup_ui',
        'server_client',
        'PySide6',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'faster_whisper',
        'ctranslate2',
        'onnxruntime',
        'sherpa_onnx',
        'openai',
        'torch',
        'scipy',
        'rapidfuzz',
        'uiautomation',
    ],
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
    name='Dictate Lite',
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
    icon=_ICON,
)
