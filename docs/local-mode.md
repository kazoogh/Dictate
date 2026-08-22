# Running Dictate Lite without a server

Lite normally posts audio to a Dictate API server. In local mode it transcribes
with Whisper in its own process instead — no server, no account, no internet
after the first model download.

**On Windows, read [`local/`](../local/README.md) first.** The local app does
everything described here and adds spoken punctuation, vocabulary correction
and clinical sessions. Lite's local mode exists for the cases `local/` can't
cover: macOS, and machines where you want the thinnest possible install.

## What you need

- macOS 12+, or Windows 10/11
- Python 3.10–3.12 (only if you run from source; a packaged build ships its own)
- About 1 GB free disk for the app and a small model
- A working microphone

A GPU is optional. `base.en` on a mid-range CPU transcribes a 15-second
dictation in roughly a second.

## Install from source

```bash
git clone https://github.com/<your-account>/Dictate.git
cd Dictate/lite
python -m venv .venv
.venv\Scripts\activate            # macOS: source .venv/bin/activate
pip install -r requirements-local.txt
python main.py
```

`requirements-local.txt` is the app's own dependencies plus `faster-whisper`,
which is what actually runs the model.

## Turn it on

Open **Settings** in the dashboard:

1. **Mode** → *Local — Whisper runs on this computer*
2. **Local model** → `base.en` to start with
3. **Run on** → CPU, unless you have an NVIDIA card and CUDA set up
4. **Test local engine** — the first run downloads the weights (a minute or two
   on a normal connection) and reports back when the model is loaded

Then close Settings and press your hotkey. The default is **End** on Windows
and **Ctrl+Alt+D** on macOS.

The model stays in memory while the app runs, so only the first dictation after
launch waits for loading — and the app starts that load in the background as
soon as it opens.

## Cleanup: rules or a local LLM

**Basic** (default) is a set of rules that runs instantly: fillers removed,
stuttered words collapsed, spacing, casing and end punctuation fixed. It never
changes your wording.

**Ollama** hands the transcript to a language model running on your machine and
asks it to tidy the writing — better paragraphing, cleaner sentences, false
starts removed. It adds a second or two and it can rephrase, so use it when you
want polished prose rather than a faithful transcript.

To use it:

```bash
ollama pull llama3.2      # or any chat model you like
ollama serve              # usually already running
```

Then in **Settings → Cleanup**, choose *Ollama* and enter the model name.
Dictate talks to `http://127.0.0.1:11434` by default. If Ollama isn't running
when you dictate, the app quietly falls back to the basic rules rather than
losing your text.

## Where your data lives

| What | Where |
|---|---|
| Recorded audio | Your temp directory, deleted right after transcription |
| Model weights | `~/.cache/huggingface/hub` (Windows: `%USERPROFILE%\.cache\huggingface\hub`) |
| History and settings | Next to the app; on a packaged macOS build, `~/Library/Application Support/Dictate Lite` |

Nothing is uploaded. Transcribed text is never written to a log file.

## Tuning

Settings covers the common knobs; `config.json` has the rest:

| Key | Default | What it does |
|---|---|---|
| `local_model` | `base.en` | Any faster-whisper model name |
| `local_device` | `cpu` | `cuda` for an NVIDIA GPU |
| `local_compute_type` | `int8` | `float16` on GPU |
| `local_beam_size` | `1` | Greedy. `5` is slower and slightly more accurate |
| `local_batch_size` | `8` | Parallel VAD chunks. `1` disables batching |
| `local_cpu_threads` | `0` | `0` uses every physical core |

## If something goes wrong

**"Local mode needs faster-whisper"** — you're in the wrong environment or
installed `requirements-lite.txt` instead of `requirements-local.txt`.

**First dictation hangs** — the model is still downloading. Watch the status
line; **Test local engine** in Settings shows the same progress.

**Transcription is slow** — drop to a smaller model, keep `local_beam_size` at
1, and make sure `local_batch_size` is above 1. If it's still slow, the machine
is probably a better fit for [server mode](server-mode.md).

**A packaged .exe or .app ignores local mode** — `faster-whisper` is imported
lazily so that server-mode builds stay small, which means PyInstaller doesn't
bundle it by default. Add `hiddenimports=["faster_whisper"]` to
`DictateLite.spec` (or `DictateLite-mac.spec`) and build in an environment
where it's installed.

**You want punctuation and vocabulary correction too** — that's `local/`, on
Windows. Lite's cleanup is deliberately lighter.
