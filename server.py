#!/usr/bin/env python3
"""RpiControl - a tiny, dependency-free web server to control a Raspberry Pi.

Serves a small web GUI with Reboot / Shut down / Run updates buttons and exposes
a JSON API guarded by a shared token. Uses only the Python standard library, so
it runs on a stock Raspberry Pi OS (Trixie, 64-bit) with no pip installs.

Configuration (all optional, via environment variables):
    RPICONTROL_TOKEN   Shared secret required for reboot/shutdown/update actions
                       and for reading status. If unset, a random token is
                       generated and printed on start.
    RPICONTROL_PORT    TCP port to listen on (default: 8080).
    RPICONTROL_HOST    Interface to bind (default: 0.0.0.0 = all interfaces).
    RPICONTROL_DELAY   Seconds to wait before a power action runs (default: 5).
                       Gives the browser time to show a confirmation and lets
                       you cancel via /api/cancel.
"""

from __future__ import annotations

import hmac
import json
import math
import os
import secrets
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

PORT = int(os.environ.get("RPICONTROL_PORT", "8080"))
HOST = os.environ.get("RPICONTROL_HOST", "0.0.0.0")
DELAY = max(0, int(os.environ.get("RPICONTROL_DELAY", "5")))
TOKEN = os.environ.get("RPICONTROL_TOKEN") or secrets.token_urlsafe(18)
TOKEN_WAS_GENERATED = "RPICONTROL_TOKEN" not in os.environ

# IMPORTANT: these absolute paths MUST stay in lock-step with the command paths
# allowed in rpicontrol-sudoers. sudo matches an allowed command by its exact
# path, so we hardcode them here rather than resolving via PATH/shutil.which() -
# a divergent path (e.g. /bin/systemctl vs /usr/bin/systemctl) would make sudo
# deny the command. If you change one file, change the other.
SUDO = "/usr/bin/sudo"
SYSTEMCTL = "/usr/bin/systemctl"
SHUTDOWN = "/sbin/shutdown"
APT = "/usr/bin/apt-get"

# A pending action is stored here so it can be cancelled before it fires.
_pending_lock = threading.Lock()
_pending_timer: threading.Timer | None = None
_pending_action: str | None = None


# --------------------------------------------------------------------------- #
# System actions
# --------------------------------------------------------------------------- #

def _run_power_action(action: str) -> None:
    """Actually reboot or power off the machine."""
    verb = "reboot" if action == "reboot" else "poweroff"
    # Prefer systemctl; fall back to shutdown(8). sudo is used so the service
    # can run as an unprivileged user (see rpicontrol-sudoers).
    cmds = [
        [SUDO, "-n", SYSTEMCTL, verb],
        [SUDO, "-n", SHUTDOWN, "-r" if action == "reboot" else "-h", "now"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, timeout=30)
            return
        except (subprocess.SubprocessError, OSError) as exc:
            sys.stderr.write(f"[rpicontrol] command failed {cmd}: {exc}\n")
    sys.stderr.write("[rpicontrol] all power commands failed\n")


def schedule_action(action: str) -> dict:
    """Schedule reboot/shutdown after DELAY seconds. Returns a status dict."""
    global _pending_timer, _pending_action
    with _pending_lock:
        if _pending_timer is not None:
            return {"ok": False, "error": "an action is already pending",
                    "pending": _pending_action}
        _pending_action = action

        def fire() -> None:
            global _pending_timer, _pending_action
            with _pending_lock:
                _pending_timer = None
                _pending_action = None
            _run_power_action(action)

        _pending_timer = threading.Timer(DELAY, fire)
        _pending_timer.daemon = True
        _pending_timer.start()
        return {"ok": True, "action": action, "delay": DELAY}


def cancel_action() -> dict:
    global _pending_timer, _pending_action
    with _pending_lock:
        if _pending_timer is None:
            return {"ok": False, "error": "nothing to cancel"}
        _pending_timer.cancel()
        cancelled = _pending_action
        _pending_timer = None
        _pending_action = None
        return {"ok": True, "cancelled": cancelled}


# --------------------------------------------------------------------------- #
# System updates (apt-get) - runs in a background thread with a live log
# --------------------------------------------------------------------------- #

MAX_LOG_LINES = 600
_update_lock = threading.Lock()
_update = {
    "state": "idle",        # idle | running | done | error
    "log": [],              # list[str], trimmed to MAX_LOG_LINES
    "started": None,
    "finished": None,
    "returncode": None,
}


def _log(line: str) -> None:
    with _update_lock:
        buf = _update["log"]
        buf.append(line)
        if len(buf) > MAX_LOG_LINES:
            del buf[: len(buf) - MAX_LOG_LINES]


def _run_update() -> None:
    """Run apt-get update && apt-get --with-new-pkgs upgrade -y, streamed to log."""
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    # `--with-new-pkgs upgrade` upgrades packages, including ones held back
    # because they need a NEW dependency installed, but (unlike full-upgrade /
    # dist-upgrade) never REMOVES an installed package to resolve dependencies.
    steps = [
        [SUDO, "-n", APT, "update"],
        [SUDO, "-n", APT, "--with-new-pkgs", "upgrade", "-y"],
    ]
    rc = 0
    for cmd in steps:
        _log("$ apt-get " + " ".join(cmd[3:]))
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, text=True, bufsize=1,
            )
        except OSError as exc:
            _log(f"error: {exc}")
            rc = 1
            break
        assert proc.stdout is not None
        for line in proc.stdout:
            _log(line.rstrip("\n"))
        proc.wait()
        if proc.returncode != 0:
            rc = proc.returncode
            _log(f"[exited with code {rc}]")
            break
    if rc == 0:
        _log("[updates complete]")
    with _update_lock:
        _update["state"] = "done" if rc == 0 else "error"
        _update["returncode"] = rc
        _update["finished"] = int(time.time())


def start_update() -> dict:
    with _update_lock:
        if _update["state"] == "running":
            return {"ok": False, "error": "an update is already running"}
        _update.update(state="running", log=[], started=int(time.time()),
                       finished=None, returncode=None)
    threading.Thread(target=_run_update, daemon=True).start()
    return {"ok": True}


def update_status() -> dict:
    with _update_lock:
        return {
            "state": _update["state"],
            "running": _update["state"] == "running",
            "returncode": _update["returncode"],
            "started": _update["started"],
            "finished": _update["finished"],
            "log": list(_update["log"]),
        }


# --------------------------------------------------------------------------- #
# App-icon generation (pure stdlib PNG encoder - keeps the project dependency
# free and asset free). Icons are rendered on demand and cached in memory.
# --------------------------------------------------------------------------- #

def _png_bytes(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0 (none) per scanline
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


_icon_cache: dict[int, bytes] = {}


def power_icon_png(size: int) -> bytes:
    """A full-bleed amber tile with a dark 'power' glyph, anti-aliased."""
    if size in _icon_cache:
        return _icon_cache[size]

    cx = cy = (size - 1) / 2.0
    radius = 0.27 * size
    half = 0.055 * size                 # half stroke width
    bar_top = cy - 0.34 * size
    bar_bot = cy - 0.02 * size
    gap = math.radians(36)              # half of the ring's top gap
    top = -math.pi / 2
    aa = 0.9                            # edge softness (px)
    top_rgb = (0xF2, 0xB0, 0x62)        # amber gradient, top -> bottom
    bot_rgb = (0xD5, 0x87, 0x2F)
    ink = (0x1C, 0x14, 0x08)           # dark glyph (--accent-ink)

    def smooth(e0: float, e1: float, x: float) -> float:
        if x <= e0:
            return 0.0
        if x >= e1:
            return 1.0
        t = (x - e0) / (e1 - e0)
        return t * t * (3 - 2 * t)

    cap_pts = [(cx + radius * math.cos(top + s * gap),
                cy + radius * math.sin(top + s * gap)) for s in (1.0, -1.0)]

    buf = bytearray(size * size * 4)
    i = 0
    for y in range(size):
        py = y + 0.5
        fy = py / size
        br = int(top_rgb[0] + (bot_rgb[0] - top_rgb[0]) * fy)
        bgc = int(top_rgb[1] + (bot_rgb[1] - top_rgb[1]) * fy)
        bb = int(top_rgb[2] + (bot_rgb[2] - top_rgb[2]) * fy)
        for x in range(size):
            px = x + 0.5
            dx = px - cx
            dy = py - cy
            dist = math.hypot(dx, dy)
            # Ring, minus a gap centered on the top.
            ang = math.atan2(dy, dx)
            da = abs(math.atan2(math.sin(ang - top), math.cos(ang - top)))
            g = 0.0 if da < gap else (1.0 - smooth(-aa, aa, abs(dist - radius) - half))
            # Rounded caps where the gap meets the ring.
            for ex, ey in cap_pts:
                cap = 1.0 - smooth(-aa, aa, math.hypot(px - ex, py - ey) - half)
                if cap > g:
                    g = cap
            # Vertical bar of the power symbol.
            by = bar_top if py < bar_top else (bar_bot if py > bar_bot else py)
            bar = 1.0 - smooth(-aa, aa, math.hypot(px - cx, py - by) - half)
            if bar > g:
                g = bar
            buf[i] = int(br + (ink[0] - br) * g)
            buf[i + 1] = int(bgc + (ink[1] - bgc) * g)
            buf[i + 2] = int(bb + (ink[2] - bb) * g)
            buf[i + 3] = 255
            i += 4

    png = _png_bytes(size, size, bytes(buf))
    _icon_cache[size] = png
    return png


ICON_SIZES = (180, 192, 512)


def manifest_json() -> str:
    return json.dumps({
        "name": "RpiControl",
        "short_name": "RpiControl",
        "description": "Reboot, shut down and update your Raspberry Pi",
        "start_url": "/",
        "scope": "/",
        "display": "fullscreen",
        "display_override": ["fullscreen", "standalone"],
        "orientation": "portrait-primary",
        "background_color": "#0d0e12",
        "theme_color": "#0d0e12",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png",
             "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "any maskable"},
        ],
    })


# --------------------------------------------------------------------------- #
# Status helpers
# --------------------------------------------------------------------------- #

def read_uptime() -> float | None:
    try:
        with open("/proc/uptime", encoding="ascii") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError):
        return None


def read_cpu_temp() -> float | None:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", encoding="ascii") as fh:
            return int(fh.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def humanize(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def status_payload() -> dict:
    uptime = read_uptime()
    temp = read_cpu_temp()
    with _pending_lock:
        pending = _pending_action
    return {
        "hostname": socket.gethostname(),
        "uptime_seconds": uptime,
        "uptime_human": humanize(uptime) if uptime is not None else None,
        "cpu_temp_c": round(temp, 1) if temp is not None else None,
        "pending": pending,
        "delay": DELAY,
        "time": int(time.time()),
    }


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #

def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    server_version = "RpiControl/1.0"
    protocol_version = "HTTP/1.1"

    # ----- helpers -------------------------------------------------------- #
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str,
                    cache: str = "no-store") -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Auth-Token", "")
        return bool(supplied) and constant_time_equals(supplied, TOKEN)

    def log_message(self, fmt: str, *args) -> None:  # quieter, single-line logs
        # Never log query strings: a `?token=...` bookmark would otherwise write
        # the secret into journald in clear text.
        line = fmt % args
        if self.path and "?" in self.path:
            line = line.replace(self.path, self.path.split("?", 1)[0])
        sys.stderr.write("[rpicontrol] %s - %s\n" % (self.address_string(), line))

    # ----- routes --------------------------------------------------------- #
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self._send_html(PAGE)
        elif path == "/api/status":
            if not self._authorized():
                self._send_json({"ok": False, "error": "unauthorized"}, status=401)
                return
            self._send_json(status_payload())
        elif path == "/api/update/status":
            if not self._authorized():
                self._send_json({"ok": False, "error": "unauthorized"}, status=401)
                return
            self._send_json(update_status())
        elif path == "/manifest.webmanifest":
            self._send_bytes(manifest_json().encode("utf-8"),
                             "application/manifest+json; charset=utf-8",
                             cache="public, max-age=86400")
        elif path.startswith("/icon-") and path.endswith(".png"):
            try:
                size = int(path[len("/icon-"):-len(".png")])
            except ValueError:
                size = 0
            if size in ICON_SIZES:
                self._send_bytes(power_icon_png(size), "image/png",
                                 cache="public, max-age=604800")
            else:
                self._send_json({"ok": False, "error": "not found"}, status=404)
        elif path == "/healthz":
            self._send_json({"ok": True})
        else:
            self._send_json({"ok": False, "error": "not found"}, status=404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        # Drain any request body so keep-alive connections stay in sync.
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length:
            self.rfile.read(length)

        if path in ("/api/reboot", "/api/shutdown"):
            if not self._authorized():
                self._send_json({"ok": False, "error": "unauthorized"}, status=401)
                return
            action = "reboot" if path.endswith("reboot") else "shutdown"
            self._send_json(schedule_action(action))
        elif path == "/api/update":
            if not self._authorized():
                self._send_json({"ok": False, "error": "unauthorized"}, status=401)
                return
            self._send_json(start_update())
        elif path == "/api/cancel":
            if not self._authorized():
                self._send_json({"ok": False, "error": "unauthorized"}, status=401)
                return
            self._send_json(cancel_action())
        else:
            self._send_json({"ok": False, "error": "not found"}, status=404)


# --------------------------------------------------------------------------- #
# Web GUI (single self-contained page)
# --------------------------------------------------------------------------- #

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0d0e12">
<title>RpiControl</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23e8a24a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 2v10'/%3E%3Cpath d='M18.36 6.64a9 9 0 1 1-12.73 0'/%3E%3C/svg%3E">
<!-- Installable web app / Add to Home Screen -->
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon-180.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="RpiControl">
<style>
  :root {
    /* Backgrounds & surfaces (darkest -> lightest) */
    --bg:            #0d0e12;
    --surface:       #15161d;
    --surface-2:     #1c1e27;
    --surface-3:     #242732;
    /* Borders */
    --border:        #2a2d38;
    --border-strong: #3a3e4c;
    /* Text */
    --text:  #ecedf2;
    --muted: #969cae;
    --faint: #686e7e;
    /* Accent - amber "tube glow" */
    --accent:        #e8a24a;
    --accent-strong: #d5872f;
    --accent-soft:   rgba(232,162,74,0.13);
    --accent-ink:    #1c1408;
    /* Secondary accent - teal */
    --accent-2: #4fc8bd;
    /* Status */
    --success: #63d68f;
    --danger:  #ff6f6f;
    /* Type & shape */
    --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    --mono: ui-monospace, "Cascadia Code", "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
    --radius:    14px;
    --radius-sm:  9px;
    --gap:       16px;
  }

  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    margin: 0; min-height: 100dvh; display: flex; font-family: var(--sans); color: var(--text);
    -webkit-font-smoothing: antialiased; -webkit-tap-highlight-color: transparent;
    background:
      radial-gradient(1100px 500px at 12% -12%, #1a1c27 0%, transparent 60%),
      radial-gradient(900px 480px at 100% -6%, #171a24 0%, transparent 55%),
      var(--bg);
    background-attachment: fixed;
  }

  /* --- MOBILE FIRST: full-height app shell -------------------------------- */
  .app {
    display: flex; flex-direction: column; flex: 1; width: 100%; min-height: 100dvh;
  }

  .topbar {
    position: sticky; top: 0; z-index: 5; display: flex; align-items: center; gap: 10px;
    padding: calc(16px + env(safe-area-inset-top)) calc(16px + env(safe-area-inset-right))
             14px calc(16px + env(safe-area-inset-left));
    background: rgba(13,14,18,.82); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border);
  }
  .topbar .ic { color: var(--accent); }
  h1 { margin: 0; font-size: 18px; font-weight: 650; letter-spacing: -0.01em; }
  .host {
    margin-left: auto; font-family: var(--mono); font-size: 11.5px; color: var(--muted);
    background: var(--bg); border: 1px solid var(--border); border-radius: 999px; padding: 5px 11px;
    max-width: 48%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }

  .content {
    flex: 1 1 auto; overflow-y: auto; -webkit-overflow-scrolling: touch;
    padding: 18px calc(16px + env(safe-area-inset-right)) 8px calc(16px + env(safe-area-inset-left));
  }
  .sub {
    color: var(--muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.09em;
    font-weight: 700; margin: 4px 0 10px;
  }
  .content .sub + .sub, .content .stats + .sub { margin-top: 22px; }

  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .stat {
    background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 13px 14px; display: flex; align-items: center; gap: 11px;
  }
  .stat .ic { color: var(--muted); flex: none; }
  .stat .k {
    color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.09em; font-weight: 700;
  }
  .stat .v { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 16px; font-weight: 600; margin-top: 2px; }

  label.check {
    display: flex; align-items: center; gap: 10px; font-size: 13.5px; color: var(--muted);
    margin: 2px 0 12px; min-height: 44px; cursor: pointer;
  }
  :where(input[type=checkbox]) { accent-color: var(--accent); width: 20px; height: 20px; flex: none; }

  input[type=password] {
    width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text);
    border-radius: var(--radius-sm); padding: 14px 14px; font-size: 16px; /* 16px: no iOS zoom */
    font-family: var(--mono); min-height: 52px; transition: border-color .12s, box-shadow .12s;
  }
  input[type=password]::placeholder { color: var(--faint); font-family: var(--sans); }
  input[type=password]:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }

  .log {
    margin: 0; font-family: var(--mono); font-size: 11.5px; line-height: 1.55;
    color: var(--muted); background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 12px; max-height: 42vh; overflow: auto;
    white-space: pre-wrap; word-break: break-word; font-variant-numeric: tabular-nums;
    -webkit-overflow-scrolling: touch;
  }

  /* --- Sticky action bar (thumb zone) ------------------------------------- */
  .actionbar {
    position: sticky; bottom: 0; display: grid; gap: 10px;
    padding: 12px calc(16px + env(safe-area-inset-right))
             calc(14px + env(safe-area-inset-bottom)) calc(16px + env(safe-area-inset-left));
    background: linear-gradient(to top, var(--bg) 62%, rgba(13,14,18,0));
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
    border-top: 1px solid var(--border);
  }
  .btn {
    border: 1px solid var(--border); background: var(--surface-3); color: var(--text);
    padding: 14px 16px; border-radius: var(--radius-sm); font-size: 15px; font-weight: 600;
    cursor: pointer; min-height: 52px; touch-action: manipulation;
    display: inline-flex; align-items: center; justify-content: center; gap: 8px; font-family: var(--sans);
    transition: filter .12s, transform .04s, border-color .12s;
  }
  .btn:hover:not(:disabled) { filter: brightness(1.15); border-color: var(--border-strong); }
  .btn:active:not(:disabled) { transform: translateY(1px); }
  .btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .btn:disabled { opacity: .5; cursor: not-allowed; filter: none; }
  .btn.primary {
    background: linear-gradient(180deg, #f2b062, var(--accent-strong));
    border-color: transparent; color: var(--accent-ink); font-weight: 700;
  }
  .btn.primary .ic { color: var(--accent-ink); }
  .btn.danger { color: var(--danger); }
  .btn.ghost { background: var(--surface-3); }

  .msg {
    font-size: 12.5px; text-align: center; border-radius: 999px; padding: 9px 12px;
    border: 1px solid transparent; transition: all .12s; font-variant-numeric: tabular-nums;
  }
  .msg:empty { display: none; }
  .msg.ok   { color: var(--success); border-color: rgba(99,214,143,.30); background: rgba(99,214,143,.08); }
  .msg.err  { color: var(--danger);  border-color: rgba(255,111,111,.40); background: rgba(255,111,111,.10); }
  .msg.info { color: var(--accent-2); border-color: rgba(79,200,189,.30);  background: rgba(79,200,189,.08); }
  .spinner {
    width: 13px; height: 13px; border: 2px solid rgba(255,255,255,.22); border-top-color: var(--accent-2);
    border-radius: 50%; animation: spin .8s linear infinite; display: inline-block; vertical-align: -2px; margin-right: 6px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* --- DESKTOP ENHANCEMENT: collapse the shell into a centered console ---- */
  @media (min-width: 600px) {
    body { align-items: center; justify-content: center; padding: var(--gap); }
    .app {
      flex: none; min-height: 0; max-width: 440px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); overflow: hidden;
    }
    .topbar {
      position: static; background: transparent; backdrop-filter: none; -webkit-backdrop-filter: none;
      padding: 20px 20px 14px;
    }
    .content { overflow: visible; padding: 6px 20px 4px; }
    .actionbar {
      position: static; background: transparent; backdrop-filter: none; -webkit-backdrop-filter: none;
      border-top: none; padding: 14px 20px 20px;
    }
    .btn { min-height: 46px; padding: 12px 16px; font-size: 13.5px; }
    .btn:hover:not(:disabled) { filter: brightness(1.15); }
    input[type=password], label.check { min-height: 0; }
    input[type=password] { padding: 11px 12px; }
    label.check { min-height: 0; margin-bottom: 10px; }
  }

  @media (prefers-reduced-motion: reduce) {
    * { animation-duration: .001ms !important; transition-duration: .001ms !important; }
  }
</style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <span id="titleIcon" class="ic"></span>
      <h1>RpiControl</h1>
      <span class="host" id="host">raspberrypi</span>
    </header>

    <main class="content">
      <div class="sub">Status</div>
      <div class="stats">
        <div class="stat"><span id="icUptime" class="ic"></span><div><div class="k">Uptime</div><div class="v" id="uptime">-</div></div></div>
        <div class="stat"><span id="icTemp" class="ic"></span><div><div class="k">CPU temp</div><div class="v" id="temp">-</div></div></div>
      </div>

      <div class="sub">Access</div>
      <label class="check"><input type="checkbox" id="remember" checked> Remember token on this device</label>
      <input type="password" id="token" placeholder="Access token" autocomplete="current-password">

      <div class="sub" id="logHead" hidden>Update log</div>
      <pre class="log" id="log" hidden></pre>
    </main>

    <footer class="actionbar">
      <div class="msg" id="msg"></div>
      <button class="btn ghost"   id="btnUpdate"><span id="icUpdate" class="ic"></span>Run updates</button>
      <button class="btn primary" id="btnReboot"><span id="icReboot" class="ic"></span>Reboot</button>
      <button class="btn danger"  id="btnShutdown"><span id="icShutdown" class="ic"></span>Shut down</button>
      <button class="btn ghost"   id="btnCancel" hidden><span id="icCancel" class="ic"></span>Cancel pending action</button>
    </footer>
  </div>

<script>
(function () {
  const $ = (id) => document.getElementById(id);

  // --- Lucide icons (stroke-only, inlined as paths) ------------------------
  const ICONS = {
    power:     '<path d="M12 2v10"/><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/>',
    reboot:    '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    x:         '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    clock:     '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    thermo:    '<path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/>',
    download:  '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
  };
  function icon(name, size) {
    return '<svg class="ic" width="' + (size || 16) + '" height="' + (size || 16) + '" viewBox="0 0 24 24" ' +
      'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true">' + (ICONS[name] || '') + '</svg>';
  }
  $("titleIcon").innerHTML  = icon("power", 20);
  $("icUptime").innerHTML   = icon("clock");
  $("icTemp").innerHTML     = icon("thermo");
  $("icUpdate").innerHTML   = icon("download");
  $("icReboot").innerHTML   = icon("reboot");
  $("icShutdown").innerHTML = icon("power");
  $("icCancel").innerHTML   = icon("x");

  // --- Logic ---------------------------------------------------------------
  const tokenEl = $("token"), rememberEl = $("remember"), msgEl = $("msg");
  const KEY = "rpicontrol_token";

  const params = new URLSearchParams(location.search);
  const urlToken = params.get("token");
  tokenEl.value = urlToken || localStorage.getItem(KEY) || "";
  // Don't leave the token sitting in the address bar / history if it arrived
  // via ?token=... — read it once, then scrub it from the URL.
  if (urlToken) {
    params.delete("token");
    const qs = params.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
  }

  function token() { return tokenEl.value.trim(); }
  function saveToken() {
    if (rememberEl.checked && token()) localStorage.setItem(KEY, token());
    else localStorage.removeItem(KEY);
  }
  function say(text, kind, spinner) {
    msgEl.className = "msg " + (kind || "");
    msgEl.textContent = "";
    if (spinner) {
      const sp = document.createElement("span");
      sp.className = "spinner";
      msgEl.appendChild(sp);
    }
    if (text) msgEl.appendChild(document.createTextNode(text));
  }

  async function api(path, opts) {
    const res = await fetch(path, Object.assign({
      method: "POST",
      headers: { "X-Auth-Token": token() },
    }, opts));
    let data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
    return data;
  }

  async function refresh() {
    if (!token()) return;  // status requires the token
    try {
      const res = await fetch("/api/status", { headers: { "X-Auth-Token": token() } });
      if (!res.ok) return;
      const s = await res.json();
      $("host").textContent = s.hostname || "Raspberry Pi";
      $("uptime").textContent = s.uptime_human || "-";
      $("temp").textContent = (s.cpu_temp_c != null) ? s.cpu_temp_c + " °C" : "-";
      $("btnCancel").hidden = !s.pending;
      if (s.pending) say(s.pending + " in progress — you can still cancel", "info", true);
    } catch (e) { /* ignore transient errors */ }
  }

  async function doAction(action) {
    if (!token()) { say("Enter the access token first", "err"); return; }
    if (!confirm("Really " + action + " the Raspberry Pi?")) return;
    saveToken();
    try {
      const r = await api("/api/" + action);
      if (r.ok) say(action + " scheduled in " + r.delay + "s — cancel now if this was a mistake.", "ok");
      else say(r.error || "Failed", "err");
      refresh();
    } catch (e) { say(e.message, "err"); }
  }

  $("btnReboot").onclick   = () => doAction("reboot");
  $("btnShutdown").onclick = () => doAction("shutdown");
  $("btnCancel").onclick   = async () => {
    try { const r = await api("/api/cancel");
      say(r.ok ? "Cancelled." : (r.error || "Nothing to cancel"), r.ok ? "ok" : "err");
      refresh();
    } catch (e) { say(e.message, "err"); }
  };

  // --- System updates ------------------------------------------------------
  const logEl = $("log"), logHead = $("logHead"), btnUpdate = $("btnUpdate");
  let updatePolling = false;

  function renderUpdate(st) {
    if (st.log && st.log.length) {
      logHead.hidden = false; logEl.hidden = false;
      const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
      logEl.textContent = st.log.join("\n");
      if (atBottom) logEl.scrollTop = logEl.scrollHeight;
    }
    const running = st.state === "running";
    btnUpdate.disabled = running;
    $("btnReboot").disabled = running;
    $("btnShutdown").disabled = running;
  }

  async function updateStatus() {
    const res = await fetch("/api/update/status", { method: "GET", headers: { "X-Auth-Token": token() } });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return res.json();
  }

  async function pollUpdate() {
    if (updatePolling) return;
    updatePolling = true;
    try {
      while (true) {
        const st = await updateStatus();
        renderUpdate(st);
        if (st.state === "running") {
          say("Installing updates — this can take a few minutes", "info", true);
          await new Promise(r => setTimeout(r, 1500));
          continue;
        }
        if (st.state === "done")  say("Updates complete.", "ok");
        if (st.state === "error") say("Update failed (exit " + st.returncode + ") — see log.", "err");
        break;
      }
    } catch (e) { /* token missing or transient network error */ }
    finally { updatePolling = false; }
  }

  btnUpdate.onclick = async () => {
    if (!token()) { say("Enter the access token first", "err"); return; }
    if (!confirm("Run system updates now?\n\napt-get update && apt-get --with-new-pkgs upgrade -y — this can take several minutes and must not be interrupted.")) return;
    saveToken();
    try {
      const r = await api("/api/update");
      if (!r.ok) { say(r.error || "Failed to start updates", "err"); return; }
      say("Starting updates…", "info", true);
      pollUpdate();
    } catch (e) { say(e.message, "err"); }
  };

  // If an update is already running (e.g. after a page reload), reattach.
  (async function resumeUpdate() {
    if (!token()) return;
    try {
      const st = await updateStatus();
      if (st.state === "running") { renderUpdate(st); pollUpdate(); }
    } catch (e) { /* ignore */ }
  })();

  // Status needs the token, so refresh as soon as one is entered/changed.
  tokenEl.addEventListener("change", refresh);

  refresh();
  setInterval(refresh, 5000);
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def _prewarm_icons() -> None:
    for size in ICON_SIZES:
        try:
            power_icon_png(size)
        except Exception:  # noqa: BLE001 - best-effort cache warming
            pass


def main() -> None:
    # Render the app icons up front, off the request path, so the first PWA
    # install doesn't wait on a CPU-bound render.
    threading.Thread(target=_prewarm_icons, daemon=True).start()

    httpd = ThreadingHTTPServer((HOST, PORT), Handler)

    def shutdown_handler(signum, frame):
        sys.stderr.write("\n[rpicontrol] shutting down server\n")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    sys.stderr.write(f"[rpicontrol] listening on http://{HOST}:{PORT}\n")
    if TOKEN_WAS_GENERATED:
        sys.stderr.write(
            "[rpicontrol] no RPICONTROL_TOKEN set - generated one for this run:\n"
            f"[rpicontrol]     {TOKEN}\n"
            "[rpicontrol] set RPICONTROL_TOKEN to keep it stable across restarts.\n"
        )
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
