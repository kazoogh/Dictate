# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_dynamic_libs

_ICON = os.path.join(os.path.dirname(SPEC), "assets", "dictate.ico")
_TEMPLATES = os.path.join(os.path.dirname(SPEC), "clinical", "templates")
_PUNCTUATION = os.path.join(os.path.dirname(SPEC), "assets", "punctuation")
_VOCABULARY = os.path.join(os.path.dirname(SPEC), "assets", "vocabulary.default.json")

datas = []
binaries = []
datas += collect_data_files('faster_whisper')
datas += [( _TEMPLATES, 'clinical/templates' )]
if os.path.isdir(_PUNCTUATION):
    datas += [(_PUNCTUATION, 'assets/punctuation')]
if os.path.isfile(_VOCABULARY):
    datas += [(os.path.dirname(_VOCABULARY), 'assets')]
binaries += collect_dynamic_libs('onnxruntime')
binaries += collect_dynamic_libs('sherpa_onnx')
_DLL = os.path.join(os.path.dirname(SPEC), "dictate_native.dll")
if os.path.isfile(_DLL):
    binaries += [(_DLL, '.')]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'onnxruntime',
        'faster_whisper.vad',
        'ui_qt',
        'clinical_ui_qt',
        'icon_loader',
        'clinical',
        'clinical.service',
        'clinical.llm',
        'clinical.pdf_export',
        'transcript_cleanup',
        'punctuation_assets',
        'vocabulary',
        'paste_learner',
        'focus_text',
        'uiautomation',
        'native_bridge',
        'rapidfuzz',
        'sherpa_onnx',
        'PySide6',
    ],
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
    name='Dictate',
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
