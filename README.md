# Dictate

Press a key, talk, and your words land in whatever app you're typing in —
already cleaned up. It's an open-source, self-hosted alternative to Wispr Flow,
built because paying per seat for dictation didn't make sense.

Nothing you say goes to a company that sells dictation. This repository holds
all three pieces, and which ones you use depends on how you want to run it.

```
dictate/
├── local/    Dictate — the full app, Whisper runs on your Windows PC
├── lite/     Dictate Lite — a thin client for Windows and macOS
└── server/   Dictate API — the transcription server Lite talks to
```

## Which one do I want?

**One Windows PC, everything on it → [`local/`](local/README.md).**
This is the original app and still the most capable one. Whisper runs on your
machine, and on top of transcription it does spoken punctuation with a local
ONNX model, custom vocabulary correction that learns from your edits, dictated
list formatting, and clinical session recording with AI answer sheets. Nothing
to deploy, no server, works offline.

**A team, or a Mac, or a PC too slow to run Whisper → [`lite/`](lite/) + [`server/`](server/).**
Deploy the API once on a VM or an old desktop with a GPU, then point every
workstation's Lite client at it. Workstations stay light — recording, pasting
and history only — and one machine does the transcribing for everyone. Lite is
also the only part that runs on macOS.

**A Mac, with no server →** `lite/` on its own. It can transcribe locally too
(see [docs/local-mode.md](docs/local-mode.md)), with a lighter feature set than
`local/`: no spoken punctuation, no vocabulary correction, no clinical
sessions.

| | `local/` | `lite/` + `server/` | `lite/` alone |
|---|---|---|---|
| Where audio is transcribed | Your PC | Your server | Your PC or Mac |
| Windows | Yes | Yes | Yes |
| macOS | No | Yes | Yes |
| Needs a network | No | Yes | No |
| Spoken punctuation, vocabulary, clinical | Yes | No | No |
| Setup effort | Install and run | Deploy the server once | Install and run |

Not sure? If you're on Windows and it's just you, start with `local/`.

## Getting started

**Local app** — [`local/README.md`](local/README.md)

```powershell
cd local
pip install -r requirements.txt
python main.py
```

**Server** — [`docs/server-mode.md`](docs/server-mode.md), with the full
Proxmox walkthrough in [`server/DEPLOY-on-proxmox.md`](server/DEPLOY-on-proxmox.md)

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env      # then edit it
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8765
```

**Lite client** — [`docs/local-mode.md`](docs/local-mode.md) to run it
standalone, [`docs/server-mode.md`](docs/server-mode.md) to point it at a
server, [`lite/README-macOS.md`](lite/README-macOS.md) for Macs

```powershell
cd lite
pip install -r requirements-local.txt   # or requirements-lite.txt for server-only
python main.py
```

## How dictation works

1. The hotkey starts recording from your default microphone (16 kHz mono WAV in
   your temp directory).
2. Pressing it again stops the recording and transcribes — with Whisper in the
   app (`local/`, or `lite/` in local mode) or by posting the file to your
   server (`lite/` in server mode).
3. The transcript is cleaned up: fillers dropped, stutters collapsed,
   punctuation and casing fixed. `local/` adds spoken punctuation, vocabulary
   correction and list formatting on top.
4. The result goes on the clipboard, is pasted into the focused window, and is
   saved to your local history.

The audio file is deleted as soon as it's transcribed. Transcribed text is
never written to a log.

## Choosing a Whisper model

`base` (or `base.en` for English) is the default because it's where accuracy
stops being annoying and speed is still instant on an ordinary CPU.

| Model | Size | Feels like | Use when |
|---|---|---|---|
| `tiny.en` | ~75 MB | Instant, makes mistakes | Old hardware, short commands |
| `base.en` | ~150 MB | Fast, good enough | The default for most people |
| `small.en` | ~500 MB | Noticeably better, still quick | You dictate long passages |
| `medium.en` | ~1.5 GB | Better again, slower on CPU | You have cores to spare |
| `large-v3-turbo` | ~1.6 GB | Best, needs a GPU to feel fast | A server with CUDA |

English-only (`.en`) builds are both faster and more accurate than the
multilingual ones.

## A note on the two apps

`local/` and `lite/` are two forks of the same app that grew apart: `local/`
went deep on transcript quality and clinical work, `lite/` went thin so it
could run on weak machines and picked up macOS support along the way. They
share their lineage — and a lot of `ui_qt.py` — but they are not the same
program, and merging them into one is a project of its own rather than a
rename.

## History

This repository combines three that used to be separate — the local app, the
Lite client and the API — with every commit preserved. `git log --follow` on
any file works across the move into `local/`.

## License

MIT. See [LICENSE](LICENSE).
