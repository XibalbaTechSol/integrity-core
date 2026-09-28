#!/usr/bin/env bash
# Scan the commits about to be pushed for secrets, before they reach a public remote.
#
# docs/EXECUTION_PLAN.md A0: integrity-core, xibalba-shield and xibalba-cortex are
# public, and the Phase A splits/mirrors copy history into new repositories.
# Known local secrets (contracts/.env, a prover config with a populated
# `secret_key`) are gitignored, but a mistake in staging would be published the
# moment it is pushed. This runs gitleaks (pinned, fetched from its GitHub
# release) over exactly the commits in <base>..HEAD, with findings redacted so
# the scan's own output never repeats a secret.
#
# Usage: scripts/secret_scan.sh [base-ref]     (default: origin/main)
# Exit status: 0 clean, 1 findings, 2 setup error.

set -euo pipefail

GITLEAKS_VERSION="8.28.0"
base="${1:-origin/main}"

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) asset="linux_x64" ;;
  Linux-aarch64) asset="linux_arm64" ;;
  Darwin-arm64) asset="darwin_arm64" ;;
  Darwin-x86_64) asset="darwin_x64" ;;
  *) echo "unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 2 ;;
esac

bin_dir="$HOME/.local/bin"
gitleaks="$bin_dir/gitleaks"
if ! "$gitleaks" version 2>/dev/null | grep -q "${GITLEAKS_VERSION}"; then
  mkdir -p "$bin_dir"
  curl -fsSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_${asset}.tar.gz" \
    | tar -xz -C "$bin_dir" gitleaks || { echo "could not install gitleaks ${GITLEAKS_VERSION}" >&2; exit 2; }
fi

repo_root="$(git rev-parse --show-toplevel)"
if ! git -C "$repo_root" rev-parse --verify --quiet "$base" >/dev/null; then
  echo "base ref '$base' not found; fetch it first (git fetch origin main)" >&2
  exit 2
fi

count="$(git -C "$repo_root" rev-list --count "$base..HEAD")"
echo "scanning $count commit(s) in $base..HEAD"
if [ "$count" -eq 0 ]; then
  exit 0
fi

set +e
"$gitleaks" git "$repo_root" --log-opts="$base..HEAD" --redact --no-banner --exit-code 1
status=$?
set -e
if [ "$status" -eq 1 ]; then
  echo "secret scan found potential secrets; do not push until they are removed from history" >&2
  exit 1
fi
exit "$status"
