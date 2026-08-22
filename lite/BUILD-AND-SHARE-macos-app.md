# Build "Dictate Lite.app" in the cloud and email it to your friend

You can't build a Mac app on Windows. This uses **GitHub Actions** — free Mac
build machines — to produce a ready-to-run `Dictate Lite.app` for you to
download and email. No Mac needed on your end.

One-time setup, then every future build is one command.

---

## 1. Put the workflow file in place

The build recipe is `build-macos.yml`. It must live at exactly this path inside
the repo:

    Dictate-Lite/.github/workflows/build-macos.yml

From the `Dictate-Lite` folder in a terminal (PowerShell or Git Bash):

    mkdir -p .github/workflows

Then move the `build-macos.yml` file you were sent into that
`.github/workflows/` folder. (It couldn't be placed automatically — GitHub
workflow files are protected from remote writes.)

---

## 2. Put the repo on GitHub (one time)

You need a free GitHub account and git installed. Easiest with the GitHub CLI
(`gh`), from inside the `Dictate-Lite` folder:

    git add .
    git commit -m "Add macOS CI build"
    gh auth login                      # follow the prompts, once
    gh repo create dictate-lite --private --source . --push

No `gh`? Do it on the web instead: create a new **private** repo on github.com,
then:

    git remote add origin https://github.com/<your-username>/dictate-lite.git
    git add .
    git commit -m "Add macOS CI build"
    git branch -M main
    git push -u origin main

> Private is fine — GitHub Actions works on private repos (free tier includes
> plenty of macOS build minutes for occasional builds).

---

## 3. Build it

**Recommended — tag a version (this also creates a shareable download):**

    git tag v1.0.0
    git push origin v1.0.0

That kicks off the build. When it finishes (~5–10 min), go to your repo's
**Releases** page — there'll be a `v1.0.0` release with two files attached:

- `DictateLite-apple-silicon.zip`  — for M1/M2/M3/M4 Macs
- `DictateLite-intel.zip`          — for older Intel Macs

**Or, quick test build with no tag:** repo → **Actions** tab → **Build macOS
app** → **Run workflow**. Download the result from that run's **Artifacts**
section (you'll unzip one extra layer this way — the Release route above is
cleaner for sharing).

---

## 4. Pick the right file for your friend

Which Mac does he have? On his Mac: **Apple menu →  About This Mac**.

- "Chip: Apple M…"  → send **DictateLite-apple-silicon.zip**
- "Processor: Intel…" → send **DictateLite-intel.zip**

Most Macs from 2020 onward are Apple Silicon. If you're unsure, send both.

---

## 5. Email it and tell him how to open it first time

Email the `.zip`. He double-clicks it to unzip, and gets **Dictate Lite.app**.

Because the app isn't signed with a paid Apple Developer ID, macOS will block a
**double-click** the first time. Tell him to do this **once**:

> **Right-click** (or Control-click) Dictate Lite.app → **Open** → in the dialog,
> click **Open** again.

After that first time, it opens normally by double-click. If macOS insists the
app is "damaged" (can happen with emailed apps), he can clear the download flag
in Terminal:

    xattr -dr com.apple.quarantine "/path/to/Dictate Lite.app"

Then he grants **Microphone**, **Accessibility**, and **Input Monitoring** the
first time (System Settings → Privacy & Security — see `INSTALL-on-your-Mac.md`),
and dictates with **Ctrl+Option+D**. Since he's on your network, it'll reach the
server with no extra config.

---

## Future builds

Change the code, then bump the tag:

    git add -A && git commit -m "what changed"
    git tag v1.0.1
    git push && git push origin v1.0.1

A fresh Release with new zips appears a few minutes later.

---

## Notes

- The build is **ad-hoc signed** (the `build_mac.sh` script does this). That's
  what makes the right-click-Open route work. Removing the first-launch prompt
  entirely would need a paid Apple Developer ID ($99/yr) + notarization — nice to
  have, not required.
- The emailed app already points at your server (`http://10.159.0.31:8765`) and
  defaults to the Ctrl+Option+D hotkey, so there's nothing for him to configure
  as long as he's on the practice network.
