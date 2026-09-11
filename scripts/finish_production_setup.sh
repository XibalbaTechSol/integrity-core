#!/usr/bin/env bash
set -euo pipefail

# Finish the local deployment wiring for CORE -> Shield -> Cortex.
# This script is deliberately fail-closed: it never enables AGENT_DIRECTORY_FINALIZED
# without a live finalized snapshot, never accepts a sudo password argument, and never
# submits an on-chain transaction.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTEGRITY_CONFIG_DIR="${INTEGRITY_CONFIG_DIR:-/etc/xibalba-integrity}"
SHIELD_CONFIG_DIR="${SHIELD_CONFIG_DIR:-/etc/xibalba-shield}"
ISSUER_SEED_FILE="${ISSUER_SEED_FILE:-$INTEGRITY_CONFIG_DIR/oracle-policy-issuer.seed}"
ISSUER_PUBLIC_FILE="${ISSUER_PUBLIC_FILE:-$INTEGRITY_CONFIG_DIR/oracle-policy-issuer.pub}"
PUBLISHER_ENV="${PUBLISHER_ENV:-$INTEGRITY_CONFIG_DIR/policy-publisher.env}"
SHIELD_BACKEND_ENV="${SHIELD_BACKEND_ENV:-$SHIELD_CONFIG_DIR/backend.env}"
CORE_URL="${CORE_URL:-http://127.0.0.1:8080}"
SHIELD_URL="${SHIELD_URL:-http://127.0.0.1:8421}"
SHIELD_TENANT_ID="${SHIELD_TENANT_ID:-}"
ROTATE_ISSUER_KEY="${ROTATE_ISSUER_KEY:-false}"
ENABLE_FINALITY="${ENABLE_FINALITY:-false}"

die() { echo "ERROR: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

usage() {
  cat <<'EOF'
Usage: sudo -E bash scripts/finish_production_setup.sh

Required environment:
  SHIELD_ADMIN_TOKEN   Shield backend admin token (never printed)
  SHIELD_TENANT_ID     tenant used by the policy publisher

Optional gates:
  ROTATE_ISSUER_KEY=true  replace an existing issuer keypair; default preserves it
  ENABLE_FINALITY=true    only succeeds if CORE returns a valid finalized snapshot
The script installs file-backed secrets, configures the publisher and Shield trust path,
restarts services, verifies health, and leaves finality disabled unless the explicit gate
passes. It does not run blockchain transactions or accept a password argument.
EOF
}

[[ "${1:-}" != "--help" ]] || { usage; exit 0; }
[[ "$(id -u)" -eq 0 ]] || die "run with sudo from the repository checkout"
[[ -n "${SHIELD_ADMIN_TOKEN:-}" ]] || die "SHIELD_ADMIN_TOKEN must be provided in the environment"
[[ -n "$SHIELD_TENANT_ID" ]] || die "SHIELD_TENANT_ID must be provided in the environment"
case "$SHIELD_ADMIN_TOKEN" in
  your-*|actual-*|REPLACE_*|replace-*) die "SHIELD_ADMIN_TOKEN still contains a placeholder" ;;
esac
case "$SHIELD_TENANT_ID" in
  your-*|actual-*|REPLACE_*|replace-*) die "SHIELD_TENANT_ID still contains a placeholder" ;;
esac

need install
need curl
need python3
need systemctl

install -d -m 0750 "$INTEGRITY_CONFIG_DIR"
install -d -m 0750 "$SHIELD_CONFIG_DIR"

# Generate a fresh Ed25519 seed and PEM public key only when no pair exists. Rotation is
# explicit so a rerun cannot silently invalidate already-issued credentials.
if [[ ! -s "$ISSUER_SEED_FILE" || ! -s "$ISSUER_PUBLIC_FILE" || "$ROTATE_ISSUER_KEY" == "true" ]]; then
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  python3 - "$tmpdir" <<'PY'
from pathlib import Path
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

out = Path(sys.argv[1])
key = Ed25519PrivateKey.generate()
seed = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
pub = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
(out / "seed").write_text(seed.hex() + "\n", encoding="ascii")
(out / "pub").write_bytes(pub)
PY
  install -o root -g root -m 0600 "$tmpdir/seed" "$ISSUER_SEED_FILE"
  install -o root -g root -m 0644 "$tmpdir/pub" "$ISSUER_PUBLIC_FILE"
  rm -rf "$tmpdir"
  trap - EXIT
fi

[[ -s "$ISSUER_SEED_FILE" && -s "$ISSUER_PUBLIC_FILE" ]] || die "issuer keypair was not created"

# Keep operator-owned settings intact while ensuring the two required trust paths exist.
if [[ ! -e "$SHIELD_BACKEND_ENV" ]]; then
  die "$SHIELD_BACKEND_ENV is missing; create the Shield backend environment first"
fi
python3 - "$SHIELD_BACKEND_ENV" "$ISSUER_PUBLIC_FILE" <<'PY'
from pathlib import Path
import sys

path, pub = map(Path, sys.argv[1:])
lines = path.read_text(encoding="utf-8").splitlines()
key = "XIBALBA_ORACLE_POLICY_PUBLIC_KEY"
replacement = f"{key}=file:{pub}"
seen = False
out = []
for line in lines:
    if line.startswith(key + "="):
        if not seen:
            out.append(replacement)
            seen = True
    else:
        out.append(line)
if not seen:
    out.append(replacement)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
chmod 0600 "$SHIELD_BACKEND_ENV"

if [[ ! -e "$PUBLISHER_ENV" ]]; then
  install -o xibalba-integrity -g xibalba-integrity -m 0600 \
    "$REPO_ROOT/packaging/systemd/policy-publisher.env.example" "$PUBLISHER_ENV"
fi
SHIELD_ADMIN_TOKEN="$SHIELD_ADMIN_TOKEN" python3 - "$PUBLISHER_ENV" "$SHIELD_TENANT_ID" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
tenant = sys.argv[2]
token = os.environ["SHIELD_ADMIN_TOKEN"]
values = {
    "SHIELD_URL": "http://127.0.0.1:8421",
    "CORE_ORACLE_URL": "http://127.0.0.1:8080",
    "SHIELD_ADMIN_TOKEN": token,
    "SHIELD_TENANT_ID": tenant,
}
lines = path.read_text(encoding="utf-8").splitlines()
out, seen = [], set()
for line in lines:
    name = line.split("=", 1)[0] if "=" in line else ""
    if name in values:
        if name not in seen:
            out.append(f"{name}={values[name]}")
            seen.add(name)
    else:
        out.append(line)
for name, value in values.items():
    if name not in seen:
        out.append(f"{name}={value}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
chown xibalba-integrity:xibalba-integrity "$PUBLISHER_ENV"
chmod 0600 "$PUBLISHER_ENV"

# Install the current checkout and restart only the service this script owns.
bash "$REPO_ROOT/scripts/install_policy_publisher.sh"
systemctl restart xibalba-shield-backend.service
systemctl restart xibalba-core-shield-policy.service

curl --fail --silent --show-error "$SHIELD_URL/api/shield/health" >/dev/null || die "Shield health check failed"
if ! curl --fail --silent --show-error "$CORE_URL/healthz" >/dev/null; then
  echo "CORE is not live at $CORE_URL; publisher will remain retry-safe, finality stays disabled." >&2
  exit 2
fi

if [[ "$ENABLE_FINALITY" == "true" ]]; then
  snapshot="$(curl --fail --silent --show-error "$CORE_URL/v1/agents/snapshot")" || die "could not fetch CORE snapshot"
  python3 - "$snapshot" <<'PY'
import json, re, sys
p = json.loads(sys.argv[1])
if p.get("finalized") is not True:
    raise SystemExit("snapshot is not finalized")
block = int(p["block_number"])
finalized = int(p["finalized_block_number"])
if finalized < block or not re.fullmatch(r"0x[0-9a-fA-F]{64}", str(p["finalized_block_hash"])):
    raise SystemExit("snapshot finalized cursor is invalid or does not cover snapshot")
print("finalized snapshot verified at block", block, "cursor", finalized)
PY
  echo "Finality evidence verified. Set AGENT_DIRECTORY_FINALIZED=true in the Cortex deployment environment and restart its sync service." >&2
else
  echo "Finality gate not requested; AGENT_DIRECTORY_FINALIZED remains unchanged." >&2
fi

echo "Policy publisher and Shield trust wiring installed. Verify with: systemctl --no-pager status xibalba-core-shield-policy.service"
