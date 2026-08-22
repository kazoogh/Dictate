# Server mode — one machine transcribes for everyone

In server mode each workstation runs the Lite client, which records audio and
posts it to a Dictate API server you run. The workstations need nothing but the app; the server does all
the work. This is what you want for a team, for thin or ageing PCs, or when one
GPU should serve everybody.

## The shape of it

```
 workstation ──POST /transcribe──▶  Dictate API  ──▶ faster-whisper
 workstation ──POST /transcribe──▶  (your VM)     ──▶ cleanup (rules or OpenAI)
 workstation ──POST /transcribe──▶
```

The full walkthrough for a Proxmox LXC — user, venv, systemd, firewall — is in
[`server/DEPLOY-on-proxmox.md`](../server/DEPLOY-on-proxmox.md). Any Linux box
works the same way.

## Install the server

```bash
git clone https://github.com/<your-account>/Dictate.git
cd Dictate/server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then edit it
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8765
```

Check it:

```bash
curl http://localhost:8765/health
```

You want `"ok": true` and `"model_loaded": true`. The model loads at startup, so
the first request after a restart isn't the one that pays for it.

To run it as a service, `server/deploy/dictate-api.service` is a ready systemd
unit — it expects the code in `/opt/dictate-api` with its venv at
`/opt/dictate-api/.venv`.

## Configure it

Everything is environment variables, documented in `server/.env.example`. The
ones that matter:

| Variable | Default | Notes |
|---|---|---|
| `DICTATE_API_KEY` | *(empty)* | Empty means no auth. Set it if the server is reachable by anyone but you |
| `DICTATE_PORT` | `8765` | |
| `DICTATE_WHISPER_MODEL` | `small` | `.en` variant chosen automatically for English |
| `DICTATE_WHISPER_DEVICE` | `cpu` | `cuda` with an NVIDIA GPU |
| `DICTATE_WHISPER_COMPUTE_TYPE` | `int8` | `float16` on GPU |
| `DICTATE_WHISPER_BATCH_SIZE` | `8` | Parallel VAD chunks; the big CPU win |
| `DICTATE_CLEANUP_MODE` | `basic` | `openai` to polish transcripts with an LLM |
| `OPENAI_API_KEY` | *(empty)* | Only read when cleanup mode is `openai` |

`basic` cleanup keeps everything on your own hardware. `openai` sends the
transcript text (never the audio) to OpenAI — worth knowing before you turn it
on somewhere with confidentiality rules.

## Point Lite at it

In **Settings** on each workstation:

1. **Mode** → *Server*
2. **Server URL** → `http://<server-ip>:8765`
3. **Server API key** → whatever you set as `DICTATE_API_KEY`
4. **Test server connection** — it reports the service, whether the model is
   loaded, and how many transcriptions it has served

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Uptime, model state, temp-file count, free disk |
| `POST` | `/transcribe` | Multipart `file=` audio in, cleaned text out |
| `POST` | `/cleanup` | Rule-based cleanup of text you already have |
| `POST` | `/rewrite` | Cleanup with an explicit `basic` or `openai` mode |

All but `/health` honour the `x-api-key` header when a key is configured.

## Operational notes

- Uploads are capped (`DICTATE_MAX_UPLOAD_MB`, 50 by default) and deleted right
  after transcription; a background sweep clears anything stranded by a crash.
- Transcript text is never logged — the logs record durations and lengths.
- Keep the server on your LAN or behind a VPN. If it must face the internet,
  set an API key and put TLS in front of it.
- One model instance serves all requests, so a busy office queues rather than
  thrashing. If queueing shows up, a GPU helps far more than more CPU cores.

## If something goes wrong

**Workstations say "Dictate server unavailable"** — check the firewall on the
server (`ufw allow 8765/tcp`), then `curl /health` from a workstation.

**`model_loaded: false`** — the download failed or there wasn't enough RAM.
`journalctl -u dictate-api -n 100` will say which.

**macOS clients can't reach a LAN server** — that's the macOS Local Network
privacy gate. The app already works around it by routing through `curl`; make
sure you're on a build that includes `lite/server_client.py`'s curl path.
