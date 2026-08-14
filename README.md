<!-- Replace the banner below with your own image when ready. -->
<p align="center">
  <img src="https://placehold.co/900x260/0d0e12/e8a24a/png?text=RpiControl" alt="RpiControl" width="100%">
</p>

<h1 align="center">RpiControl</h1>

<p align="center">
  A tiny, dependency-free web app to <b>reboot</b>, <b>shut down</b>, and <b>update</b>
  your Raspberry Pi — from any phone, tablet, or computer on your network.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-e8a24a.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/dependencies-none-63d68f.svg" alt="No dependencies">
  <img src="https://img.shields.io/badge/platform-Raspberry%20Pi%20OS%20(Trixie)-c51a4a.svg" alt="Platform">
  <img src="https://img.shields.io/badge/PWA-installable-4fc8bd.svg" alt="Installable PWA">
</p>

---

## What is this?

**RpiControl** turns the boring "how do I safely power off my headless Raspberry Pi?"
problem into a single tap. It runs a tiny web server **on the Pi** that hosts a small,
good-looking web page. Open that page from any browser on your LAN and you get three
buttons — **Reboot**, **Shut down**, and **Run updates** — plus live status (uptime,
CPU temperature).

- 🪶 **Zero dependencies.** Pure Python 3 standard library. Nothing to `pip install` —
  even the app icons are generated in-process.
- 📱 **Mobile-first & installable.** Ships a web-app manifest, so you can **Add to Home
  Screen** and launch it fullscreen like a native app. Desktop gets a centered console card.
- 🔐 **Token protected.** Every power/update action requires a shared secret.
- 🛡️ **Safe by design.** Runs as an unprivileged `rpicontrol` user with a narrow `sudo`
  rule that allows *only* reboot, poweroff, and the two `apt-get` update commands.
- ↩️ **Undo window.** Power actions fire after a short delay (default 5s) so a misclick
  is recoverable.
- 📜 **Live update log.** "Run updates" streams `apt-get` output straight to the page.

> **Scope & intent:** RpiControl speaks plain HTTP and is built for a **trusted home LAN**.
> Don't expose it to the public internet — see [Security](#-security).

---

## Screenshots

<!-- These are placeholders. Drop your own screenshots in and update the paths. -->
<p align="center">
  <img src="https://placehold.co/360x740/0d0e12/e8a24a/png?text=Mobile+view" alt="RpiControl on mobile" width="280">
  &nbsp;&nbsp;&nbsp;
  <img src="https://placehold.co/460x430/0d0e12/e8a24a/png?text=Desktop+card" alt="RpiControl on desktop" width="440">
</p>

---

## Requirements

- A **Raspberry Pi** (built and tested on a Pi 4 running **Raspberry Pi OS Trixie, 64-bit**).
- **Python 3.9+** — already present on Raspberry Pi OS.
- The Pi and your phone/computer on the **same network**.

No other software, packages, or accounts required.

---

## 🚀 Quick start (install on the Raspberry Pi)

Clone the repo **on the Pi**, then run the installer:

```bash
# SSH
git clone git@github.com:SonapSav/RpiControl.git

# …or HTTPS
git clone https://github.com/SonapSav/RpiControl.git

cd RpiControl
sudo bash install.sh
```

The installer:

1. creates a locked-down `rpicontrol` system user,
2. installs the server to `/opt/rpicontrol`,
3. generates an access **token**,
4. adds a narrow `sudo` rule (reboot / poweroff / apt-get only),
5. starts a **systemd** service that auto-starts on boot.

When it finishes it prints the URL and token. Grab the token any time with:

```bash
sudo cat /etc/rpicontrol.env
```

Then open **`http://<pi-ip>:8080/`** from any device, paste the token, and you're in.

> 💡 Find the Pi's address with `hostname -I`, or reach it by name at
> `http://raspberrypi.local:8080/`.

---

## 📲 Add it to your home screen

The page is an installable PWA — pin it and it launches fullscreen with the amber power icon:

| Platform | How |
|----------|-----|
| **iPhone / iPad** (Safari) | Share → **Add to Home Screen** |
| **Android** (Chrome) | ⋮ menu → **Add to Home screen** |
| **Desktop** (Chrome / Edge) | Install icon in the address bar |

> ℹ️ **iOS** installs as a fullscreen app over plain HTTP on your LAN. **Android
> Chrome and desktop browsers only offer full PWA install (standalone launch)
> over a secure context** — i.e. HTTPS or `localhost`. Over a plain-HTTP LAN
> address you'll get a regular shortcut instead. To get the full install on
> Android, front RpiControl with HTTPS (e.g. a **Tailscale**/reverse-proxy URL).

---

## 💻 Use it / run it from your computer

RpiControl is a **web app**, so *using* it from **Windows, macOS, or Linux** needs nothing
but a browser pointed at the Pi. The steps below are only for **running the server locally**
(to try it, develop, or preview the UI) — power actions won't actually fire off-Pi, but the
GUI, API, and status endpoints all work.

<details>
<summary><b>Windows</b> (PowerShell)</summary>

```powershell
git clone https://github.com/SonapSav/RpiControl.git
cd RpiControl
$env:RPICONTROL_TOKEN = "test"
python server.py
```
Then browse to <http://localhost:8080/> and use the token `test`.
</details>

<details>
<summary><b>macOS</b></summary>

```bash
git clone https://github.com/SonapSav/RpiControl.git
cd RpiControl
RPICONTROL_TOKEN=test python3 server.py
```
Then browse to <http://localhost:8080/>.
</details>

<details>
<summary><b>Linux</b></summary>

```bash
git clone https://github.com/SonapSav/RpiControl.git
cd RpiControl
RPICONTROL_TOKEN=test python3 server.py
```
Then browse to <http://localhost:8080/>.
</details>

---

## ⚙️ Configuration

Set these in `/etc/rpicontrol.env` (or as environment variables when running by hand):

| Variable | Default | Meaning |
|----------|---------|---------|
| `RPICONTROL_TOKEN` | *(random)* | Secret required for reboot / shutdown / update. Set it to keep it stable across restarts. |
| `RPICONTROL_PORT` | `8080` | Port to listen on. |
| `RPICONTROL_HOST` | `0.0.0.0` | Interface to bind (`127.0.0.1` = local only). |
| `RPICONTROL_DELAY` | `5` | Seconds before a power action runs (the cancel window). |

After editing the file:

```bash
sudo systemctl restart rpicontrol
```

---

## 🔌 HTTP API

Endpoints marked ✅ require the header `X-Auth-Token: <token>`.

| Method | Path | Auth | Description |
|--------|------|:----:|-------------|
| `GET`  | `/` | — | The web GUI. |
| `GET`  | `/healthz` | — | Liveness check (`{"ok": true}`). |
| `GET`  | `/manifest.webmanifest` | — | PWA manifest. |
| `GET`  | `/icon-{180,192,512}.png` | — | Generated app icons. |
| `GET`  | `/api/status` | ✅ | Hostname, uptime, CPU temp, pending action. |
| `POST` | `/api/reboot` | ✅ | Schedule a reboot after `DELAY`s. |
| `POST` | `/api/shutdown` | ✅ | Schedule a shutdown after `DELAY`s. |
| `POST` | `/api/cancel` | ✅ | Cancel a pending power action. |
| `POST` | `/api/update` | ✅ | Start `apt-get update && apt-get upgrade -y`. |
| `GET`  | `/api/update/status` | ✅ | Update state + streamed log lines. |

```bash
curl -X POST -H "X-Auth-Token: YOURTOKEN" http://<pi-ip>:8080/api/reboot
```

---

## 🧰 Managing the service

```bash
systemctl status rpicontrol           # is it running?
journalctl -u rpicontrol -f           # live logs
sudo systemctl restart rpicontrol
sudo systemctl disable --now rpicontrol   # stop & don't start on boot
```

---

## 🛡️ Security

- **Plain HTTP, LAN only.** Intended for a trusted home network. For remote access, put it
  behind a VPN (e.g. **WireGuard / Tailscale**) or a reverse proxy with TLS + auth. Don't
  port-forward it to the internet.
- **Least privilege.** The `rpicontrol` user can run *only* `systemctl reboot|poweroff`,
  `shutdown -r|-h now`, `apt-get update`, and `apt-get upgrade -y` via `sudo` — nothing
  else. The sudoers allowlist is the privilege boundary.
- **Keep the token private.** `/etc/rpicontrol.env` is installed mode `0640` (root + rpicontrol).

---

## 🗑️ Uninstall

```bash
sudo systemctl disable --now rpicontrol
sudo rm -f /etc/systemd/system/rpicontrol.service /etc/sudoers.d/rpicontrol /etc/rpicontrol.env
sudo rm -rf /opt/rpicontrol
sudo userdel rpicontrol
sudo systemctl daemon-reload
```

---

## 🗂️ Project layout

| Path | Purpose |
|------|---------|
| `server.py` | The server **and** the embedded web GUI — the whole app. |
| `install.sh` | One-shot installer for the Pi. |
| `rpicontrol.service` | systemd unit (auto-start, restart on failure). |
| `rpicontrol-sudoers` | Narrow sudo permission for reboot / poweroff / apt-get. |
| `.githooks/commit-msg` | Enforces the commit-authorship standard (see below). |
| `docs/BRANDING.md` | The design system the UI is built from. |

---

## 🤝 Contributing

This repo pins a commit-authorship standard via a tracked git hook. After cloning, enable it:

```bash
git config core.hooksPath .githooks
```

Every commit is then automatically given a `Co-authored-by:` trailer — no need to add it by hand.

---

## 📄 License

RpiControl is released under the **MIT License** — **MIT © Panos Vasilopoulos**.
See [LICENSE](LICENSE) for the full text.

**What that means for you:**

- ✅ **Free for personal *and* commercial use.** You may use, copy, modify, merge, publish,
  distribute, sublicense, and even sell copies of the software.
- 📌 **Only requirement:** include the original copyright notice and the MIT permission notice
  (i.e. keep the `LICENSE` file) in all copies or substantial portions of the software.
- ⚠️ **No warranty.** The software is provided "as is", without warranty of any kind. You use
  it at your own risk.
