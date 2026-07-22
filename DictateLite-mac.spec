# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the macOS build of Dictate Lite.
# Produces "dist/Dictate Lite.app". Build with:  ./build_mac.sh
import os

_ICON = os.path.join(os.path.dirname(SPEC), "assets", "dictate.icns")

# Bundle the assets folder (icons, etc.) if present. No native DLL on macOS —
# the app uses its pure-Python audio/hotkey/paste fallbacks.
datas = []
_ASSETS = os.path.join(os.path.dirname(SPEC), "assets")
if os.path.isdir(_ASSETS):
    datas += [(_ASSETS, "assets")]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'ui_qt',
        'icon_loader',
        'audio_devices',
        'native_bridge',
        'mac_hotkey',
        'startup',
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
    [],
    exclude_binaries=True,
    name='Dictate Lite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,          # host arch; set 'universal2' for a fat binary
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Dictate Lite',
)

app = BUNDLE(
    coll,
    name='Dictate Lite.app',
    icon=_ICON,
    bundle_identifier='care.franklindental.dictatelite',
    info_plist={
        'CFBundleName': 'Dictate Lite',
        'CFBundleDisplayName': 'Dictate Lite',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,
        # Required so macOS will allow microphone access for dictation.
        'NSMicrophoneUsageDescription':
            'Dictate Lite records your voice so it can be transcribed to text.',
        # Keep a normal Dock icon (the app has a main window). Set to True only
        # if you want a menu-bar-only app with no Dock presence.
        'LSUIElement': False,
    },
)
