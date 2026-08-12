#!/usr/bin/env bash
# RpiControl installer - run ON the Raspberry Pi (Raspberry Pi OS Trixie, 64-bit).
#
#   git clone / copy this folder to the Pi, then:
#       cd RpiControl
#       sudo bash install.sh
#
# It creates a locked-down 'rpicontrol' user, installs the server to
# /opt/rpicontrol, grants a narrow sudo rule for reboot/poweroff, and starts a
# systemd service. Re-running is safe (idempotent).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo:  sudo bash install.sh" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/rpicontrol"
ENV_FILE="/etc/rpicontrol.env"
SERVICE="/etc/systemd/system/rpicontrol.service"
SUDOERS="/etc/sudoers.d/rpicontrol"
PORT="${RPICONTROL_PORT:-8080}"

echo "==> Creating service user 'rpicontrol'"
if ! id rpicontrol >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin rpicontrol
fi

echo "==> Installing server to ${APP_DIR}"
install -d -o root -g root -m 0755 "$APP_DIR"
install -o root -g root -m 0644 "$SRC_DIR/server.py" "$APP_DIR/server.py"

echo "==> Writing ${ENV_FILE}"
if [[ ! -f "$ENV_FILE" ]]; then
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  cat > "$ENV_FILE" <<EOF
# RpiControl configuration. Keep this file private (it holds the access token).
RPICONTROL_TOKEN=${TOKEN}
RPICONTROL_PORT=${PORT}
# RPICONTROL_HOST=0.0.0.0
# RPICONTROL_DELAY=5
EOF
  chown root:rpicontrol "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  echo "    Generated access token: ${TOKEN}"
else
  echo "    ${ENV_FILE} already exists - leaving it (and your token) untouched."
fi

echo "==> Installing sudoers rule"
install -o root -g root -m 0440 "$SRC_DIR/rpicontrol-sudoers" "$SUDOERS"
visudo -cf "$SUDOERS"

echo "==> Installing systemd service"
install -o root -g root -m 0644 "$SRC_DIR/rpicontrol.service" "$SERVICE"
systemctl daemon-reload
systemctl enable --now rpicontrol.service

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "==> Done. RpiControl is running."
echo "    Open:   http://${IP:-<pi-ip>}:${PORT}/"
echo "    Token:  see ${ENV_FILE}  (sudo cat ${ENV_FILE})"
echo "    Status: systemctl status rpicontrol"
echo "    Logs:   journalctl -u rpicontrol -f"
