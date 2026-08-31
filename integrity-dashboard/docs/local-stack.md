# Integrated stack

To run Cortex, the Shield backend, and the dashboard wiring together with the
canonical Integrity services, use the core repository launcher:

```bash
cd ..
./scripts/dev-integrated-stack.sh
```

This applies `docker-compose.integrations.yml`, exposes Cortex on `:8420`, the
Shield backend on `:8765`, and the dashboard on `:5173`. It keeps Cortex and
Shield data in separate named volumes. This remains a local development
workflow; healthy HTTP endpoints do not establish live-chain or production
security evidence.

# Local Stack

The MVP can run against the real local Integrity services and the graph-memory
viewer API. From this repository, start the stack with:

```bash
./scripts/dev-stack.sh
```

The script starts `xibalba-cortex` on `http://localhost:8420`, then runs
the `oracle-backend` and `bcc-middleware` services from the sibling
`integrity-core/docker-compose.yml`. Docker Compose starts their Postgres,
Redis, and OPA dependencies as needed. In a second terminal, run the MVP:

```bash
npm run dev -- --port 5174
```

The Memory page uses `GET /api/status` and shows an explicit unavailable state
when graph-memory is stopped. The header connectivity indicators probe Oracle
`/healthz`, BCC `/health`, and graph-memory `/api/status`.

Useful overrides:

```bash
INTEGRITY_ROOT=/path/to/integrity-core \
XIBALBA_CORTEX_HOME=/path/to/graph-home \
./scripts/dev-stack.sh
```

This is a development workflow only. The compose file's development credentials
and local chain settings must not be reused in production.
