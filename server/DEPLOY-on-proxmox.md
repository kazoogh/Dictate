# Deploy the (faster) Dictate API on Proxmox — step by step

Follow this top to bottom. Every line in a grey box is meant to be
**copied and pasted** exactly. Placeholders in CAPS (like `YOURLOGIN`) are the
only things you change.

There are two parts:

- **Part 1** puts the code on GitHub (on your Windows PC). ~1 minute.
- **Part 2** updates the server so it runs the faster version. ~10 minutes.

---

# PART 1 — Put dictate-api on GitHub (Windows PC)

1. Save the two files I sent — `Run-Dictate-API-GitHub-Setup.bat` and
   `setup-dictate-api-github.ps1` — into the **same folder** (your Desktop).
2. **Double-click** `Run-Dictate-API-GitHub-Setup.bat`.
3. Wait for it to say **DONE**. It prints two things you'll want:
   - your repo link, e.g. `https://github.com/YOURNAME/dictate-api`
   - a **yellow clone URL** that looks like
     `https://ghp_xxx@github.com/YOURNAME/dictate-api.git`
4. **Copy that whole yellow URL** and keep it handy — you paste it in Part 2.
   (It has your token in it, which lets the server download a private repo.)

That's the code on GitHub. Now the server.

---

# PART 2 — Update the server

## 2A. Open a terminal INTO the server

1. On your Windows PC, click the **Start** button (bottom-left corner).
2. Type the word **PowerShell**.
3. Click **Windows PowerShell** in the results. A blue window opens.
4. In that blue window, paste this and press **Enter**
   (replace `YOURLOGIN` with the username you use for the server — often `root`):

   ```
   ssh YOURLOGIN@192.168.1.10
   ```

5. The first time it may say *"Are you sure you want to continue connecting"* —
   type **yes** and press Enter.
6. Type your server password when asked (you won't see the characters — that's
   normal), press **Enter**.

You are now "on" the server. Every command below is pasted into **this same
blue window**.

> Prefer the Proxmox web page? Log into Proxmox in your browser, click the VM or
> container that runs Dictate, click **>_ Console** (or **Shell**), and use that
> instead. The commands are identical.

## 2B. Make sure the tools we need are installed

Paste this (it's safe to run even if they're already installed):

```
sudo apt-get update && sudo apt-get install -y git python3-venv
```

## 2C. Stop the running service and back up the current copy

Paste these **one block at a time** (press Enter after each):

```
sudo systemctl stop dictate-api
```

```
sudo mv /opt/dictate-api /opt/dictate-api.old
```

Your old code (with your `.env` and its API keys) is now safely at
`/opt/dictate-api.old`. We'll copy the keys back in a moment.

## 2D. Download the new code from GitHub

Paste this, but **replace the URL** with the **yellow clone URL** you copied in
Part 1 (keep the `/opt/dictate-api` at the end):

```
sudo git clone https://ghp_xxx@github.com/YOURNAME/dictate-api.git /opt/dictate-api
```

## 2E. Put your settings and keys back

This copies your old `.env` (with your API keys) into the new code:

```
sudo cp /opt/dictate-api.old/.env /opt/dictate-api/.env
```

Reuse the Python environment you already had (so you don't re-download
everything):

```
sudo mv /opt/dictate-api.old/.venv /opt/dictate-api/.venv
```

Make the `dictate` user own it all:

```
sudo chown -R dictate:dictate /opt/dictate-api
```

## 2F. Install the one new requirement (batched Whisper)

```
sudo -u dictate /opt/dictate-api/.venv/bin/pip install -r /opt/dictate-api/requirements.txt
```

This upgrades `faster-whisper` to the version that does the parallel (batched)
transcription. Give it a minute.

## 2G. Turn on the speed settings

First, check whether the server has a usable GPU. Paste:

```
nvidia-smi
```

- If you see a **table with a GPU** in it → you have a GPU. Use the **GPU block**
  below.
- If you see **"command not found"** or an error → no GPU. Use the **CPU block**
  below (this is the common case).

Open the settings file:

```
sudo nano /opt/dictate-api/.env
```

Use the arrow keys to find the lines that start with `DICTATE_WHISPER_`. Make
that section look **exactly** like one of these (leave every other line,
especially your `DICTATE_API_KEY` and `OPENAI_API_KEY`, untouched):

**CPU block (no GPU):**

```
DICTATE_WHISPER_MODEL=small
DICTATE_WHISPER_DEVICE=cpu
DICTATE_WHISPER_COMPUTE_TYPE=int8
DICTATE_WHISPER_LANGUAGE=en
DICTATE_WHISPER_BEAM_SIZE=1
DICTATE_WHISPER_BATCH_SIZE=8
```

**GPU block (only if nvidia-smi showed a GPU):**

```
DICTATE_WHISPER_MODEL=large-v3-turbo
DICTATE_WHISPER_DEVICE=cuda
DICTATE_WHISPER_COMPUTE_TYPE=float16
DICTATE_WHISPER_LANGUAGE=en
DICTATE_WHISPER_BEAM_SIZE=1
DICTATE_WHISPER_BATCH_SIZE=16
```

To save in nano: press **Ctrl+O**, press **Enter**, then **Ctrl+X** to exit.

## 2H. Start it back up

```
sudo systemctl start dictate-api
```

Check it's healthy (should print `"ok": true`):

```
curl http://localhost:8765/health
```

If you see `ok` and a model name, you're done. If it looks stuck, watch the log
live with:

```
sudo journalctl -u dictate-api -f
```

(press **Ctrl+C** to stop watching.)

## 2I. Test the speed

Do a real dictation from the Windows app. In the app, go to
**Settings → Test server connection** — it shows the model and the last
transcription time. Or on the server, the log line now reads
`whisper=X.XXs total=Y.YYs`, so you can see exactly how fast it got.

---

## If something goes wrong (rollback)

Put the old version back instantly:

```
sudo systemctl stop dictate-api
sudo rm -rf /opt/dictate-api
sudo mv /opt/dictate-api.old /opt/dictate-api
sudo systemctl start dictate-api
```

## When everything works

- Delete `/opt/dictate-api.old` to reclaim space:
  ```
  sudo rm -rf /opt/dictate-api.old
  ```
- On your Windows PC, delete the two setup scripts and **revoke the GitHub
  token** (GitHub → Settings → Developer settings → Personal access tokens).
- Future updates are now easy: on the server, run
  `cd /opt/dictate-api && sudo git pull`, then repeat steps 2F–2H.

---

### GPU note

If you chose the GPU block and it fails to start with an error about `cudnn`,
`cublas`, or `libcudart`, the CUDA libraries aren't installed. Paste me that
error and I'll give you the exact install commands — it's a known, fixable step.
