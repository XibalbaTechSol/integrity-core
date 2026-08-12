# Local Stack

The MVP can run against the real local Integrity services and the graph-memory
viewer API. From this repository, start the stack with:

```bash
./scripts/dev-stack.sh
```

The script starts `xibalba-cortex` on `http://localhost:8420`, then runs
the `oracle-backend` and `bcc-middleware` services from the sibling
`INTEGRITY-LATEST/docker-compose.yml`. Docker Compose starts their Postgres,
Redis, and OPA dependencies as needed. In a second terminal, run the MVP:

```bash
npm run dev -- --port 5174
```

The Memory page uses `GET /api/status` and shows an explicit unavailable state
when graph-memory is stopped. The header connectivity indicators probe Oracle
`/healthz`, BCC `/health`, and graph-memory `/api/status`.

Useful overrides:

```bash
INTEGRITY_ROOT=/path/to/INTEGRITY-LATEST \
XIBALBA_GRAPH_HOME=/path/to/graph-home \
./scripts/dev-stack.sh
```

This is a development workflow only. The compose file's development credentials
and local chain settings must not be reused in production.
