#!/usr/bin/env bash
# Install the pinned contract/policy toolchain from GitHub release assets.
#
# Why this exists (docs/EXECUTION_PLAN.md, A0): cloud sessions and fresh
# containers start without forge/anvil/opa, and some egress policies block
# binaries.soliditylang.org, which forge normally uses to fetch solc. Every
# binary here comes from a GitHub release instead, at the versions pinned in
# docs/INTERFACE_CONTRACT.md. Halmos is not installed here: `make verify-kernel`
# already installs its pinned version into contracts/.venv-halmos.
#
# Idempotent: a tool already at the pinned version is left alone.
# Usage: scripts/install_toolchain.sh            (installs into ~/.foundry/bin, ~/.svm, ~/.local/bin)
#        FOUNDRY_OFFLINE=true forge build        (afterwards, when the solc host is blocked)

set -euo pipefail

FOUNDRY_VERSION="1.7.1"   # INTERFACE_CONTRACT.md: forge/anvil 1.7.1
SOLC_VERSION="0.8.28"     # contracts/foundry.toml: solc_version
OPA_VERSION="1.18.2"      # INTERFACE_CONTRACT.md: opa 1.18.2

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) foundry_asset="linux_amd64"; solc_asset="solc-static-linux"; opa_asset="opa_linux_amd64_static" ;;
  Linux-aarch64) foundry_asset="linux_arm64"; solc_asset=""; opa_asset="opa_linux_arm64_static" ;;
  Darwin-arm64) foundry_asset="darwin_arm64"; solc_asset="solc-macos"; opa_asset="opa_darwin_arm64_static" ;;
  Darwin-x86_64) foundry_asset="darwin_amd64"; solc_asset="solc-macos"; opa_asset="opa_darwin_amd64" ;;
  *) echo "unsupported platform: $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

foundry_bin="${FOUNDRY_DIR:-$HOME/.foundry}/bin"
local_bin="$HOME/.local/bin"
mkdir -p "$foundry_bin" "$local_bin"

# forge, anvil, cast, chisel -- one release tarball.
if ! "$foundry_bin/forge" --version 2>/dev/null | grep -q "Version: ${FOUNDRY_VERSION}"; then
  echo "installing foundry ${FOUNDRY_VERSION}"
  curl -fsSL "https://github.com/foundry-rs/foundry/releases/download/v${FOUNDRY_VERSION}/foundry_v${FOUNDRY_VERSION}_${foundry_asset}.tar.gz" \
    | tar -xz -C "$foundry_bin"
fi

# solc, placed where forge's solc manager (svm) looks for it, so a build never
# needs to reach binaries.soliditylang.org. solc publishes no static linux-arm64
# binary on GitHub; on that platform forge must be allowed to fetch it itself.
solc_path="$HOME/.svm/${SOLC_VERSION}/solc-${SOLC_VERSION}"
if [ -n "$solc_asset" ] && ! "$solc_path" --version 2>/dev/null | grep -q "${SOLC_VERSION}"; then
  echo "installing solc ${SOLC_VERSION}"
  mkdir -p "$(dirname "$solc_path")"
  curl -fsSL -o "$solc_path" "https://github.com/ethereum/solidity/releases/download/v${SOLC_VERSION}/${solc_asset}"
  chmod +x "$solc_path"
fi

# opa, used by bcc_middleware's `opa test policies/`.
if ! "$local_bin/opa" version 2>/dev/null | grep -q "Version: ${OPA_VERSION}"; then
  echo "installing opa ${OPA_VERSION}"
  curl -fsSL -o "$local_bin/opa" "https://github.com/open-policy-agent/opa/releases/download/v${OPA_VERSION}/${opa_asset}"
  chmod +x "$local_bin/opa"
fi

"$foundry_bin/forge" --version | head -1
"$foundry_bin/anvil" --version | head -1
[ -x "$solc_path" ] && "$solc_path" --version | tail -1
"$local_bin/opa" version | head -1
echo "add to PATH if needed: export PATH=\"$foundry_bin:$local_bin:\$PATH\""
