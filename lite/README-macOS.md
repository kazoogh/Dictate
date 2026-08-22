# Dictate Lite on macOS

Dictate Lite is a Python + Qt (PySide6) app. Transcription happens on your
Dictate API server over HTTP, and the only Windows-specific piece was
`dictate_native.dll` (global hotkey, paste, audio) — which already had
pure-Python fallbacks. With a few cross-platform fixes, the same code now runs
on macOS. **None of these changes alter Windows behavior.**

There are two ways to run it on the Mac. Start with "Run from source" — it's the
fastest and avoids Apple's code-signing/Gatekeeper friction. Build the `.app`
later if you want a double-clickable icon.

---

## Before anything: the transcription server must be reachable

The app sends audio to your Dictate API server. The default in `config.json` is:

    http://10.159.0.31:8765

That is a **private IP**. The Mac will only reach it if it's on the same
network as the server or connected through your practice VPN. From a normal home
internet connection it will not be reachable, and dictation will fail with
"Dictate server unavailable." If your friend is remote, you'll need to either
put the Mac on the VPN or expose the server at an address he can reach, then set
that address in Settings (or `config.json` → `dictate_server_url`).

---

## Option A — Run from source (recommended, simplest)

Requires macOS with Python 3.10+ (`python3 --version`). If Python is missing,
install it from https://www.python.org/downloads/macos/ or via Homebrew
(`brew install python`).

    cd Dictate-Lite
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements-mac.txt
    python3 main.py

The first run will ask for permissions (see below).

## Option B — Build a double-clickable app

Must be done **on a Mac** (PyInstaller can't build a Mac app from Windows).

    cd Dictate-Lite
    chmod +x build_mac.sh
    ./build_mac.sh

The result is `dist/Dictate Lite.app`. Copy it to `/Applications` if you like.
Because it isn't signed with an Apple Developer ID, the first launch needs a
right-click → **Open** (once) to get past Gatekeeper. If macOS calls it
"damaged" after copying, clear the quarantine flag:

    xattr -dr com.apple.quarantine "/Applications/Dictate Lite.app"

---

## Permissions macOS will ask for

Dictation needs three things. Grant them in **System Settings → Privacy &
Security**. If you run from source, the app you grant is **Terminal** (or your
IDE); if you built the `.app`, it's **Dictate Lite** itself.

- **Microphone** — to record your voice. You'll get a prompt on first recording.
- **Accessibility** — so the app can paste the transcribed text (⌘V) into the
  focused field. Toggle the app on under Accessibility.
- **Input Monitoring** — so the global hotkey works while other apps are focused.
  Toggle the app on under Input Monitoring.

After enabling Accessibility / Input Monitoring you usually need to quit and
reopen the app once.

---

## The hotkey (important on Mac laptops)

Full desktop keyboards have a dedicated **End** key; most Mac **laptops do not**
(it's Fn+Right Arrow, which won't register as a global hotkey). Because of that,
the trigger key differs by platform:

- **Windows** defaults to the **End** key (`"hotkey": "<end>"`).
- **macOS** defaults to **Ctrl+Option+D** (`"hotkey": "<ctrl>+<alt>+d"`), which
  works on every Mac keyboard. This default applies to a fresh install (the
  built `.app` with no existing settings). If you run from source and the repo's
  `config.json` still says `<end>`, change it to a combo before first use.

Change it to whatever is convenient in the app's **Settings** screen, or edit
`config.json`. Single function keys like `"<f8>"` are unreliable on Mac (they're
consumed as media keys unless you enable "use F1, F2 as standard function keys"),
so a modifier combo such as `"<ctrl>+<alt>+d"` or `"<cmd>+<shift>+d"` is the
safest choice.

---

## Where settings and history live

- **Run from source:** `config.json` and `history.json` sit in the project
  folder (same as on Windows).
- **Built `.app`:** they live in
  `~/Library/Application Support/Dictate Lite/` (the app bundle itself is
  read-only). Edit `config.json` there if you prefer not to use the in-app
  Settings screen.

---

## What changed to make this cross-platform

- `native_bridge.py` — guarded the Windows-only `WINFUNCTYPE` import so the
  module loads on macOS and the app uses its Python fallbacks.
- `main.py` — paste now sends **⌘V on macOS** (Ctrl+V elsewhere); client name
  falls back to the machine hostname; a macOS `.app` stores its data in
  Application Support instead of inside the bundle.
- `startup.py` — "launch at login" now uses a macOS **LaunchAgent** (and is a
  safe no-op on unsupported systems) instead of crashing on the Windows-only
  registry code.
- Added `DictateLite-mac.spec`, `build_mac.sh`, `requirements-mac.txt`, and
  `scripts/generate_icns.py` for building the Mac app.

The Windows build (`build_lite.bat`, `DictateLite.spec`, the native DLL) is
untouched and still works exactly as before.
