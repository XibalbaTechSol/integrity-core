# Integrated local stack

Run the complete dashboard integration stack from the `integrity-core` root:

```bash
./scripts/dev-integrated-stack.sh
```

The script applies `docker-compose.integrations.yml` over the core compose
file. In addition to Oracle, BCC middleware, User API, OPA, and the Shield
enforcement daemon, it starts:

- Cortex local API at `http://localhost:8420`
- Shield backend API at `http://localhost:8765`
- Dashboard at `http://localhost:5173`

Cortex data and Shield backend data use separate named volumes. Cortex remains
the authority for its profile-scoped memory; Shield remains the authority for
endpoint enforcement and its local evidence store.

This is a local integration environment. It does not establish production,
testnet, external-counterparty, or compliance evidence.
