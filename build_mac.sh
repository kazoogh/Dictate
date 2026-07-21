#!/usr/bin/env bash
#
# Build Dictate Lite.app for macOS.
# Run this ON A MAC (PyInstaller cannot cross-compile from Windows/Linux).
#
#   chmod +x build_mac.sh
#   ./build_mac.sh
#
# Result: "dist/Dictate Lite.app"
#
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "==> Using Python: $("$PY" --version)"

echo "==> Installing build + runtime dependencies"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install pyinstaller
"$PY" -m pip install -r requirements-mac.txt

echo "==> Generating app icon (assets/dictate.icns)"
"$PY" scripts/generate_icns.py

echo "==> Building the .app bundle"
"$PY" -m PyInstaller DictateLite-mac.spec --noconfirm

# Ad-hoc code signature. This does NOT remove the first-launch Gatekeeper
# prompt (that needs an Apple Developer ID), but it makes the app stabler and
# avoids "damaged" errors after copying. Safe to run; ignore failures.
if command -v codesign >/dev/null 2>&1; then
  echo "==> Ad-hoc signing the app"
  codesign --force --deep --sign - "dist/Dictate Lite.app" || true
fi

echo
echo "==> Done. App is at: dist/Dictate Lite.app"
echo "    First launch: right-click the app -> Open (to get past Gatekeeper),"
echo "    then grant Microphone + Accessibility permissions when prompted."
echo "    Set your server URL / hotkey in the app's Settings screen."
