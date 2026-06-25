# Dictate

A local dictation app for Windows with two modes:

- **Quick Dictate** — press a global hotkey, speak, paste into any text box (Wispr Flow style)
- **Clinical Session** — record full appointments (up to 2 hours), transcribe locally, generate AI answer sheets from clinical note templates

No cloud transcription. OpenAI is used **only** for clinical answer sheet generation.

## Requirements

- Windows 10+
- Python 3.10+
- A working microphone
- OpenAI API key (clinical sessions only)

**Optional — native shell (`dictate_native.dll`):**

- Visual Studio Build Tools 2022 with **Desktop development with C++** (MSVC + Windows SDK)
- CMake is optional; `build_native.bat` can compile with MSVC directly

Without the native DLL, Dictate uses Python fallbacks (`pynput`, `pyautogui`, `sounddevice`) and works normally.

## Install

```powershell
cd C:\Users\INTERN4\Dictate
pip install -r requirements.txt
```

**First launch** downloads the faster-whisper model (~150 MB for `base`).

## Run

```powershell
python main.py
```

The dashboard uses **PySide6 (Qt)**. Clinical logic, templates, vocabulary, punctuation cleanup, and Whisper remain in Python.

## Native shell (recommended)

The native DLL provides Win32 global hotkeys, clipboard paste, and low-latency mic capture for Quick Dictate.

### Build

```powershell
.\build_native.bat
```

On success you should see `dictate_native.dll` in the project folder. The app footer shows **Native shell** when the DLL is loaded.

### If the build fails

**"No Visual Studio C++ compiler was found"** — Build Tools may be installed without the C++ workload. Run:

```powershell
.\install_cpp_workload.bat
```

Approve the UAC prompt, wait for the installer to finish, then close and reopen PowerShell and run `.\build_native.bat` again.

**Manual fix:** open **Visual Studio Installer** → **Modify** on Build Tools 2022 → check **Desktop development with C++** → **Modify**.

**Skip the native build** — `python main.py` works with Python fallbacks.

## Quick Dictate

1. Click into any text box.
2. Press **End** to start recording.
3. Speak.
4. Press **End** again — text is pasted and saved to history.

Works from the system tray even when the window is closed.

Optional post-processing (Settings):

- **Dictation cleanup** — removes filler words and adds punctuation (local sherpa-onnx model, ~7 MB)
- **Custom vocabulary** — corrects company names, software, file types via `vocabulary.json` (fuzzy matching with rapidfuzz)
- **Learn vocabulary when I fix pasted text** — on your next dictate, compares the focused field to what was last pasted; single-word fixes (e.g. John → Johnny) are saved as `term` + `alias` in `vocabulary.json`

## Clinical Session

1. Open Dictate → **Clinical Session** in the sidebar.
2. Choose procedure type (Extraction, Filling, Crown, etc.).
3. Click **Start Recording** (or use **Ctrl+Alt+R** to stop).
4. When the appointment ends, click **Stop & Generate Answer Sheet**.
5. Review the answer sheet, copy fields, or open the PDF.
6. Mark **Entered in Dentrix** when done.

- Transcription: **local** (faster-whisper)
- Template matching: **OpenAI** (configure API key in Settings)
- Raw audio is deleted after processing; transcripts and answer sheets are retained per your retention policy.

Clinical data is stored in `clinical_data/` next to the app. Dentrix Ascend templates are seeded on first run (Extraction and Filling v3.0).

## Settings

| Key | Default | Description |
|-----|---------|-------------|
| `hotkey` | `<end>` | Quick dictate hotkey |
| `clinical_hotkey` | `<ctrl>+<alt>+r` | Stop clinical recording |
| `model_size` | `base` | Whisper model (`tiny`, `base`, `small`, `medium`, `large-v3`) |
| `dictation_cleanup` | `true` | Filler removal + punctuation (local) |
| `vocabulary_correction` | `true` | Apply custom vocabulary corrections |
| `vocabulary_auto_learn` | `true` | Learn from edits to pasted text on next hotkey |
| `vocabulary_fuzzy_threshold` | `82` | Fuzzy match sensitivity (0–100) |
| `openai_model` | `gpt-4o-mini` | OpenAI model for answer sheets |
| `clinical_max_duration_hours` | `2` | Max appointment length |
| `clinical_retention_days` | `7` | Session retention (`1`, `7`, `30`, `manual`) |
| `restore_clipboard_after_paste` | `false` | Restore clipboard after quick dictate paste |

Edit `vocabulary.json` from Settings → **Edit vocabulary.json**, or copy defaults from `assets/vocabulary.default.json`.

## Build executable

```powershell
.\build.bat
```

This installs dependencies, builds the native DLL (if MSVC is available), downloads the punctuation model, and runs PyInstaller.

Output: `dist\Dictate.exe` (bundles `dictate_native.dll` when present).

## Architecture

```
PySide6 UI (ui_qt.py, clinical_ui_qt.py)
        ↓
Python: Whisper, vocabulary, cleanup, clinical/OpenAI
        ↓
dictate_native.dll (optional): hotkeys, paste, quick-dictate audio
```

| Component | Location |
|-----------|----------|
| App entry | `main.py` |
| Native bridge | `native_bridge.py` |
| C++ sources | `native/` |
| Transcript cleanup | `transcript_cleanup.py` |
| Custom vocabulary | `vocabulary.py` |
| Clinical backend | `clinical/` |

## License

MIT
