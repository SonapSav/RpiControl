# RpiControl

A tiny web GUI + server to **reboot**, **shut down**, or **run system updates**
on a Raspberry Pi 4 running Raspberry Pi OS (Trixie, 64-bit) from any browser on
your network — phone, laptop, tablet.

- **Zero dependencies.** Pure Python 3 standard library. Nothing to `pip install`
  (even the app icons are generated in-process).
- **One page.** The server hosts the GUI itself; open the Pi's address and click.
- **Mobile-first, installable.** A web-app manifest + icons let you **Add to Home
  Screen** and launch it fullscreen like a native app. Desktop gets a centered
  console card.
- **Token protected.** Reboot / shutdown / update require a shared secret.
- **Safe by design.** Runs as an unprivileged `rpicontrol` user with a narrow
  `sudo` rule that allows *only* reboot, poweroff, and the two apt-get update
  commands — nothing else.
- **Undo window.** Power actions fire after a short delay (default 5s) so a
  misclick can be cancelled from the same page.
- **Live update log.** "Run updates" streams `apt-get` output to the page.

## Files

| File | Purpose |
|------|---------|
| `server.py` | The server + embedded web GUI (the whole app). |
| `install.sh` | One-shot installer to run on the Pi. |
| `rpicontrol.service` | systemd unit (auto-start on boot, restart on failure). |
| `rpicontrol-sudoers` | Narrow sudo permission for reboot/poweroff only. |

## Install (on the Raspberry Pi)

Copy this folder to the Pi, then:

```bash
cd RpiControl
sudo bash install.sh
```

The installer prints the URL and generates an access token. Retrieve the token
any time with:

```bash
sudo cat /etc/rpicontrol.env
```

Then open `http://<pi-ip>:8080/` from any device on the LAN, paste the token,
and use the **Reboot** / **Shut down** / **Run updates** buttons.

> Tip: find the Pi's address with `hostname -I` on the Pi. You can also reach it
> by name, e.g. `http://raspberrypi.local:8080/`.

## Install it as an app (Add to Home Screen)

The page ships a web-app manifest, so you can pin it and launch it fullscreen:

- **iPhone/iPad (Safari):** Share → *Add to Home Screen*.
- **Android (Chrome):** ⋮ menu → *Install app* / *Add to Home screen*.
- **Desktop (Chrome/Edge):** the install icon in the address bar.

It opens without browser chrome, with the amber power icon — just like a native
app. (Browsers only offer install over `http://` on the local network or over
HTTPS; on a plain-HTTP LAN, iOS and Android still support *Add to Home Screen*.)

## Run updates

The **Run updates** button runs `apt-get update` followed by
`apt-get -y full-upgrade` as root (via the narrow sudo rule) and streams the
output to the page live. Kernel/firmware updates take effect after a reboot, so
a common flow is **Run updates → wait for "complete" → Reboot**. Don't close the
Pi's power while an update is running.

## Try it before installing

You can run the server directly (it just won't be able to actually power off
unless the sudo rule is in place):

```bash
RPICONTROL_TOKEN=test python3 server.py
```

Then browse to `http://localhost:8080/`.

## Configuration

Set these in `/etc/rpicontrol.env` (or as environment variables when running by
hand):

| Variable | Default | Meaning |
|----------|---------|---------|
| `RPICONTROL_TOKEN` | random | Secret required for reboot/shutdown. Set it to keep it stable. |
| `RPICONTROL_PORT` | `8080` | Port to listen on. |
| `RPICONTROL_HOST` | `0.0.0.0` | Interface to bind (`127.0.0.1` = local only). |
| `RPICONTROL_DELAY` | `5` | Seconds before the action runs (cancel window). |

After editing the env file:

```bash
sudo systemctl restart rpicontrol
```

## Manage the service

```bash
systemctl status rpicontrol      # is it running?
journalctl -u rpicontrol -f      # live logs
sudo systemctl restart rpicontrol
sudo systemctl disable --now rpicontrol   # stop & don't start on boot
```

## API (if you want to script it)

All action endpoints require the header `X-Auth-Token: <token>`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | no | The web GUI. |
| GET | `/api/status` | no | Hostname, uptime, CPU temp, pending action. |
| GET | `/manifest.webmanifest` | no | PWA manifest. |
| GET | `/icon-{180,192,512}.png` | no | Generated app icons. |
| POST | `/api/reboot` | yes | Schedule a reboot after `DELAY`s. |
| POST | `/api/shutdown` | yes | Schedule a shutdown after `DELAY`s. |
| POST | `/api/cancel` | yes | Cancel a pending action. |
| POST | `/api/update` | yes | Start `apt-get update && full-upgrade`. |
| GET | `/api/update/status` | yes | Update state + streamed log lines. |

Example:

```bash
curl -X POST -H "X-Auth-Token: YOURTOKEN" http://<pi-ip>:8080/api/reboot
```

## Security notes

- Traffic is plain HTTP — intended for a **trusted home LAN**. Do not expose it
  to the internet. If you need remote access, put it behind a VPN (e.g.
  WireGuard/Tailscale) or a reverse proxy with TLS + auth.
- The `rpicontrol` user can *only* run `systemctl reboot|poweroff`,
  `shutdown -r|-h now`, `apt-get update`, and `apt-get -y full-upgrade` via
  sudo. It cannot run arbitrary commands. Because apt must write across the
  filesystem, the systemd unit deliberately avoids `ProtectSystem`/`ProtectHome`
  sandboxing — the sudoers allowlist is the privilege boundary, not the sandbox.
- Keep `/etc/rpicontrol.env` readable only by root/rpicontrol (the installer
  sets mode `0640`).

## Uninstall

```bash
sudo systemctl disable --now rpicontrol
sudo rm -f /etc/systemd/system/rpicontrol.service /etc/sudoers.d/rpicontrol /etc/rpicontrol.env
sudo rm -rf /opt/rpicontrol
sudo userdel rpicontrol
sudo systemctl daemon-reload
```
