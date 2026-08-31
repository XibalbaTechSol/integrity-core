#!/usr/bin/env bash
set -euo pipefail

# Starts the complete local cross-repository stack. The base compose file is
# intentionally unchanged; this overlay is the explicit integration boundary.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec docker compose \
  -f "$ROOT/docker-compose.yml" \
  -f "$ROOT/docker-compose.integrations.yml" \
  up --build "$@"
