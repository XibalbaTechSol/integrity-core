#!/usr/bin/env bash
set -euo pipefail

PREFIX="${PREFIX:-/opt/integrity-core}"
SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"
CONFIG_DIR="${CONFIG_DIR:-/etc/xibalba-integrity}"
STATE_DIR="${STATE_DIR:-/var/lib/xibalba-integrity}"
SERVICE_USER="${SERVICE_USER:-xibalba-integrity}"

if [ "$(id -u)" -ne 0 ]; then
  echo "install_policy_publisher.sh must run as root" >&2
  exit 1
fi
getent group "$SERVICE_USER" >/dev/null 2>&1 || groupadd --system "$SERVICE_USER"
getent passwd "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --gid "$SERVICE_USER" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
install -d -m 0755 "$PREFIX/scripts" "$SERVICE_DIR"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$CONFIG_DIR" "$STATE_DIR"
install -m 0755 scripts/shield_policy_publisher.py "$PREFIX/scripts/shield_policy_publisher.py"
install -m 0644 packaging/systemd/xibalba-core-shield-policy.service "$SERVICE_DIR/xibalba-core-shield-policy.service"
if [ ! -f "$CONFIG_DIR/policy-publisher.env" ]; then
  install -m 0600 -o "$SERVICE_USER" -g "$SERVICE_USER" packaging/systemd/policy-publisher.env.example "$CONFIG_DIR/policy-publisher.env"
fi
systemctl daemon-reload
systemctl enable xibalba-core-shield-policy.service
echo "Installed policy publisher; edit $CONFIG_DIR/policy-publisher.env and start the service."
